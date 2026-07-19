"""
Main OR Core — เครื่องทำนายเวลาผ่าตัดของบอร์ด
ตัวหลัก: thesis_ML (or_time_model — hierarchical median + XGBoost residual + conformal)
fallback: ค่ากลางจากประวัติใน DB → ค่าเริ่มต้น
(ชั้น SurgicalTimePredictor เก่าถูกถอดออก 4 ก.ค. 2026 — ดู git history ถ้าต้องการคืน)
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
# ⚡ rerun_board — rerun ให้ "แคบที่สุด" (perf fix ก.ค. 2026)
# ถ้าโค้ดกำลังรันอยู่ใน st.fragment → rerun เฉพาะ fragment นั้น (บอร์ดขยับ
# แต่ CSS/เมนู/หน้าอื่นไม่ต้องวิ่งใหม่) · นอก fragment / streamlit เก่า → rerun ปกติ
# ============================================================================

def rerun_board():
    """st.rerun แบบ scope แคบสุดที่รุ่น streamlit รองรับ — ใช้แทน st.rerun()
    ในทุก action ของ OR Board (ปุ่มรับเข้า/เข้าห้อง/ผ่าเสร็จ/undo/แก้เวลา ฯลฯ)
    🐛 fix 6 ก.ค. 2026: scope="fragment" ใช้ได้เฉพาะ "fragment rerun" จริง ๆ —
    ถ้าปุ่มถูกกดในจังหวะ full run (เช่น เพิ่งเปิดหน้า) ต้องถอยเป็น rerun เต็ม"""
    _in_frag = False
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        _ctx = get_script_run_ctx()
        # ต้องเป็น fragment rerun จริง (fragment_ids_this_run ไม่ว่าง) ไม่ใช่แค่
        # "โค้ดอยู่ใน fragment" — full run แรกของหน้า render fragment ด้วยแต่ขอ scope ไม่ได้
        _in_frag = (bool(getattr(_ctx, 'current_fragment_id', None))
                    and bool(getattr(_ctx, 'fragment_ids_this_run', None)))
    except Exception:
        _in_frag = False
    if _in_frag:
        try:
            st.rerun(scope="fragment")
            return
        except TypeError:               # streamlit เก่า: ไม่มี kwarg scope
            pass
        except Exception as _e:         # กันเหนียว: StreamlitAPIException ตอน full run
            if type(_e).__name__ == 'RerunException':
                raise                   # rerun สำเร็จ — ปล่อย control flow ผ่าน
            print(f"[rerun_board] fragment scope ใช้ไม่ได้ → rerun เต็ม: {_e}")
    st.rerun()


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
                          diagnosis: str = "",           # NEW: ICD10 diagnosis
                          ward: str = "") -> dict:       # NEW: ward (ว่าง = OPD) — v2 ใช้แยก IPD/OPD
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
    # 🥇 thesis_ML_v2 (โมเดลเล่ม 13 features) — โปรโมตขึ้นตัวหลัก 7 ก.ค. 2026 ตามคำสั่งมุคกี้
    #    (บอร์ดโชว์ v2 · thesis_ML ย้ายไปทำนายเงียบใน shadow_v2_log — การเทียบไม่ขาดตอน)
    try:
        from shadow_v2 import _get_model as _get_v2
        _mv2 = _get_v2()
        if _mv2 is not None:
            _r2 = _mv2.predict_case({
                'procedure': procedure, 'diagnosis': diagnosis,
                'surgeon': surgeon, 'division': division, 'age': age,
                'ward': ward,       # ว่าง = OPD · มีค่า = IPD (feature is_inpatient)
            })
            _pn2 = int(_r2.get('proc_n') or 0)
            return {
                'predicted_min': int(_r2['predicted_min']),
                'confidence': _r2.get('confidence', 'ปานกลาง'),
                'method': 'General XGBoost 13 features (thesis_ML_v2 — โมเดลวิทยานิพนธ์)',
                'details': f'จาก {_pn2} เคสใกล้เคียง' if _pn2 else 'ไม่มีเคสใกล้เคียง (ใช้ค่ากลาง)',
                'proc_n': _pn2, 'surg_n': 0, 'source': 'thesis_ML_v2', 'tier': 1,
                'predicted_range': tuple(_r2.get('range90') or ()) or None,
                'predicted_range80': None,
                'range_method': 'conformal' if _r2.get('range90') else None,
                'range_coverage': 0.90 if _r2.get('range90') else None,
                'evidence_levels': [], 'fuzzy_correction': None,
            }
    except Exception as _vx:
        try:
            from logger_setup import get_logger
            get_logger("core").warning("thesis_ML_v2 ใช้ไม่ได้ จะ fallback thesis_ML: %s", _vx)
        except Exception:
            print(f"[core] thesis_ML_v2 fallback: {_vx}")

    # 🥈 thesis_ML: fallback ชั้นสอง (และยังทำนายเงียบใน shadow เพื่อเทียบต่อเนื่อง)
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
            'method': 'มัธยฐานลำดับชั้น + XGBoost residual (thesis_ML)',
            'details': 'อิงกลุ่มหัตถการระดับ %s จาก %d เคส' % (_det['level'], _n),
            'proc_n': _n, 'surg_n': 0, 'source': 'thesis_ML', 'tier': 1,
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
            get_logger("core").warning("thesis_ML ใช้ไม่ได้ จะ fallback: %s", _hx)
        except Exception:
            print(f"[core] thesis_ML fallback: {_hx}")

    # 🧯 Fallback 2 ชั้น (thesis_ML ใช้ไม่ได้): ค่ากลางจากประวัติใน DB → ค่าเริ่มต้น
    # (ชั้น SurgicalTimePredictor เก่าถูกถอด 4 ก.ค. 2026 — บน cloud มันไม่เคยทำงาน
    #  อยู่แล้วเพราะ pkl ถูก gitignore · เหลือ 2 ชั้น = พฤติกรรม local ตรงกับ cloud เป๊ะ)
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
        'details': 'thesis_ML และประวัติ local ใช้ไม่ได้ — ใช้ค่าเริ่มต้น 60 นาที (ควรตรวจ ✏️)',
        'proc_n': 0, 'surg_n': 0,
        'source': 'default', 'tier': 0,
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
