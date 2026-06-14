"""
Main OR Core — ML Engine v4 (XGBoost + multi-level evidence + fuzzy)
ใช้ SurgicalTimePredictor จาก main_or_predictor.py แทน RF เก่า
"""
import os
import pickle
import re
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Main OR constants
TURNOVER_MAIN = 15            # turnover เวลาเตรียมห้อง (นาที) — Main OR > Minor
WORK_START = 8
WORK_END = 17                 # Main OR ทำงานยาวกว่า Minor (8-17)
WORK_MINUTES = (WORK_END - WORK_START) * 60   # 540 นาที

# Backward-compat alias (เผื่อ admin/tracking imported TURNOVER_MINOR)
TURNOVER_MINOR = TURNOVER_MAIN

# ============================================================================
# ML MODEL LOADER — ใช้ SurgicalTimePredictor v2 (XGBoost + multi-evidence)
# ============================================================================

@st.cache_resource
def load_ml_assets():
    """โหลด predictor v2 (XGBoost + fuzzy + multi-level evidence)"""
    assets = {'predictor': None, 'model_loaded': False, 'error': None}
    try:
        from main_or_predictor import SurgicalTimePredictor
        assets['predictor'] = SurgicalTimePredictor.load_default()
        assets['model_loaded'] = True
    except Exception as e:
        assets['error'] = str(e)
        print(f"Warning: Cannot load predictor: {e}")
    return assets


# ============================================================================
# Fuzzy helper (deprecated — predictor v2 ทำ fuzzy ภายในเอง)
# เก็บไว้เผื่อ legacy callers
# ============================================================================
from difflib import get_close_matches

def fuzzy_resolve(query, candidates, cutoff=0.65):
    if not query or not candidates:
        return None, None
    if query in candidates:
        return query, 'exact'
    contains = [c for c in candidates if query in c]
    if contains:
        return min(contains, key=len), 'contains'
    rev = [c for c in candidates if c and c in query]
    if rev:
        return max(rev, key=len), 'contains_rev'
    matches = get_close_matches(query, candidates, n=1, cutoff=cutoff)
    if matches:
        return matches[0], 'fuzzy'
    return None, None

# ============================================================================
# PREDICTION ENGINE v3 (16 features — optimized, Major-OR compatible)
# Feature order MUST match training:
#   [proc_enc, surgeon_enc, division_enc, age, op_hour, day_of_week, month,
#    timeslot_enc, optype_enc, surgeon_avg_duration, proc_avg_duration,
#    surg_proc_avg, scrub_enc, circ_enc, wait_min, month_avg]
# ============================================================================

def predict_surgical_time(procedure: str, age: int, surgeon: str = "",
                          division: str = "1", op_hour: int = 9,
                          optype: str = "elective",
                          anesthesia: str = "UNKNOWN",  # API compat
                          scrub_nurse: str = "UNKNOWN", # API compat (Main OR ไม่ใช้)
                          circ_nurse: str = "UNKNOWN",  # API compat
                          has_assistant: int = 0,        # API compat
                          wait_min: int = 0,             # API compat
                          op_date: datetime = None,
                          orroom: int = 11,             # NEW: Main OR room (11-17)
                          diagnosis: str = "") -> dict:  # NEW: ICD10 diagnosis
    """
    ทำนายเวลาผ่าตัด — ใช้ predictor v2 (XGBoost + fuzzy + multi-level evidence)

    Return dict ที่ backward-compatible กับ Minor OR API:
      - predicted_min: int นาที (เวลาที่ทำนาย)
      - confidence: 'สูงมาก' / 'สูง' / 'ปานกลาง' / 'ต่ำ'
      - method: คำอธิบายโมเดล
      - details: รายละเอียดเพิ่มเติม
      - proc_n, surg_n: จำนวน similar cases
      - source, tier: backward-compat
    + Fields ใหม่ (v4):
      - predicted_range: (low, high) — ช่วงน่าจะอยู่
      - evidence_levels: list หลักฐานหลายระดับ
      - fuzzy_correction: ถ้ามี auto-correct
    """
    # honest_v1: ทำนายด้วย hier + XGBoost residual (เวลาครองห้อง) เป็นหลัก; fallback v2 ด้านล่าง
    try:
        import or_time_model as _otm
        _det = _otm.predict_detail({
            'procedure_name': procedure, 'surgeon_name': surgeon,
            'division': division, 'orroom': orroom, 'age': age,
            'planned_hour': op_hour, 'diagnosis': diagnosis,
        }, 'room_use')
        _n = _det['n_cases']
        _conf = ('สูงมาก' if _n >= 50 else 'สูง' if _n >= 20
                 else 'ปานกลาง' if _n >= 5 else 'ต่ำ')
        _pm = _det['predicted_min']
        # 📏 ช่วงทำนาย: split conformal (คาลิเบรตจาก hold-out ปี 2567 — coverage 90% จริง)
        #    ไม่มีไฟล์คาลิเบรต → fallback heuristic เดิม (ติดป้ายให้รู้ว่าไม่การันตี)
        _iv90 = _det.get('interval90')
        _iv80 = _det.get('interval80')
        return {
            'predicted_min': _pm, 'confidence': _conf,
            'method': 'มัธยฐานลำดับชั้น + XGBoost residual (honest_v1)',
            'details': 'อิงกลุ่มหัตถการระดับ %s จาก %d เคส' % (_det['level'], _n),
            'proc_n': _n, 'surg_n': 0, 'source': 'honest_v1', 'tier': 1,
            'predicted_range': (tuple(_iv90) if _iv90
                                else (max(5, int(_pm * 0.6)), int(_pm * 1.5))),
            'predicted_range80': tuple(_iv80) if _iv80 else None,
            'range_method': 'conformal' if _iv90 else 'heuristic',
            'range_coverage': 0.90 if _iv90 else None,
            'evidence_levels': [], 'fuzzy_correction': None,
        }
    except Exception as _hx:
        # ⚠️ เดิม except เงียบ — โมเดลหลักล่มแล้ว fallback โดยไม่มีใครรู้ → log ไว้เสมอ
        try:
            from logger_setup import get_logger
            get_logger("core").warning("honest_v1 ใช้ไม่ได้ จะ fallback: %s", _hx)
        except Exception:
            print(f"[core] honest_v1 fallback: {_hx}")

    assets = load_ml_assets()
    now = op_date if op_date else datetime.now()

    # ถ้า predictor โหลดไม่ขึ้น → fallback local DB
    if not assets.get('model_loaded') or assets.get('predictor') is None:
        try:
            from main_or_db import predict_from_local_history
            # 🔁 M-05: ส่งวันผ่าตัดเป็น as_of_date → fallback ใช้เฉพาะเคสก่อนหน้า (กัน leak ตอน backfill)
            local = predict_from_local_history(
                procedure, surgeon,
                as_of_date=(op_date.strftime('%Y-%m-%d') if op_date else None))
            if local is not None:
                return {
                    'predicted_min': local['predicted_min'],
                    'confidence': local['confidence'],
                    'method': local['method_label'],
                    'details': f'median ของ {local["n_cases"]} เคส (local DB)',
                    'proc_n': local['n_cases'],
                    'surg_n': local['n_cases'] if local['tier'] == 1 else 0,
                    'source': 'local_history',
                    'tier': local['tier'],
                }
        except Exception:
            pass
        return {
            'predicted_min': 60, 'confidence': 'ต่ำ',
            'method': 'ค่าเริ่มต้น',
            'details': f'predictor v2 โหลดไม่สำเร็จ: {assets.get("error", "?")}',
            'proc_n': 0, 'surg_n': 0,
            'source': 'default', 'tier': 0,
        }

    predictor = assets['predictor']

    # แปลง division string → int (Minor OR ใช้ "75", Main OR ใช้ 1-86)
    try:
        div_int = int(str(division).strip())
    except (ValueError, TypeError):
        div_int = 1

    # Predict
    try:
        result = predictor.predict(
            procedure_name=procedure or "unknown",
            surgeon_name=surgeon or "unknown",
            division=div_int,
            orroom=int(orroom) if orroom else 11,
            age=int(age) if age else 50,
            planned_hour=int(op_hour) if op_hour else 9,
            opedate=now.strftime("%Y-%m-%d"),
            diagnosis_name=diagnosis or "",
        )
    except Exception as e:
        return {
            'predicted_min': 60, 'confidence': 'ต่ำ',
            'method': 'Predictor error',
            'details': f'predict() error: {str(e)[:60]}',
            'proc_n': 0, 'surg_n': 0,
            'source': 'error', 'tier': 0,
        }

    # Map confidence: predictor v2 → Thai labels (Minor OR API)
    conf_map = {
        'high': 'สูงมาก',
        'medium': 'สูง',
        'low': 'ปานกลาง',
        'very_low': 'ต่ำ',
    }
    confidence_th = conf_map.get(result.confidence_level, 'ปานกลาง')

    # หลักฐานที่ใช้
    best = result.best_evidence
    n_evidence = best.n_cases if best else 0
    evidence_name = best.level_name if best else 'global'

    # ลักษณะ method label
    method = f'AI XGBoost ({evidence_name})'

    # Details — รวม info สำคัญ
    detail_parts = [confidence_th]
    detail_parts.append(f'อ้างอิง {n_evidence} เคส')
    if best:
        detail_parts.append(f'median={best.median:.0f}m IQR[{best.q1:.0f}-{best.q3:.0f}]')
    if result.fuzzy_procedure:
        fp = result.fuzzy_procedure
        detail_parts.append(f'auto-correct: {fp["matched_name"][:25]} ({fp["similarity"]}%)')
    if result.fuzzy_surgeon:
        fs = result.fuzzy_surgeon
        detail_parts.append(f'surg→{fs["matched_name"][:20]} ({fs["similarity"]}%)')

    # tier (legacy compat): 1 = narrow, 2 = medium, 3 = broad
    tier_map = {'narrow': 1, 'medium': 2, 'broad': 3}
    tier = tier_map.get(best.granularity if best else 'broad', 3)

    return {
        'predicted_min': max(5, int(round(result.predicted_minutes))),
        'confidence': confidence_th,
        'method': method,
        'details': ' | '.join(detail_parts),
        'proc_n': n_evidence,
        'surg_n': n_evidence,
        'surg_proc_n': n_evidence,
        'source': 'ml_v7',
        'tier': tier,
        # ─── v4 fields ───
        'predicted_range': result.predicted_range,
        'evidence_levels': [
            {
                'level': e.level_name,
                'granularity': e.granularity,
                'n': e.n_cases,
                'median': e.median,
                'q1': e.q1, 'q3': e.q3,
            }
            for e in result.evidence_levels
        ],
        'best_evidence': {
            'level': best.level_name if best else None,
            'granularity': best.granularity if best else None,
            'n': n_evidence,
            'median': best.median if best else None,
            'q1': best.q1 if best else None,
            'q3': best.q3 if best else None,
        },
        'fuzzy_procedure': result.fuzzy_procedure,
        'fuzzy_surgeon': result.fuzzy_surgeon,
        'notes': result.notes,
    }

# ============================================================================
# HELPERS
# ============================================================================

def parse_opetime_full(val) -> tuple:
    try:
        t = int(float(val))
        return (t // 10000, (t % 10000) // 100)
    except:
        return (8, 0)

def parse_opetime(val) -> int:
    try:
        return int(float(val)) // 10000
    except:
        return 8

# ============================================================================
# PERSISTENT CASE HISTORY (for Top 5/10 statistics)
# ============================================================================

HISTORY_FILE = os.path.join(_SCRIPT_DIR, 'case_history.csv')

HISTORY_COLUMNS = [
    'timestamp', 'case_id', 'procedure', 'surgeon', 'division',
    'age', 'op_hour', 'scrub', 'circ',
    'ai_predicted_min', 'user_override_min', 'actual_duration_min',
    'abs_error', 'signed_error', 'wait_min', 'room',
]

def load_case_history() -> pd.DataFrame:
    """Load persistent case history CSV (returns empty DF if missing)."""
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    try:
        df = pd.read_csv(HISTORY_FILE, encoding='utf-8-sig')
        for col in HISTORY_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception as e:
        print(f"Warning: cannot read history: {e}")
        return pd.DataFrame(columns=HISTORY_COLUMNS)

def append_case_history(record: dict) -> bool:
    """Append one completed case to persistent CSV. Computes errors automatically."""
    try:
        ai = record.get('ai_predicted_min')
        actual = record.get('actual_duration_min')
        if ai is not None and actual is not None:
            record['signed_error'] = actual - ai
            record['abs_error'] = abs(actual - ai)
        row = {c: record.get(c) for c in HISTORY_COLUMNS}
        df_new = pd.DataFrame([row])
        header = not os.path.exists(HISTORY_FILE)
        df_new.to_csv(HISTORY_FILE, mode='a', header=header,
                      index=False, encoding='utf-8-sig')
        return True
    except Exception as e:
        print(f"Warning: cannot append history: {e}")
        return False


def remove_last_case_history(case_id, procedure) -> bool:
    """ลบแถวล่าสุดของเคสนี้ออกจาก CSV history — ใช้ตอน undo 'ผ่าเสร็จ'
    (จับคู่ case_id + procedure แล้วลบเฉพาะแถวสุดท้ายที่ตรง — แถวอื่นไม่แตะ)"""
    try:
        if not os.path.exists(HISTORY_FILE):
            return False
        df = pd.read_csv(HISTORY_FILE, encoding='utf-8-sig')
        if df.empty:
            return False
        m = ((df.get('case_id').astype(str) == str(case_id))
             & (df.get('procedure').astype(str) == str(procedure)))
        idxs = df.index[m]
        if len(idxs) == 0:
            return False
        df = df.drop(idxs[-1])
        df.to_csv(HISTORY_FILE, index=False, encoding='utf-8-sig')
        return True
    except Exception as e:
        print(f"Warning: cannot remove history row: {e}")
        return False

def top_n_procedures(df: pd.DataFrame, by: str = 'volume', n: int = 10) -> pd.DataFrame:
    """by = 'volume' | 'avg_duration' | 'mae' | 'bias'"""
    if df.empty:
        return pd.DataFrame()
    g = df.groupby('procedure').agg(
        n_cases=('procedure', 'size'),
        avg_duration=('actual_duration_min', 'mean'),
        median_duration=('actual_duration_min', 'median'),
        mae=('abs_error', 'mean'),
        bias=('signed_error', 'mean'),
    ).reset_index()
    g = g[g['n_cases'] >= 1]
    sort_key = {'volume': 'n_cases', 'avg_duration': 'avg_duration',
                'mae': 'mae', 'bias': 'bias'}.get(by, 'n_cases')
    ascending = (by == 'mae')
    return g.sort_values(sort_key, ascending=ascending).head(n).round(1)

def top_n_surgeons(df: pd.DataFrame, by: str = 'volume', n: int = 10) -> pd.DataFrame:
    """by = 'volume' | 'avg_duration' | 'mae'"""
    if df.empty:
        return pd.DataFrame()
    g = df.groupby('surgeon').agg(
        n_cases=('surgeon', 'size'),
        avg_duration=('actual_duration_min', 'mean'),
        mae=('abs_error', 'mean'),
    ).reset_index()
    sort_key = {'volume': 'n_cases', 'avg_duration': 'avg_duration',
                'mae': 'mae'}.get(by, 'n_cases')
    ascending = (by == 'mae')
    return g.sort_values(sort_key, ascending=ascending).head(n).round(1)

def top_n_surg_proc(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top surgeon x procedure combos by volume."""
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(['surgeon', 'procedure']).agg(
        n_cases=('procedure', 'size'),
        avg_duration=('actual_duration_min', 'mean'),
        mae=('abs_error', 'mean'),
    ).reset_index()
    return g.sort_values('n_cases', ascending=False).head(n).round(1)

def top_n_nurses(df: pd.DataFrame, role: str = 'scrub', n: int = 10) -> pd.DataFrame:
    """role = 'scrub' | 'circ'"""
    if df.empty or role not in df.columns:
        return pd.DataFrame()
    g = df.groupby(role).agg(
        n_cases=(role, 'size'),
        avg_duration=('actual_duration_min', 'mean'),
    ).reset_index()
    g = g[g[role].notna() & (g[role].astype(str).str.strip() != '')]
    return g.sort_values('n_cases', ascending=False).head(n).round(1)

# ============================================================================
# SESSION STATE
# ============================================================================

def init_session_state():
    if 'patient_cases' not in st.session_state:
        st.session_state.patient_cases = []
    if 'my_room' not in st.session_state:
        st.session_state.my_room = 'หัวหน้า (ทุกห้อง)'
    if 'or_rooms' not in st.session_state:
        _room_tpl = lambda name, spec: {
            'status': 'ว่าง', 'current_case': None, 'start_time': None,
            'predicted_time': None, 'override_time': None, 'is_emergency': False,
            'staff': {'scrub': '', 'circulating': ''},
            'name': name, 'specialty': spec,
        }
        # ✅ ใช้ห้องจริงตึกใหม่จาก room_config (single source of truth — 90-98)
        #    เดิม hardcode 11-17 (รหัสตึกเก่า) → state ค้างไม่ตรงห้องจริง และทำให้
        #    การ restore room_settings จาก DB ตอนบูตถูกข้าม (key ไม่ตรงกัน)
        from room_config import NEW_BUILDING_ROOMS as _RC_ROOMS, \
            ROOM_INFO as _RC_INFO, SPECIALTY_FULL as _RC_SPEC
        st.session_state.or_rooms = {
            r: _room_tpl(_RC_INFO[r][0],
                         _RC_SPEC.get(_RC_INFO[r][1], _RC_INFO[r][1]))
            for r in _RC_ROOMS}
    if 'statistics' not in st.session_state:
        st.session_state.statistics = {
            'total_cases': 0, 'completed_cases': 0, 'cancelled_cases': 0,
            'case_history': [], 'predictions_history': []
        }
    if 'room_settings' not in st.session_state:
        _empty_scrub = ['', '']
        _empty_circ = ['', '', '', '']
        # ✅ ห้องตึกใหม่จาก room_config (เดิม hardcode 11-17 ตึกเก่า — ดูคอมเมนต์ or_rooms)
        from room_config import NEW_BUILDING_ROOMS as _RC_ROOMS, \
            ROOM_INFO as _RC_INFO, SPECIALTY_FULL as _RC_SPEC
        st.session_state.room_settings = {
            r: {'enabled': True, 'name': _RC_INFO[r][0],
                'specialty': _RC_SPEC.get(_RC_INFO[r][1], _RC_INFO[r][1]),
                'scrub': list(_empty_scrub), 'circ': list(_empty_circ), 'nurses': []}
            for r in _RC_ROOMS
        }
    if 'uploaded_cases' not in st.session_state:
        st.session_state.uploaded_cases = []
    if 'schedule' not in st.session_state:
        st.session_state.schedule = []
