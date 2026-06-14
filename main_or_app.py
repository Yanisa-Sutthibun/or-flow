"""
General Surgery Management Dashboard - Trial Version
ระบบจัดการห้องผ่าตัดศัลยกรรมทั่วไป — AI ทำนายเวลาผ่าตัด
โครงสร้าง UI เหมือน pro09.py (ห้องผ่าตัดศัลยกรรมทั่วไป)

Author: Mukky — Master's Thesis, Nursing Administration
Institution: Chulalongkorn University
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
from collections import defaultdict
import uuid

from main_or_core import (
    init_session_state, load_ml_assets, predict_surgical_time,
    parse_opetime_full, parse_opetime,
    TURNOVER_MINOR, WORK_START, WORK_END, WORK_MINUTES
)
# หมายเหตุ: page_statistics (main_or_pages) และ page_tracking (main_or_tracking)
# ไม่ถูก route ใน sidebar แล้ว — ตัด import ออกเพื่อลดเวลาโหลด/ความสับสน
# (โค้ดหน้าเหล่านั้นยังอยู่ในไฟล์เดิม เผื่อเรียกคืนในอนาคต)
from main_or_pages import page_or_board
from main_or_admin import page_admin
from main_or_db import init_db, get_db_stats, save_room_settings, load_room_settings

# ────────────────────────────────────────────────────────────────────
# ดึงรายชื่อพยาบาลจริง จาก intraopปี69.xls (nursurgnm + nurcircunm)
# ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_real_nurse_list():
    """ดึงรายชื่อพยาบาลที่เคยทำงานในห้องผ่าตัดศัลยกรรม จากไฟล์ intraop ปี 69
    คอลัมน์ nursurgnm (Scrub) + nurcircunm (Circulating)
    Return: sorted list of unique nurse names
    """
    import re, json
    from pathlib import Path

    # 1) อ่านจาก Supabase ก่อน (เก็บใน DB — ไม่อยู่ใน repo สาธารณะ ตรงนโยบาย PDPA)
    #    populate ด้วย populate_nurse_list.py (ตัดยศแล้ว เหลือ ชื่อ-นามสกุล)
    try:
        from main_or_db import _get_app_setting
        _raw = _get_app_setting('or_nurse_list_69', '')
        if _raw:
            _lst = json.loads(_raw)
            if isinstance(_lst, list) and _lst:
                return _lst
    except Exception:
        pass

    # 2) fallback (เครื่อง local dev): อ่านจากไฟล์ intraop ปี 69 ตรงๆ (ไฟล์นี้ไม่ commit ขึ้น cloud)
    base = Path(__file__).resolve().parent
    candidates = [
        base / "data" / "year69" / "intraopปี69.xls",
        base.parent / "thesis_main_OR" / "data_for_train" / "year69" / "intraopปี69.xls",
    ]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        return []
    try:
        df = pd.read_excel(src, usecols=["nursurgnm", "nurcircunm"])
    except Exception:
        return []

    # คำขึ้นต้นที่ไม่ใช่พยาบาล (data entry ผิด — แพทย์ปนมา)
    NON_NURSE_PREFIXES = ("แพทย์หญิง", "นายแพทย์", "นพ.", "พญ.")
    CIVIL_TITLES = ("นางสาว", "นาง", "นาย", "ด.ช.", "ด.ญ.", "น.ส.")

    def _strip_rank(name):
        """ตัดยศ/คำนำหน้า เหลือ ชื่อ-นามสกุล (เช่น 'พ.ต.ท.หญิงกนกวรรณ มีแก้ว' -> 'กนกวรรณ มีแก้ว')"""
        s = name.strip()
        s = re.sub(r'^ว่าที่\s*', '', s)   # ตัด 'ว่าที่' นำหน้ายศ
        for t in CIVIL_TITLES:
            if s.startswith(t):
                s = s[len(t):]
                break
        else:
            m = re.match(r'^((?:[ก-ฮ]{1,2}\.)+)', s)   # ยศตำรวจ เช่น พ.ต.ท. จ.ส.ต. ด.ต.
            if m:
                s = s[m.end():]
        return re.sub(r'^(หญิง|ชาย)\s*', '', s).strip()

    nurses = set()
    for col in ["nursurgnm", "nurcircunm"]:
        if col not in df.columns:
            continue
        for v in df[col].dropna():
            for n in re.split(r"[,\r\n]+", str(v)):
                n = n.strip()
                if not n or len(n) <= 2:
                    continue
                if any(n.startswith(p) for p in NON_NURSE_PREFIXES):
                    continue
                nm = _strip_rank(n)
                if len(nm) > 2:
                    nurses.add(nm)
    return sorted(nurses)

# ============================================================================
# PAGE CONFIG & CSS
# ============================================================================

st.set_page_config(
    page_title="ห้องผ่าตัดศัลยกรรมทั่วไป Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700&display=swap');
    * { font-family: 'Sarabun', sans-serif; }

    /* ─── ซ่อนเฉพาะ Streamlit toolbar/menu/deploy (ปลอดภัย ไม่กระทบ content) ─── */
    #MainMenu { visibility: hidden; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDeployButton"] { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }

    .card { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 12px; padding: 20px; margin: 10px 0; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-left: 5px solid #3498db; }
    .card-waiting { background: linear-gradient(135deg, #fff9e6 0%, #ffe680 100%); border-left-color: #f1c40f; }
    .card-inor { background: linear-gradient(135deg, #e3f2fd 0%, #90caf9 100%); border-left-color: #2196f3; }
    .card-recovery { background: linear-gradient(135deg, #e8f5e9 0%, #81c784 100%); border-left-color: #4caf50; }
    .card-emergency { background: linear-gradient(135deg, #ffebee 0%, #ef5350 100%); border-left-color: #f44336; border: 2px solid #f44336; }
    .or-room-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; min-height: 300px; border-top: 4px solid #3498db; }
    .or-room-empty { border-top-color: #95a5a6; background: linear-gradient(135deg, #ecf0f1 0%, #bdc3c7 100%); }
    .or-room-active { border-top-color: #2196f3; background: linear-gradient(135deg, #e3f2fd 0%, #e1f5fe 100%); }
    .timer { font-size: 32px; font-weight: bold; color: #e74c3c; font-family: 'Courier New', monospace; }
    .metric-box { background: white; border-radius: 12px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
    .stat-title { color: #7f8c8d; font-size: 14px; font-weight: 600; margin-bottom: 10px; }
    .stat-value { color: #2c3e50; font-size: 32px; font-weight: bold; }
    .header-title { color: #2c3e50; font-size: 28px; font-weight: 700; margin-bottom: 20px; }
    .subheader { color: #34495e; font-size: 18px; font-weight: 600; margin-top: 20px; margin-bottom: 15px; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Inject central enterprise theme
try:
    from ui_theme import inject_theme as _inject_theme
    _inject_theme()
except Exception:
    pass

# --- Auto-refresh ทุก 30 นาที ---
# (เดิมใช้ <script> ผ่าน st.markdown ซึ่ง "ไม่ทำงานจริง" — Streamlit ไม่ execute
#  script ที่ inject ทาง markdown · เปลี่ยนเป็น streamlit_autorefresh ที่มีใน requirements)
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30 * 60 * 1000, key="_app_autorefresh_30min")
except Exception:
    pass  # ไม่มี package → ข้าม (ผู้ใช้กดปุ่ม 🔄 รีเฟรชเองได้)

init_session_state()

# Restore room settings from DB on first load (fix #1: persist across restarts)
if not st.session_state.get('_room_settings_loaded'):
    try:
        db_settings = load_room_settings()
        for rm_no, data in db_settings.items():
            if rm_no in st.session_state.room_settings:
                st.session_state.room_settings[rm_no]['enabled'] = data['enabled']
                st.session_state.room_settings[rm_no]['scrub'] = data['scrub']
                st.session_state.room_settings[rm_no]['circ'] = data['circ']
                st.session_state.room_settings[rm_no]['nurses'] = [n for n in data['scrub'] + data['circ'] if n]
    except Exception:
        pass
    st.session_state['_room_settings_loaded'] = True

# ============================================================================
# PAGE 1: ROOM SETTINGS
# ============================================================================

def render_system_status():
    """🤖 กล่องสถานะโมเดล AI (honest_v1) — อ่านจาก artifact จริง · เอาแค่กล่องนี้พอ"""
    try:
        import json as _json
        from pathlib import Path as _Path
        _hdir = _Path(__file__).resolve().parent / 'models' / 'honest_v1'
        _honest_ok = ((_hdir / 'hier_room_use.json').exists()
                      and (_hdir / 'resid_room_use.pkl').exists())
        _meta_h = (_json.loads((_hdir / 'meta.json').read_text(encoding='utf-8'))
                   if (_hdir / 'meta.json').exists() else {})
        import or_time_model as _otm_info
        _cinfo = _otm_info.conformal_info('room_use')
    except Exception:
        _honest_ok, _meta_h, _cinfo = False, {}, {}
    if _honest_ok:
        _ntr = (_meta_h.get('room_use') or {}).get('n_train', '—')
        _hl = _cinfo.get('headline') or {}
        _q90 = (_cinfo.get('q') or {}).get('0.90')
        _rng_txt = (f'ช่วงทำนาย 90%: ±{_q90:.0f} นาที (split conformal)'
                    if _q90 else 'ช่วงทำนาย: ยังไม่คาลิเบรต')
        st.markdown(
            f'<div style="background:#e8f5e9;padding:8px;border-radius:8px;text-align:center;">'
            f'<p style="margin:0;font-size:11px;color:#2e7d32;">'
            f'🤖 <b>AI Model: honest_v1</b> (ตัวที่ทำนายบนบอร์ด)<br>'
            f'มัธยฐานลำดับชั้น + XGBoost residual<br>'
            f'เทรน {_ntr} เคส (พ.ศ. 2564–2567)<br>'
            f'MAE {_hl.get("mae", "—")} นาที · ±15 นาที {_hl.get("within15_pct", "—")}% '
            f'(ทดสอบปี 2567)<br>{_rng_txt}'
            f'</p></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="background:#ffebee;padding:8px;border-radius:8px;text-align:center;">'
            '<p style="margin:0;font-size:11px;color:#c62828;">'
            '⚠️ <b>ไม่พบโมเดล honest_v1</b><br>'
            'ตรวจ models/honest_v1/ (hier_*.json + resid_*.pkl)<br>'
            'ระบบจะ fallback เป็นค่ามัธยฐานจากฐานข้อมูล</p></div>',
            unsafe_allow_html=True,
        )


def page_room_settings():
    # ห้องผ่าตัดศัลยกรรมตึกใหม่ (1 มี.ค. 69) — 8 ห้อง อ้างตาม OR_mapping_reference
    ROOM_INFO = {
        90: {'label': 'OR1 — ส่องกล้อง (SCOPE)',        'desc': 'ห้องผ่าตัดส่องกล้อง'},
        91: {'label': 'OR2 — ฉุกเฉิน (EM) 🚨',          'desc': 'ห้องรับเคสฉุกเฉิน 24 ชม.'},
        92: {'label': 'OR3 — ทางเดินปัสสาวะ (URO)',     'desc': 'ห้องผ่าตัดระบบทางเดินปัสสาวะ'},
        93: {'label': 'OR4 — ศัลย์ทั่วไป (GEN)',        'desc': 'ห้องผ่าตัดศัลยกรรมทั่วไป'},
        94: {'label': 'OR5 — หลอดเลือด (VAS)',          'desc': 'ห้องผ่าตัดหลอดเลือด'},
        95: {'label': 'OR6 — ประสาท/สมอง (NEURO)',     'desc': 'ห้องผ่าตัดประสาทศัลยศาสตร์'},
        96: {'label': 'OR7 — ตกแต่ง (PLASTIC)',         'desc': 'ห้องศัลยกรรมตกแต่ง'},
        97: {'label': 'OR8 — หู คอ จมูก (ENT)',         'desc': 'ห้องผ่าตัด ENT'},
    }
    ROOM_LIST = list(ROOM_INFO.keys())

    # page header — slim
    st.caption('เปิด/ปิด ห้องผ่าตัดที่ใช้งานวันนี้ — ห้องที่ปิดจะไม่แสดงบนบอร์ด')

    all_inputs = {}

    for rm in ROOM_LIST:
        info = ROOM_INFO[rm]
        # Ensure room exists in session state
        if rm not in st.session_state.room_settings:
            st.session_state.room_settings[rm] = {
                'enabled': True, 'name': info['label'].split(' — ')[0],
                'specialty': info['desc'], 'scrub': ['', ''], 'circ': ['', '', '', ''],
                'nurses': [],
            }
        settings = st.session_state.room_settings[rm]
        if rm not in st.session_state.or_rooms:
            st.session_state.or_rooms[rm] = {
                'status': 'ว่าง', 'current_case': None, 'start_time': None,
                'predicted_time': None, 'override_time': None, 'is_emergency': False,
                'staff': {'scrub': '', 'circulating': ''},
                'name': info['label'].split(' — ')[0], 'specialty': info['desc'],
            }

        _c1, _c2 = st.columns([4, 1])
        with _c1:
            st.markdown(
                f'<div style="background:#f8f9fa;padding:10px 16px;border-radius:10px;'
                f'border-left:4px solid #3498db;"><b>{info["label"]}</b><br>'
                f'<span style="color:#7f8c8d;font-size:12px;">{info["desc"]}</span></div>',
                unsafe_allow_html=True)
        with _c2:
            enabled = st.toggle("เปิดใช้งาน", value=settings.get('enabled', True),
                                key=f"toggle_room_{rm}")
        all_inputs[rm] = {'enabled': enabled}

    if st.button("💾 บันทึกการตั้งค่า", type="primary", use_container_width=True):
        for rm, room_inputs in all_inputs.items():
            settings = st.session_state.room_settings[rm]
            room = st.session_state.or_rooms[rm]
            settings['enabled'] = room_inputs['enabled']
            if room_inputs['enabled']:
                if room['status'] == 'ปิด':
                    room['status'] = 'ว่าง'
            else:
                room['status'] = 'ปิด'
            # คงค่าพยาบาลเดิมไว้ใน DB (UI ตอนนี้ตั้งแค่ เปิด/ปิด ห้อง — dropdown พยาบาลถูกซ่อนชั่วคราว)
            _scrub = settings.get('scrub') if isinstance(settings.get('scrub'), list) else ['', '']
            _circ = settings.get('circ') if isinstance(settings.get('circ'), list) else ['', '', '', '']
            save_room_settings(rm, settings['enabled'], _scrub, _circ)
        st.success("✅ บันทึกการตั้งค่าสำเร็จ! (บันทึกลง DB แล้ว)")
        st.rerun()

    # ---------- 🛠️ เครื่องมือผู้ดูแล (ย้ายมาจากหน้าตารางผ่าตัด) ----------
    st.markdown("---")
    st.markdown("### 🛠️ เครื่องมือผู้ดูแล")
    st.caption("อัปโหลดตารางผ่าตัด (CSV) + ล้างกระดานทดสอบ — ย้ายมารวมที่หน้าตั้งค่า "
               "(ล็อก PIN เหมือนเดิม) · หน้าตารางผ่าตัดเหลือเฉพาะ ➕ เพิ่มเคส")
    from main_or_pages import render_csv_upload, render_clear_board
    render_csv_upload()
    render_clear_board()

    st.markdown("---")
    st.markdown("### 🤖 โมเดล AI + สถานะระบบ")
    render_system_status()


# ============================================================================
# PAGE 2: PLAN SCHEDULE
# ============================================================================

def parse_schedule_csv_to_cases(uploaded_file):
    """อ่าน CSV ตารางผ่าตัด (HIS — UTF-16 + quote ซ้อน หรือ CSV ปกติ) → list เคส
    พร้อมทำนายเวลา + ฟิลด์ flow (status='not_arrived') สำหรับโหลดเข้า OR Board ในขั้นตอนเดียว."""
    import csv as _csv
    import io as _io

    # ---- อ่านเป็น text (รองรับหลาย encoding) ----
    try:
        uploaded_file.seek(0)
        data = uploaded_file.getvalue() if hasattr(uploaded_file, 'getvalue') else uploaded_file.read()
    except (AttributeError, ValueError):
        return []
    text = data
    if isinstance(data, (bytes, bytearray)):
        text = None
        for enc in ['utf-16', 'utf-8-sig', 'utf-8', 'cp874', 'tis-620']:
            try:
                text = data.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
    if not text:
        return []

    # ---- two-pass parse: แกะ quote ชั้นนอกของ HIS (no-op สำหรับ CSV ปกติ) ----
    rows = []
    for outer in _csv.reader(_io.StringIO(text)):
        if not outer:
            continue
        inner = outer[0] if len(outer) == 1 else ",".join(outer)
        rows.append(next(_csv.reader([inner])))
    rows = [r for r in rows if any(str(x).strip() for x in r)]
    if len(rows) < 2:
        return []

    header = [h.strip().lower() for h in rows[0]]
    idx = {}
    for i, h in enumerate(header):
        if h and h not in idx:          # คอลัมน์ชื่อซ้ำ → เก็บตัวแรก
            idx[h] = i

    def col(*kws):
        for kw in kws:
            k = kw.lower()
            for h, i in idx.items():
                if k in h:
                    return i
        return None

    pos = {
        'hn': col('hn'), 'name': col('dspname', 'name'), 'age': col('age'),
        'procedure': col('icd9cm_name', 'procedure', 'icd9'),
        'surgeon': col('surgstfnm', 'surgeon'), 'date': col('opedate', 'date'),
        'estmtime': col('estmtime', 'opetime', 'time'), 'order': col('ororder', 'order'),
        'diagnosis': col('icd10_name', 'icd10', 'diag'), 'division': col('division'),
        'room': col('orroom', 'or_room', 'room'), 'procnote': col('procnote', 'note'),
        'optype': col('optype_var', 'optype'), 'optypenm': col('optypenm'),
        'ward': col('reqward'), 'ward2': col('rgtward'),
    }

    cases = []
    for r in rows[1:]:
        def get(key):
            p = pos.get(key)
            if p is None or p >= len(r):
                return None
            v = str(r[p]).strip()
            return v if v not in ('', 'nan', 'None') else None

        raw_time = get('estmtime')
        try:
            estm_val = int(float(raw_time)) if raw_time is not None else 0
        except (ValueError, TypeError):
            estm_val = 0
        is_tf = (estm_val == 0)
        sched_h, sched_m = (23, 55) if is_tf else parse_opetime_full(raw_time)

        raw_note = get('procnote') or ''
        _d = get('date')
        try:
            sched_date = pd.to_datetime(_d, dayfirst=True).date() if _d else datetime.now().date()
        except Exception:
            sched_date = datetime.now().date()

        raw_room = get('room')
        try:
            room_val = int(float(raw_room)) if raw_room is not None else None
        except (ValueError, TypeError):
            room_val = None
        try:
            age_val = int(float(get('age'))) if get('age') else 50
        except (ValueError, TypeError):
            age_val = 50
        try:
            order_val = int(float(get('order'))) if get('order') else 1
        except (ValueError, TypeError):
            order_val = 1

        # ประเภทเคส: emergency / urgency → ติดไฟฉุกเฉินแดงบนกระดาน
        _ot = ' '.join(x for x in (get('optype'), get('optypenm')) if x).lower()
        is_emer = ('emer' in _ot) or ('urg' in _ot) or ('ฉุกเฉิน' in _ot)

        # ward ที่ขอผ่าตัด (reqward หลัก, rgtward สำรอง) — ว่าง = เคส OPD
        ward_val = (get('ward') or get('ward2') or '').strip()

        # นอกเวลา: มีคำว่า "นอกเวลา" ใน procnote / หัตถการ (ICD-9) / วินิจฉัย (ICD-10)
        _after_txt = ' '.join(
            x for x in (raw_note, get('procedure'), get('diagnosis')) if x)
        is_after = 'นอกเวลา' in _after_txt

        # 🔑 id deterministic จากเนื้อเคส — สองเครื่องอัปโหลดไฟล์เดียวกันได้ id ตรงกัน
        #    → merge บอร์ดกลางจับคู่เคสถูก ไม่เกิดผู้ป่วยซ้ำ 2 แถว (uuid สุ่ม = id ต่างต่อเครื่อง)
        import hashlib as _hl
        _seed = (f"{get('hn') or ''}|{get('name') or ''}|{sched_date}|"
                 f"{(get('procedure') or '').strip().upper()}|"
                 f"{sched_h}:{sched_m}|{order_val}")
        case = {
            'id': "CSV_" + _hl.md5(_seed.encode('utf-8')).hexdigest()[:10],
            'hn': get('hn') or '', 'name': get('name') or 'ไม่ระบุ',
            'age': age_val, 'diagnosis': get('diagnosis') or '-',
            'procedure': (get('procedure') or 'UNKNOWN').strip().upper(),
            'anesthesia': '-', 'surgeon': get('surgeon') or '', 'room': room_val,
            'division': get('division') or '75', 'ororder': order_val,
            'case_type': 'Emergency' if is_emer else 'Elective',
            'is_emergency': is_emer,
            'ward': ward_val,
            'sched_date': sched_date, 'sched_hour': sched_h, 'sched_min': sched_m,
            'is_tf': is_tf, 'is_after_note': is_after,
            'procnote': raw_note, 'predicted_min': None, 'confidence': None,
        }
        pred = predict_surgical_time(
            case['procedure'], case['age'], case['surgeon'], case['division'],
            case['sched_hour'] if case['sched_hour'] < 23 else 9)
        case['predicted_min'] = pred['predicted_min']
        case['confidence'] = pred['confidence']
        case['pred_method'] = pred['method']
        case['proc_n'] = pred.get('proc_n', 0)
        case['surg_n'] = pred.get('surg_n', 0)
        case['predicted_range'] = pred.get('predicted_range')      # 📏 ช่วง conformal 90%
        case['range_method'] = pred.get('range_method')
        case.update({
            'status': 'not_arrived',
            'ai_predicted_min': case.get('predicted_min', 30),
            'user_override_min': None,
            'effective_min': case.get('predicted_min', 30),
            'or_room_assigned': room_val or 1,
            'time_arrived_holding': None, 'time_entered_or': None,
            'time_exited_or': None, 'time_discharged': None,
            'actual_duration_min': None,
        })
        cases.append(case)
    return cases


def page_plan_schedule():
    st.markdown('<h1 class="header-title">📋 วางแผนตาราง</h1>', unsafe_allow_html=True)

    st.markdown('<div style="background:#e3f2fd;padding:12px 16px;border-radius:10px;border-left:4px solid #1976d2;margin-bottom:16px;"><b>📋 วิธีใช้</b><br>1. อัพโหลดไฟล์ CSV ตารางผ่าตัด → ระบบทำนายเวลาอัตโนมัติ<br>2. ตรวจสอบรายการ ลบเคสที่ไม่ต้องการ<br>3. กด <b>"📤 ส่งเข้า OR Board"</b><br><span style="font-size:12px;color:#666;">⚠️ Upload ซ้ำได้ — ระบบจะอัพเดทเฉพาะเคสที่ยังไม่เข้า flow</span></div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader("เลือกไฟล์ CSV ตารางผ่าตัด", type=["csv"], help="รองรับหลาย encoding")

    if uploaded_file is not None:
        encodings = ['utf-8-sig', 'utf-8', 'utf-16', 'tis-620', 'cp874']
        df_raw = None
        for enc in encodings:
            try:
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, encoding=enc)
                break
            except (ValueError, TypeError, AttributeError):
                continue
        if df_raw is None:
            st.error("❌ ไม่สามารถอ่านไฟล์ได้")
            return

        st.markdown(f"**พบ {len(df_raw)} แถว, {len(df_raw.columns)} คอลัมน์**")

        col_map = {}
        cols_lower = {c.lower(): c for c in df_raw.columns}
        def find_col(*kws):
            for kw in kws:
                for cl, co in cols_lower.items():
                    if kw.lower() in cl:
                        return co
            return None

        col_map['hn'] = find_col('hn')
        col_map['name'] = find_col('dspname','name')
        col_map['age'] = find_col('age')
        col_map['procedure'] = find_col('icd9cm_name','procedure','icd9')
        col_map['surgeon'] = find_col('surgstfnm','surgeon')
        col_map['date'] = find_col('opedate','date')
        col_map['estmtime'] = find_col('estmtime','opetime','time')
        col_map['order'] = find_col('ororder','order')
        col_map['diagnosis'] = find_col('icd10name','icd10','diag')
        col_map['anesthesia'] = find_col('anestechnm','anestype','anes')
        col_map['division'] = find_col('division')
        col_map['casetype'] = find_col('optype','casetype')
        col_map['procnote'] = find_col('procnote','note')
        col_map['room'] = find_col('orroom','or_room','room')   # ห้องที่จะผ่า (จาก CSV)

        with st.expander("🔧 ปรับ Column Mapping", expanded=False):
            all_cols = ['(ไม่มี)'] + list(df_raw.columns)
            c1, c2, c3 = st.columns(3)
            with c1:
                for k in ['hn','name','age','procedure']:
                    col_map[k] = st.selectbox(k.upper(), all_cols, index=all_cols.index(col_map[k]) if col_map[k] in all_cols else 0, key=f"map_{k}")
            with c2:
                for k in ['surgeon','date','estmtime','order']:
                    col_map[k] = st.selectbox(k.upper(), all_cols, index=all_cols.index(col_map[k]) if col_map[k] in all_cols else 0, key=f"map_{k}")
            with c3:
                for k in ['diagnosis','anesthesia','casetype','procnote']:
                    col_map[k] = st.selectbox(k.upper(), all_cols, index=all_cols.index(col_map[k]) if col_map[k] in all_cols else 0, key=f"map_{k}")

        if st.button("✅ โหลดรายการ + ทำนายเวลา", type="primary", use_container_width=True):
            new_cases = []
            for _, row in df_raw.iterrows():
                def get(key):
                    c = col_map.get(key)
                    if c and c != '(ไม่มี)' and c in row.index:
                        v = row[c]
                        return v if pd.notna(v) else None
                    return None

                raw_time = get('estmtime')
                try:
                    estm_val = int(float(raw_time)) if raw_time is not None else 0
                except (ValueError, TypeError, AttributeError):
                    estm_val = 0
                is_tf = (estm_val == 0)
                sched_h, sched_m = (23, 55) if is_tf else parse_opetime_full(raw_time)

                raw_note = str(get('procnote') or '')
                raw_date = get('date')
                try:
                    sched_date = pd.to_datetime(str(raw_date)).date()
                except (ValueError, TypeError, AttributeError):
                    sched_date = datetime.now().date()

                raw_room = get('room')
                try:
                    room_val = int(float(raw_room)) if raw_room is not None else None
                except (ValueError, TypeError):
                    room_val = None

                # 🔑 id deterministic (เหตุผลเดียวกับ parser บอร์ด — กันเคสซ้ำข้ามเครื่อง)
                import hashlib as _hl
                _seed = (f"{get('hn') or ''}|{get('name') or ''}|{sched_date}|"
                         f"{str(get('procedure') or '').strip().upper()}|"
                         f"{sched_h}:{sched_m}|{get('order') or 1}")
                case = {
                    'id': "CSV_" + _hl.md5(_seed.encode('utf-8')).hexdigest()[:10],
                    'hn': str(get('hn') or ''), 'name': str(get('name') or 'ไม่ระบุ'),
                    'age': int(float(get('age'))) if get('age') else 50,
                    'diagnosis': str(get('diagnosis') or '-'),
                    'procedure': str(get('procedure') or 'UNKNOWN').strip().upper(),
                    'anesthesia': str(get('anesthesia') or '-'),
                    'surgeon': str(get('surgeon') or ''), 'room': room_val,
                    'division': str(get('division') or '75'),
                    'ororder': int(float(get('order'))) if get('order') else 1,
                    'case_type': str(get('casetype') or 'Elective').capitalize(),
                    'sched_date': sched_date, 'sched_hour': sched_h, 'sched_min': sched_m,
                    'is_tf': is_tf,
                    # นอกเวลา: ดูทั้ง procnote + หัตถการ + วินิจฉัย
                    'is_after_note': 'นอกเวลา' in ' '.join(
                        str(x) for x in (raw_note, get('procedure'),
                                         get('diagnosis')) if x),
                    'procnote': raw_note, 'predicted_min': None, 'confidence': None,
                }
                new_cases.append(case)

            in_flow_hns = {pc['hn'] for pc in st.session_state.patient_cases if pc.get('status') != 'not_arrived' and pc.get('hn')}
            _n_before = len(st.session_state.patient_cases)
            st.session_state.patient_cases = [pc for pc in st.session_state.patient_cases if pc.get('status') != 'not_arrived']
            if len(st.session_state.patient_cases) != _n_before:
                st.session_state['_board_dirty'] = True   # CR-2: บอร์ดเปลี่ยน (ถอนเคสยังไม่มา)
            filtered = [c for c in new_cases if not (c['hn'] and c['hn'] in in_flow_hns)]
            skipped = len(new_cases) - len(filtered)

            with st.spinner("กำลังทำนายเวลาผ่าตัด..."):
                for case in filtered:
                    pred = predict_surgical_time(case['procedure'], case['age'], case['surgeon'], case['division'], case['sched_hour'] if case['sched_hour'] < 23 else 9)
                    case['predicted_min'] = pred['predicted_min']
                    case['confidence'] = pred['confidence']
                    case['pred_method'] = pred['method']
                    case['proc_n'] = pred.get('proc_n', 0)
                    case['surg_n'] = pred.get('surg_n', 0)

            st.session_state.uploaded_cases = filtered
            msg = [f"✅ โหลด + ทำนายสำเร็จ {len(filtered)} เคส"]
            if skipped > 0:
                msg.append(f"ข้าม {skipped} เคสที่เข้า flow แล้ว")
            st.success(" | ".join(msg))
            st.rerun()

    # Manual entry
    with st.expander("➕ เพิ่มเคสด้วยตนเอง"):
        c1, c2 = st.columns(2)
        with c1:
            hn_m = st.text_input("HN *", key="m_hn")
            name_m = st.text_input("ชื่อ-สกุล *", key="m_name")
            proc_m = st.text_input("หัตถการ *", key="m_proc")
            surg_m = st.text_input("แพทย์ *", key="m_surg")
        with c2:
            age_m = st.number_input("อายุ", 0, 120, 50, key="m_age")
            time_m = st.time_input("เวลาผ่าตัด", key="m_time")
            order_m = st.number_input("ลำดับ", 1, 30, 1, key="m_order")
            div_m = st.selectbox("แผนก", ['75','74','78','76','701','77','72'], key="m_div")

        if st.button("✅ เพิ่มเคส + ทำนาย", use_container_width=True):
            if hn_m and name_m and proc_m and surg_m:
                case = {
                    'id': f"MANUAL_{uuid.uuid4().hex[:8]}", 'hn': hn_m, 'name': name_m,
                    'age': age_m, 'diagnosis': '-', 'procedure': proc_m.strip().upper(),
                    'anesthesia': '-', 'surgeon': surg_m, 'room': 1, 'division': div_m,
                    'ororder': order_m, 'case_type': 'Elective', 'sched_date': datetime.now().date(),
                    'sched_hour': time_m.hour, 'sched_min': time_m.minute,
                    'is_tf': False, 'is_after_note': False, 'procnote': '',
                    'predicted_min': None, 'confidence': None,
                }
                pred = predict_surgical_time(case['procedure'], case['age'], case['surgeon'], case['division'], case['sched_hour'])
                case.update({'predicted_min': pred['predicted_min'], 'confidence': pred['confidence'], 'pred_method': pred['method'], 'proc_n': pred.get('proc_n',0), 'surg_n': pred.get('surg_n',0)})
                st.session_state.uploaded_cases.append(case)
                st.success(f"✅ ทำนาย {pred['predicted_min']} นาที")
                st.rerun()
            else:
                st.error("กรุณากรอก HN, ชื่อ, หัตถการ, แพทย์")

    # Display uploaded cases
    if st.session_state.uploaded_cases:
        st.markdown("---")
        total = len(st.session_state.uploaded_cases)
        tf_n = sum(1 for c in st.session_state.uploaded_cases if c.get('is_tf'))
        after_n = sum(1 for c in st.session_state.uploaded_cases if c.get('is_after_note') or ((not c.get('is_tf')) and c['sched_hour'] >= WORK_END))

        m1, m2, m3 = st.columns(3)
        m1.metric("เคสทั้งหมด", total)
        m2.metric("TF", tf_n)
        m3.metric("นอกเวลา", after_n)

        st.markdown("### 📋 OR Schedule — ห้องผ่าตัดศัลยกรรมทั่วไป")
        sorted_cases = sorted(enumerate(st.session_state.uploaded_cases), key=lambda x: (1 if x[1].get('is_tf') else 0, x[1]['sched_hour'], x[1]['sched_min'], x[1]['ororder']))

        st.markdown(f'<div style="background:linear-gradient(135deg,#2c3e50,#3498db);color:white;padding:10px 16px;border-radius:8px 8px 0 0;margin-top:16px;font-size:16px;font-weight:700;">🏥 ห้องผ่าตัดศัลยกรรมทั่วไป 1 ({total} เคส)</div>', unsafe_allow_html=True)

        # 🔒 mask ชื่อ/HN บนจอเสมอ (นโยบาย 11 มิ.ย. 2026 · มาตรา 3.6.4)
        from main_or_db import mask_patient_name as _mask_nm, mask_hn as _mask_hn
        to_delete = []
        for idx, case in sorted_cases:
            time_d = "TF" if case.get('is_tf') else f'{case["sched_hour"]:02d}:{case["sched_min"]:02d}'
            pred_html = ""
            if case.get('predicted_min'):
                conf = case.get('confidence', '-')
                conf_color = '#27ae60' if conf == 'สูง' else ('#f39c12' if conf == 'ปานกลาง' else '#e74c3c')
                pred_html = f'<br><span style="font-size:12px;">🤖 <b style="color:#2980b9;">{case["predicted_min"]} นาที</b> | ความเชื่อมั่น <b style="color:{conf_color};">{conf}</b></span>'

            col_i, col_d = st.columns([11, 1])
            with col_i:
                # 🔒 mask + escape (กัน HTML/script จากไฟล์ HIS แทรกหน้า)
                import html as _html
                _nm = _html.escape(_mask_nm(case["name"]))
                _h4 = _html.escape(_mask_hn(case["hn"]) or "-")
                _pc = _html.escape(str(case["procedure"]))
                _sg = _html.escape(str(case["surgeon"] or "-"))
                st.markdown(f'<div style="border-left:4px solid #eee;background:#fafafa;padding:10px 14px;border-radius:0 4px 4px 0;margin:1px 0;"><span style="font-weight:700;color:#2c3e50;">#{case["ororder"]}</span> <span style="color:#2980b9;font-weight:600;">{time_d}</span> &nbsp; <b>{_nm}</b> <span style="color:#7f8c8d;font-size:12px;">HN {_h4} | อายุ {case["age"]} ปี</span><br><span style="font-size:12px;color:#2c3e50;"><span style="color:#c0392b;">Op:</span> {_pc} | <span style="color:#2980b9;">Surg:</span> {_sg}</span>{pred_html}</div>', unsafe_allow_html=True)
            with col_d:
                if st.button("❌", key=f"del_{idx}"):
                    to_delete.append(idx)

        if to_delete:
            st.session_state.uploaded_cases = [c for i, c in enumerate(st.session_state.uploaded_cases) if i not in to_delete]
            st.rerun()

        c_clr, c_send = st.columns([1, 2])
        with c_clr:
            if st.button("🗑️ ล้างทั้งหมด", use_container_width=True):
                st.session_state.uploaded_cases = []
                st.rerun()
        with c_send:
            if st.button("📤 ส่งเข้า OR Board", type="primary", use_container_width=True):
                new_n = 0
                existing_ids = {c['id'] for c in st.session_state.patient_cases}
                for case in st.session_state.uploaded_cases:
                    if case['id'] not in existing_ids:
                        p = dict(case)
                        p.update({'status': 'not_arrived', 'ai_predicted_min': case.get('predicted_min', 30), 'user_override_min': None, 'effective_min': case.get('predicted_min', 30), 'or_room_assigned': 1, 'time_arrived_holding': None, 'time_entered_or': None, 'time_exited_or': None, 'time_discharged': None, 'actual_duration_min': None})
                        st.session_state.patient_cases.append(p)
                        new_n += 1
                if new_n:
                    # CR-2: งานเป็นชุด (bulk) → ตั้ง dirty โดยไม่ระบุ ids = ของเราชนะตอน merge
                    st.session_state['_board_dirty'] = True
                st.success(f"✅ ส่ง {new_n} เคส" if new_n else "ℹ️ เคสทั้งหมดอยู่ใน OR Board แล้ว")
                st.rerun()

        # HP Bar
        pred_cases = [c for c in st.session_state.uploaded_cases if c.get('predicted_min')]
        if pred_cases:
            st.markdown("---")
            in_time = [c for c in pred_cases if not (c.get('is_after_note') or ((not c.get('is_tf')) and c['sched_hour'] >= WORK_END))]
            op_min = sum(c['predicted_min'] for c in in_time)
            to_min = TURNOVER_MINOR * len(in_time)
            total_min = op_min + to_min

            st.markdown("### 🎮 เวลาใช้ห้องผ่าตัด (ในเวลาราชการ)")
            op_pct = min(100, op_min / WORK_MINUTES * 100)
            to_pct = min(100 - op_pct, to_min / WORK_MINUTES * 100)
            total_pct = op_pct + to_pct
            bar_c = '#27ae60' if total_pct <= 80 else ('#f39c12' if total_pct <= 100 else '#e74c3c')
            overflow = total_min > WORK_MINUTES
            st.markdown(f'<div style="margin:6px 0;"><div style="display:flex;align-items:center;margin-bottom:2px;"><span style="font-weight:700;font-size:14px;width:120px;">ผ่าตัดเล็ก 1</span><span style="font-size:12px;color:#7f8c8d;">{len(in_time)} เคส | Op {op_min} + TO {to_min} = <b style="color:{bar_c};">{total_min} นาที</b>{"⚠️ เกิน!" if overflow else ""}</span></div><div style="background:#ecf0f1;border-radius:6px;height:22px;width:100%;position:relative;overflow:visible;"><div style="background:#3498db;height:100%;width:{op_pct}%;border-radius:6px 0 0 6px;float:left;"></div><div style="background:#bdc3c7;height:100%;width:{to_pct}%;float:left;"></div><div style="position:absolute;left:100%;top:-2px;height:26px;width:2px;background:#e74c3c;"></div></div></div>', unsafe_allow_html=True)


# ============================================================================
# MAIN
# ============================================================================

def _check_password():
    """🔒 Password gate — แสดง login form ถ้ายังไม่ได้ authenticate.
    Return True ถ้าผ่านแล้ว / False ถ้ายังไม่ผ่าน (และจะแสดง login form)
    """
    try:
        _pwd_set = st.secrets.get('app_password', None)
    except Exception:
        _pwd_set = None
    if not _pwd_set:
        # 🔒 fail-closed: ถ้าต่อ Supabase (= deploy จริง/มีข้อมูลจริง) แต่ไม่ตั้งรหัส
        #    → ปิดการเข้าถึง (กันแอปเปิดสาธารณะโดยไม่ตั้งใจ)
        #    bypass เฉพาะโหมด local SQLite (dev บนเครื่องตัวเอง)
        try:
            from db_connection import IS_POSTGRES as _is_pg
        except Exception:
            _is_pg = False
        if _is_pg:
            st.error(
                "⛔ ระบบยังไม่ได้ตั้งรหัสผ่าน (app_password) — ปิดการเข้าถึงไว้ก่อนเพื่อความปลอดภัย\n\n"
                "ผู้ดูแล: ไปที่ Streamlit Cloud → App settings → Secrets แล้วเพิ่ม\n"
                "`app_password = \"รหัสที่ต้องการ\"` จากนั้น reboot แอป")
            return False
        return True  # local dev (SQLite) — allow access

    if st.session_state.get('authenticated'):
        return True

    # Login screen
    st.markdown("""
    <style>
    .login-card {
        max-width: 420px; margin: 80px auto; padding: 32px;
        background: white; border-radius: 16px;
        border: 0.5px solid #e0e0e0;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06);
    }
    </style>
    """, unsafe_allow_html=True)

    _l, _c, _r = st.columns([1, 2, 1])
    with _c:
        st.markdown(
            '<div style="text-align:center;margin:60px 0 24px;">'
            '<div style="font-size:48px;">🔒</div>'
            '<div style="font-size:22px;font-weight:600;color:#263238;'
            'margin-top:8px;">OR Dashboard — Demo</div>'
            '<div style="font-size:13px;color:#607d8b;margin-top:4px;">'
            'ใส่รหัสผ่านเพื่อเข้าใช้งาน</div></div>',
            unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            pwd = st.text_input("รหัสผ่าน", type="password",
                                placeholder="••••••••",
                                label_visibility='collapsed')
            submit = st.form_submit_button("🔓 เข้าสู่ระบบ",
                                            use_container_width=True,
                                            type='primary')
            if submit:
                if pwd == _pwd_set:
                    st.session_state['authenticated'] = True
                    st.rerun()
                else:
                    st.error("❌ รหัสผ่านไม่ถูกต้อง")

        st.caption("💡 รหัสผ่านจากเจ้าของแอป — กรุณาอย่าแชร์สาธารณะ")

    return False


def main():
    # 🔒 Password gate ก่อนทุก action
    if not _check_password():
        st.stop()

    # Initialize DB on startup — ต่อไม่ได้ให้ขึ้นข้อความอ่านรู้เรื่อง ไม่ใช่ traceback แดงใส่พยาบาล
    # 🔌 10+ users: รันครั้งเดียวต่อ session พอ (เดิมรันทุก rerun = ยืม connection ฟรีทุก 30 วิ)
    try:
        if not st.session_state.get('_db_inited'):
            init_db()
            st.session_state['_db_inited'] = True
    except Exception as _db_err:
        st.error(
            "⛔ เชื่อมต่อฐานข้อมูลไม่สำเร็จ\n\n"
            "ลองกดรีเฟรชหน้า (F5) อีกครั้งใน 1 นาที — ถ้ายังไม่หาย "
            "แจ้งผู้ดูแลระบบ (Mukky) พร้อมภาพหน้าจอนี้")
        with st.expander("รายละเอียดทางเทคนิค (สำหรับผู้ดูแล)"):
            st.code(str(_db_err)[:600])
        st.stop()

    # ========================================================================
    # แถบเมนูบนสุด (แทน sidebar — กันปัญหา sidebar พับแล้วกางไม่ได้บน Streamlit Cloud)
    # ========================================================================
    _hdr_l, _hdr_r = st.columns([5, 1])
    with _hdr_l:
        from datetime import datetime as _dtm, timedelta as _td
        _now_hdr = (_dtm.utcnow() + _td(hours=7)).strftime('%d/%m/%Y · ปรับล่าสุด %H:%M น.')
        st.markdown(
            '<div class="or-chips" style="margin-top:6px;">'
            '<span class="or-chip"><span class="dot"></span>บอร์ดกลาง ซิงก์อัตโนมัติ</span>'
            '<span class="or-chip">🤖 AI: honest_v1</span>'
            f'<span class="or-chip">📅 {_now_hdr}</span>'
            '</div>',
            unsafe_allow_html=True,
        )
    with _hdr_r:
        if st.session_state.get('authenticated'):
            if st.button("🔒 ออกจากระบบ", use_container_width=True,
                         key='_logout_btn'):
                st.session_state['authenticated'] = False
                st.rerun()

    # เมนูหลัก = แท็บแนวนอนบนสุด · เก็บค่าใน URL ให้รอด refresh (รันเฉพาะหน้าที่เลือก)
    _page_options = ["📋 ตารางผ่าตัด", "📊 ภาพรวมวันนี้", "📈 สถิติย้อนหลัง",
                     "🛏 Utilization", "🤖 AI Prediction", "⚙️ ตั้งค่า"]
    try:
        _default_page = st.query_params.get('page', _page_options[0])
    except Exception:
        _default_page = _page_options[0]
    _default_idx = _page_options.index(_default_page) if _default_page in _page_options else 0
    page = st.radio(
        "เมนูหลัก",
        _page_options,
        index=_default_idx,
        horizontal=True,
        label_visibility="collapsed",
        key='_main_page',
    )
    try:
        if page != _default_page:
            st.query_params['page'] = page
    except Exception:
        pass

    # 🤖 รายละเอียดโมเดล AI + Reload — ย้ายไปแสดงในหน้า ⚙️ ตั้งค่าแล้ว (render_system_status)
    #    หน้า board เริ่มที่เนื้อหาทันทีตาม mock-up (ไม่มีแถบคั่น + ไม่มีช่องว่างใหญ่)

    # ========================================================================
    # PAGE ROUTING — เรียกหน้าตามที่ user เลือกจากแท็บบนสุด
    # ========================================================================
    if page == "📋 ตารางผ่าตัด":
        page_or_board()
    elif page == "📊 ภาพรวมวันนี้":
        page_admin('today')
    elif page == "📈 สถิติย้อนหลัง":
        page_admin('history')
    elif page == "🛏 Utilization":
        page_admin('util')
    elif page == "🤖 AI Prediction":
        page_admin('ai')
    elif page == "⚙️ ตั้งค่า":
        page_room_settings()


if __name__ == "__main__":
    main()
