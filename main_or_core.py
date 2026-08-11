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

# ════════════════════════════════════════════════════════════════════════════
# 🩺 เฝ้าดูว่า AI ยังทำงานด้วยโมเดลจริงอยู่ไหม (11 ส.ค. 2026 · ตรวจระบบข้อ 7)
# ────────────────────────────────────────────────────────────────────────────
# ความเสี่ยงที่รู้อยู่แล้ว: ไฟล์โมเดลเป็น pickle + requirements ไม่ pin แน่น
# (ดูหัว requirements.txt) พอ Streamlit Cloud อัป xgboost/sklearn ข้ามรุ่น
# โมเดลจะโหลดไม่ขึ้น แล้วระบบ "ตกบันได" ไปชั้น fallback อย่างเงียบเชิง
# ชั้นสุดท้ายคือค่าคงที่ 60 นาที ซึ่งใช้ตัดสินใจจริงบนบอร์ดไม่ได้เลย
#
# เดิมป้องกันด้วย "คนต้องจำไปดูชิป AI หลัง deploy ทุกครั้ง" ซึ่งลืมได้
# ตรงนี้จึงนับให้เอง: ทำนายไปกี่ครั้ง มาจากชั้นไหนบ้าง แล้วให้หน้าผู้วิจัยเตือน
# ⛔ ตัวนับอยู่ในหน่วยความจำของ process ไม่แตะ DB และไม่มีข้อมูลผู้ป่วยใด ๆ
#    (แอปรีสตาร์ท = เริ่มนับใหม่ ตั้งใจให้เป็นสัญญาณของ "ตอนนี้" ไม่ใช่สถิติสะสม)
# ════════════════════════════════════════════════════════════════════════════
_PRED_TALLY: dict = {}
_PRED_HEALTHY_SOURCE = 'thesis_ML_v2'   # ชั้นเดียวที่ถือว่า "ปกติ"


def _tally_prediction(source: str) -> None:
    try:
        _PRED_TALLY[source] = _PRED_TALLY.get(source, 0) + 1
    except Exception:
        pass


def prediction_health() -> dict:
    """สรุปสุขภาพสายการทำนายของ process นี้
    คืน {'total', 'by_source', 'fallback_n', 'fallback_pct', 'alert', 'message'}
    total = 0 (ยังไม่เคยทำนาย) → alert=False เสมอ ไม่เดาแทนข้อมูลที่ไม่มี"""
    _by = dict(_PRED_TALLY)
    _total = sum(_by.values())
    _fb = _total - _by.get(_PRED_HEALTHY_SOURCE, 0)
    _pct = (100.0 * _fb / _total) if _total else 0.0
    # เกณฑ์: ต้องมีตัวอย่างพอ (≥20 ครั้ง) และ fallback เกิน 10% ถึงจะเตือน
    # (ทำนายไม่กี่ครั้งแล้วพลาด 1 ครั้ง = 50% ซึ่งไม่ได้แปลว่าระบบพัง)
    _alert = _total >= 20 and _pct > 10.0
    _msg = ''
    if _alert:
        _worst = 'ค่าเริ่มต้น 60 นาที' if _by.get('default') else 'โมเดลสำรอง'
        _msg = (f"⛔ AI ไม่ได้ใช้โมเดลหลัก (thesis_ML_v2) ใน {_pct:.0f}% "
                f"ของการทำนายล่าสุด ({_fb} จาก {_total} ครั้ง) : ตกไปใช้{_worst} "
                f"ตรวจว่าไฟล์โมเดลโหลดขึ้นหรือไม่ (ดูชิป AI บนหัวแอป) "
                f"ก่อนนำผลช่วงนี้ไปใช้ในงานวิจัย")
    return {'total': _total, 'by_source': _by, 'fallback_n': _fb,
            'fallback_pct': round(_pct, 1), 'alert': _alert, 'message': _msg}


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
                          ward: str = "",                # NEW: ward (ว่าง = OPD) — v2 ใช้แยก IPD/OPD
                          asa: str = None,               # 💉 จากไฟล์ preop วิสัญญี (19 ก.ค. 2026)
                          bmi: float = None,
                          sex: str = None,
                          planicu: str = None,
                          blood: str = None) -> dict:
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
            _case_in = {
                'procedure': procedure, 'diagnosis': diagnosis,
                'surgeon': surgeon, 'division': division, 'age': age,
                'ward': ward,       # ว่าง = OPD · มีค่า = IPD (feature is_inpatient)
            }
            # 💉 feature จาก preop วิสัญญี — ส่งเฉพาะที่มี (predictor เติม Unknown/median เอง)
            for _k, _v in (('ASA', asa), ('BMI', bmi), ('sex', sex),
                           ('planicu', planicu), ('blood', blood)):
                if _v is not None:
                    _case_in[_k] = _v
            _r2 = _mv2.predict_case(_case_in)
            _pn2 = int(_r2.get('proc_n') or 0)
            _tally_prediction('thesis_ML_v2')
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
        _tally_prediction('thesis_ML')
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
            _tally_prediction('local_history')
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
    except Exception as _lx:
        # ⚠️ เดิม except เงียบ (ตรวจระบบข้อ 9) — ชั้นสุดท้ายก่อนค่าเริ่มต้น 60 นาที
        #    ล้มแล้วไม่มีใครรู้เลย ต้องได้ยินเสียงเสมอ
        try:
            from logger_setup import get_logger
            get_logger("core").warning("predict_from_local_history ใช้ไม่ได้: %s", _lx)
        except Exception:
            print(f"[core] local_history fallback: {_lx}")
    _tally_prediction('default')
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


# ════════════════════════════════════════════════════════════════════════════
# ✏️ ตรวจค่าที่คนแก้เวลาก่อนบันทึก (11 ส.ค. 2026 · ผลการตรวจระบบข้อ 8)
# ────────────────────────────────────────────────────────────────────────────
# ช่องแก้เวลารับ 5-600 นาทีโดยไม่ทักท้วงอะไรเลย พิมพ์ 300 แทน 30 ระบบรับทันที
# แล้วค่านั้น "ชนะ AI" บนบอร์ด (effective_min) → ห้องถัดไปถูกกันไว้ยาวเกินจริง
# ซ้ำร้ายค่าผิดไหลลง override_log ซึ่งเป็นข้อมูลวิจัย human-AI collaboration
#
# เกณฑ์: ต่างจาก AI ตั้งแต่ 2.5 เท่าขึ้นไป "และ" ห่างกันเกิน 60 นาที
# (บังคับสองเงื่อนไขพร้อมกัน เพราะเคสสั้น ๆ 10→25 นาทีเป็น 2.5 เท่าก็จริง
#  แต่เป็นเรื่องปกติมากหน้างาน ถ้าเตือนด้วยจะกลายเป็นเตือนหมาป่า คนกดผ่านโดยไม่อ่าน)
# ════════════════════════════════════════════════════════════════════════════
_OV_RATIO_HI = 2.5
_OV_RATIO_LO = 0.4
_OV_MIN_GAP = 60


def override_sanity_warning(new_min, ai_min):
    """คืนข้อความเตือนถ้าค่าที่กรอกต่างจาก AI มากผิดปกติ · คืน '' ถ้าปกติ
    ไม่รู้ค่า AI = ไม่เตือน (ไม่มีอะไรให้เทียบ อย่าเดา)"""
    try:
        new_v = int(new_min)
        ai_v = int(ai_min) if ai_min else 0
    except (TypeError, ValueError):
        return ''
    if ai_v <= 0 or new_v <= 0:
        return ''
    if abs(new_v - ai_v) < _OV_MIN_GAP:
        return ''
    if new_v >= ai_v * _OV_RATIO_HI:
        return (f"⚠️ {new_v} นาที มากกว่าที่ AI ทำนายไว้ ({ai_v} นาที) "
                f"ราว {new_v / ai_v:.1f} เท่า : พิมพ์เกินหลักหรือเปล่า "
                f"ถ้าตั้งใจแบบนี้ กด 💾 บันทึก อีกครั้งเพื่อยืนยัน")
    if new_v <= ai_v * _OV_RATIO_LO:
        return (f"⚠️ {new_v} นาที น้อยกว่าที่ AI ทำนายไว้ ({ai_v} นาที) มาก : "
                f"ตรวจอีกครั้งว่าใส่ถูกช่อง ถ้าตั้งใจแบบนี้ "
                f"กด 💾 บันทึก อีกครั้งเพื่อยืนยัน")
    return ''
