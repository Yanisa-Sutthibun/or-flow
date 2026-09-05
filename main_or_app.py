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
    init_session_state, predict_surgical_time,
    parse_opetime_full, parse_opetime,
    TURNOVER_MINOR, WORK_START, WORK_END, WORK_MINUTES
)
# หมายเหตุ: page_statistics (main_or_pages) และ page_tracking (main_or_tracking)
# ไม่ถูก route ใน sidebar แล้ว — ตัด import ออกเพื่อลดเวลาโหลด/ความสับสน
# (โค้ดหน้าเหล่านั้นยังอยู่ในไฟล์เดิม เผื่อเรียกคืนในอนาคต)
from main_or_pages import page_or_board
from main_or_admin import page_admin
from main_or_db import init_db, get_db_stats, save_room_settings, load_room_settings
from room_config import (
    get_active_rooms, ROOM_INFO as RC_ROOM_INFO, SPECIALTY_FULL, room_label,
)

# 🎨 ไอคอนประจำสาขาของห้อง — ใช้ทั้งหน้าตั้งค่าและส่วน 🔗 ลิงก์ติดตั้งจอ
#    (ผูกกับ "สาขา" ไม่ใช่เลขห้อง → ย้ายสาขา/เพิ่มห้อง ไอคอนตามไปเอง)
SPECIALTY_ICON = {
    'SCOPE': '🔬', 'EM': '🚨', 'URO': '💧', 'GEN': '🩺', 'VAS': '🩸',
    'NEURO': '🧠', 'PLASTIC': '✨', 'ENT': '👂', 'GEN&ENT': '⚕️',
}
# คำบรรยายห้องที่เขียนเฉพาะตัว (นอกนั้นสร้างจาก SPECIALTY_FULL อัตโนมัติ)
ROOM_DESC = {91: 'ห้องรับเคสฉุกเฉิน 24 ชม.'}

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

# 🖥️ แอป DEMO: ชื่อแท็บ+ไอคอนต่างจากระบบจริงชัดเจน (กันเปิดสลับแอป)
def _page_config_kwargs():
    try:
        _d = str(st.secrets.get('instance_mode', '')).lower() == 'demo'
    except Exception:
        _d = False
    if _d:
        return dict(page_title="DEMO · OR Flow ระบบสาธิต", page_icon="🖥️",
                    layout="wide", initial_sidebar_state="collapsed")
    return dict(page_title="ห้องผ่าตัดศัลยกรรมทั่วไป Dashboard", page_icon="🏥",
                layout="wide", initial_sidebar_state="collapsed")


st.set_page_config(**_page_config_kwargs())

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
    /* 📐 9 ส.ค. 2026: ขนาดของ .stat-title/.stat-value/.header-title/.subheader
       ถูกย้ายไป ui_theme.py (type scale กลาง) แล้ว — เดิมประกาศซ้ำที่นี่ด้วย
       ทำให้ตัวเลขไม่ตรงกันระหว่างหน้า แก้ทีต้องไล่ 2 ที่ */
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
    """🤖 กล่องสถานะโมเดล AI — ตัวหลัก thesis_ML_v2 (13 features) · fallback thesis_ML
    (โปรโมต v2 ขึ้นบอร์ด 7 ก.ค. 2026 ตามคำสั่งมุคกี้ · อ่านจาก artifact จริง)"""
    try:
        import json as _json
        from pathlib import Path as _Path
        _v2meta_p = _Path(__file__).resolve().parent / 'models' / 'thesis_ML_v2' / 'meta.json'
        _v2pkl_ok = (_Path(__file__).resolve().parent / 'models' / 'thesis_ML_v2'
                     / 'model.pkl').exists()
        if _v2pkl_ok and _v2meta_p.exists():
            _m2 = _json.loads(_v2meta_p.read_text(encoding='utf-8'))
            _mt = _m2.get('metrics_test67') or {}
            st.markdown(
                f'<div style="background:#e8f5e9;padding:10px;border-radius:8px;text-align:center;">'
                f'<p style="margin:0;font-size:var(--fs-meta);color:#2e7d32;">'
                f'🤖 <b>AI Model: thesis_ML_v2</b> — โมเดลวิทยานิพนธ์ 13 features '
                f'(ตัวที่ทำนายบนบอร์ด · เริ่ม 7 ก.ค. 2569)<br>'
                f'General XGBoost + Target Encoding · เทรน {_m2.get("n_train", "—"):,} เคส '
                f'(พ.ศ. 2564–2566)<br>'
                f'MAE {_mt.get("MAE", "—")} นาที · R² {_mt.get("R2", "—")} · '
                f'±30 นาที {_mt.get("within30min_pct", "—")}% (ทดสอบปี 2567)<br>'
                f'ช่วงทำนาย 90%: split conformal · fallback: thesis_ML → ค่ากลาง DB'
                f'</p></div>',
                unsafe_allow_html=True,
            )
            return
        _hdir = _Path(__file__).resolve().parent / 'models' / 'thesis_ML'
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
            f'<div style="background:#e8f5e9;padding:10px;border-radius:8px;text-align:center;">'
            f'<p style="margin:0;font-size:var(--fs-meta);color:#2e7d32;">'
            f'🤖 <b>AI Model: thesis_ML</b> (ตัวที่ทำนายบนบอร์ด)<br>'
            f'มัธยฐานลำดับชั้น + XGBoost residual<br>'
            f'เทรน {_ntr} เคส (พ.ศ. 2564–2567)<br>'
            f'MAE {_hl.get("mae", "—")} นาที · ±15 นาที {_hl.get("within15_pct", "—")}% '
            f'(ทดสอบปี 2567)<br>{_rng_txt}'
            f'</p></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="background:#ffebee;padding:10px;border-radius:8px;text-align:center;">'
            '<p style="margin:0;font-size:var(--fs-meta);color:#c62828;">'
            '⚠️ <b>ไม่พบโมเดล thesis_ML</b><br>'
            'ตรวจ models/thesis_ML/ (hier_*.json + resid_*.pkl)<br>'
            'ระบบจะ fallback เป็นค่ามัธยฐานจากฐานข้อมูล</p></div>',
            unsafe_allow_html=True,
        )


def _app_base_url() -> str:
    """URL ของ "แอปที่กำลังรันอยู่" สำหรับประกอบลิงก์ติดตั้งจอ

    ลำดับที่ลอง: secrets app_base_url (ตั้งเองได้ ชนะเสมอ) → Origin/Host header
    ที่เบราว์เซอร์ส่งมา → '' (คืนค่าว่าง = ผู้เรียกไปใช้ลิงก์สัมพัทธ์แทน)

    ⚠️ ตั้งใจไม่ hardcode URL ไว้ในโค้ด — แอปจริงกับแอปสาธิตใช้โค้ดชุดเดียวกัน
    (push เดียวอัปเดต 2 แอป) ถ้า hardcode แอปสาธิตจะโชว์ลิงก์ของระบบจริง
    """
    try:
        _u = str(st.secrets.get('app_base_url', '') or '').strip()
    except Exception:
        _u = ''
    if _u.startswith('http'):
        return _u.rstrip('/')
    try:
        _h = {str(k).lower(): str(v) for k, v in dict(st.context.headers or {}).items()}
    except Exception:
        _h = {}
    _origin = str(_h.get('origin', '') or '').strip()
    if _origin.startswith('http'):
        return _origin.rstrip('/')
    _host = str(_h.get('host', '') or '').strip()
    if _host:
        _scheme = 'http' if _host.startswith(('localhost', '127.0.0.1')) else 'https'
        return f"{_scheme}://{_host}"
    return ''


def render_screen_links(room_info: dict):
    """🔗 ลิงก์ติดตั้งจอ (one stop service — มุคกี้สั่ง 7 ส.ค. 2026)

    รวมลิงก์ที่ต้องเอาไปทำ shortcut ไว้ที่เดียว: 📺 จอญาติ + 🚪 จอประจำห้องทุกห้อง
    · กุญแจอ่านสดจาก st.secrets ของแอปที่รันอยู่ → แอปจริงได้ชุดจริง แอปสาธิต
      ได้ชุดสาธิต ไม่ปนกัน และไม่มี token ค้างในโค้ด (PDPA — กันหลุดขึ้น git)
    · ห้องที่ยังไม่ได้ตั้งกุญแจ = ขึ้นเตือนให้เห็น ไม่ปล่อยหายเงียบ
      (บทเรียน OR9 ที่ตกหล่นจนจอเปิดไม่ได้)
    · สิทธิ์: หน้านี้เข้าด้วยรหัสหน่วยงานซึ่งสูงกว่าสิทธิ์จอห้องอยู่แล้ว
      จอประจำห้องเองเข้าหน้านี้ไม่ได้ (เด้งเข้าหน้าโฟกัสห้องเสมอ)
    """
    _is_demo = str(st.secrets.get('instance_mode', '')).lower() == 'demo'
    _sys = "ระบบสาธิต" if _is_demo else "ระบบจริง"
    _sys_bg, _sys_fg = ('#fef3c7', '#92400e') if _is_demo else ('#e1f5ee', '#065f46')

    # 🎨 หัวข้อการ์ดเดียว: ชื่อหัวข้อ + ป้ายบอกระบบ + คำอธิบาย (มุคกี้สั่ง 8 ส.ค. 2026)
    st.markdown("---")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
        f'<span style="font-size:22px;font-weight:700;color:#0f172a;">🔗 ลิงก์ติดตั้งจอ</span>'
        f'<span style="background:{_sys_bg};color:{_sys_fg};border-radius:999px;'
        f'padding:5px 16px;font-size:var(--fs-meta);font-weight:700;">{_sys}</span></div>'
        f'<div style="color:#64748b;font-size:var(--fs-meta);margin:6px 0 14px;">'
        f'คัดลอกลิงก์ไปสร้าง shortcut บนเครื่องของห้องนั้นครั้งเดียวจบ '
        f'· อย่าแชร์ลิงก์ข้ามห้อง</div>',
        unsafe_allow_html=True)

    _base = _app_base_url()
    if not _base:
        st.info("อ่าน URL ของแอปไม่ได้ : ตั้งค่า `app_base_url` ใน Secrets "
                "เพื่อให้ลิงก์ด้านล่างเป็นลิงก์เต็มที่คัดลอกไปใช้ได้")

    def _link(qs: str) -> str:
        return f"{_base}/?{qs}" if _base else f"./?{qs}"

    def _screen_head(icon: str, title: str, sub: str, dim: bool = False):
        _c = '#94a3b8' if dim else '#0f172a'
        st.markdown(
            f'<div style="font-size:var(--fs-card);font-weight:700;color:{_c};line-height:1.35;">'
            f'{icon} {title}</div>'
            f'<div style="font-size:var(--fs-meta);color:#94a3b8;">{sub}</div>',
            unsafe_allow_html=True)

    def _screen_row(icon: str, title: str, sub: str, url: str):
        """การ์ดจอญาติ (เต็มความกว้าง) · ซ้ายชื่อจอ · กลางลิงก์ · ขวาปุ่มเปิด"""
        with st.container(border=True):
            _c1, _c2, _c3 = st.columns([3.2, 6, 1.6], vertical_alignment="center")
            with _c1:
                _screen_head(icon, title, sub)
            with _c2:
                st.code(url, language=None)
            with _c3:
                st.link_button("เปิดจอ ↗", url, use_container_width=True)

    def _screen_tile(icon: str, title: str, sub: str, url: str):
        """การ์ดในตาราง 3 ช่อง (มุคกี้เคาะ 8 ส.ค. 2026) — เรียงลง: ชื่อ → ลิงก์ → ปุ่ม
        ลิงก์ใช้ st.code เพื่อให้มีปุ่มคัดลอกในตัว (ช่องแคบจึงมีแถบเลื่อนแนวนอน ยอมรับได้)"""
        with st.container(border=True):
            _screen_head(icon, title, sub)
            st.code(url, language=None)
            st.link_button("เปิดจอ ↗", url, use_container_width=True)

    # ── 📺 จอญาติ ──────────────────────────────────────────────────
    try:
        _fam = str(st.secrets.get('family_board_token', '') or '')
    except Exception:
        _fam = ''
    if _fam:
        _screen_row('📺', 'จอญาติ', 'ทีวีหน้าห้องผ่าตัด · อ่านอย่างเดียว',
                    _link(f"view=family&k={_fam}"))
    else:
        st.warning("ยังไม่ได้ตั้ง `family_board_token` ใน Secrets ของแอปนี้")

    # ── 🚪 จอประจำห้องผ่าตัด ───────────────────────────────────────
    try:
        _rtoks = {str(k): str(v) for k, v in dict(st.secrets.get('room_tokens', {})).items()}
    except Exception:
        _rtoks = {}
    _rooms = list(room_info.keys())
    _missing = [rm for rm in _rooms if not _rtoks.get(str(rm))]
    _ready = len(_rooms) - len(_missing)

    with st.expander(f"**🖥️ จอประจำห้องผ่าตัด · พร้อมใช้ {_ready} จาก {len(_rooms)} ห้อง**",
                     expanded=bool(_missing)):
        if _missing:
            st.warning("⚠️ ห้องที่ยังไม่ได้ตั้งกุญแจใน Secrets : "
                       + ", ".join(str(room_info[rm]['name']) for rm in _missing)
                       + " (จอห้องนี้จะเปิดไม่ได้จนกว่าจะเพิ่มกุญแจใต้ `[room_tokens]`)")
        # ตาราง 3 ช่องต่อแถว — สร้าง columns ใหม่ทุกแถวเพื่อให้การ์ดสูงเท่ากันในแถวเดียวกัน
        for _start in range(0, len(_rooms), 3):
            _cols = st.columns(3)
            for _col, _rm in zip(_cols, _rooms[_start:_start + 3]):
                _info = room_info[_rm]
                _tok = _rtoks.get(str(_rm), '')
                with _col:
                    if _tok:
                        _screen_tile(_info['icon'], _info['name'], _info['desc'],
                                     _link(f"room={_rm}&k={_tok}"))
                    else:
                        with st.container(border=True):
                            _screen_head(_info['icon'], _info['name'],
                                         '🔒 ยังไม่ได้ตั้งกุญแจห้องนี้ใน Secrets', dim=True)

    st.caption("กุญแจหลุดหรือสงสัยว่าหลุด : แจ้งผู้วิจัยเพื่อเปลี่ยนกุญแจเฉพาะห้องนั้น "
               "ใน Secrets แล้ว reboot แอป (ห้องอื่นไม่กระทบ)")


def page_room_settings():
    # 👤 production 19 ก.ค. 2026: เปิด/ปิดห้อง = ทุกคนใช้ได้ (รหัสหน่วยงาน) ·
    #    เฉพาะ 📥 นำเข้าข้อมูลย้อนหลัง ที่กันด้วยบทบาทผู้ดูแล (ดูท้ายฟังก์ชัน)
    # 🩹 7 ส.ค. 2026 (มุคกี้แจ้ง): เดิมหน้านี้ copy ลิสต์ห้องมาเขียนเองแค่ 8 ห้อง
    #    → ตกหล่น OR9 (98) ทั้งหน้า = เปิด/ปิดห้อง OR9 ไม่ได้เลย
    #    เป็นบั๊กพันธุ์เดียวกับ main_or_utilization ที่เคยลืม OR9 มาแล้ว
    #    → เลิก copy ถาวร ดึงจาก room_config เป็น single source of truth จุดเดียว
    ROOM_INFO = {
        _rm: {
            'name': RC_ROOM_INFO[_rm][0],
            'icon': SPECIALTY_ICON.get(RC_ROOM_INFO[_rm][1], '🚪'),
            'label': (f"{RC_ROOM_INFO[_rm][0]} · "
                      f"{SPECIALTY_FULL.get(RC_ROOM_INFO[_rm][1], RC_ROOM_INFO[_rm][1])} "
                      f"({RC_ROOM_INFO[_rm][1]})"),
            'desc': ROOM_DESC.get(_rm,
                                  'ห้องผ่าตัด' + SPECIALTY_FULL.get(
                                      RC_ROOM_INFO[_rm][1], RC_ROOM_INFO[_rm][1])),
        }
        for _rm in get_active_rooms() if _rm in RC_ROOM_INFO
    }
    # ★ ผูก ROOM_LIST กับ ROOM_INFO เสมอ — ถ้าใครเพิ่มห้องใน room_config
    #   แต่ลืมใส่ ROOM_INFO ห้องนั้นจะถูกข้ามเงียบ ๆ ดีกว่าหน้าพังทั้งหน้า
    ROOM_LIST = list(ROOM_INFO.keys())

    # page header — slim
    st.caption('เปิด/ปิด ห้องผ่าตัดที่ใช้งานวันนี้ : ห้องที่ปิดจะไม่แสดงบนบอร์ด')

    # ⚠️ 1 ส.ค. 2026: คำเตือนหลังบันทึก (เก็บใน session ให้รอด st.rerun) —
    #    ปิดห้องที่ยังมีเคสกำลังผ่า: ทำได้ แต่ต้องรู้ตัว
    _warn_rooms = st.session_state.pop('_room_close_warn', None)
    if _warn_rooms:
        st.warning("⚠️ ปิดห้องที่ยังมีเคสกำลังผ่าอยู่: " + ", ".join(_warn_rooms)
                   + " : เคสเดิมดำเนินต่อได้จนจบ แต่ห้องจะไม่รับเคสใหม่ "
                     "(การ์ดภาพรวมวันนี้แสดงป้าย 🔒 ปิดรับเคสใหม่)")

    all_inputs = {}

    # 📐 9 ส.ค. 2026 (มุคกี้สั่ง): เรียง 2 ช่องต่อแถว จากเดิมเต็มความกว้างห้องละแถว
    #    9 ห้อง = 9 แถว ต้องเลื่อนจอถึงจะเห็นปุ่มบันทึก · แบบใหม่เหลือ 5 แถว เห็นครบในจอเดียว
    #    สร้าง st.columns ใหม่ทุกแถวเพื่อให้การ์ดในแถวเดียวกันสูงเท่ากัน
    for _start in range(0, len(ROOM_LIST), 2):
        _cols = st.columns(2)
        for _col, rm in zip(_cols, ROOM_LIST[_start:_start + 2]):
            info = ROOM_INFO[rm]
            # Ensure room exists in session state
            if rm not in st.session_state.room_settings:
                st.session_state.room_settings[rm] = {
                    'enabled': True, 'name': info['name'],
                    'specialty': info['desc'], 'scrub': ['', ''], 'circ': ['', '', '', ''],
                    'nurses': [],
                }
            settings = st.session_state.room_settings[rm]
            if rm not in st.session_state.or_rooms:
                st.session_state.or_rooms[rm] = {
                    'status': 'ว่าง', 'current_case': None, 'start_time': None,
                    'predicted_time': None, 'override_time': None, 'is_emergency': False,
                    'staff': {'scrub': '', 'circulating': ''},
                    'name': info['name'], 'specialty': info['desc'],
                }
            with _col:
                _c1, _c2 = st.columns([3, 1.15], vertical_alignment="center")
                with _c1:
                    st.markdown(
                        f'<div style="background:#f8f9fa;padding:12px 16px;'
                        f'border-radius:10px;border-left:4px solid #3498db;">'
                        f'<b>{info["icon"]} {info["label"]}</b><br>'
                        f'<span style="color:#7f8c8d;font-size:var(--fs-meta);">'
                        f'{info["desc"]}</span></div>',
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
        # ⚠️ 1 ส.ค. 2026: ปิดห้องที่มีเคสกำลังผ่าบนบอร์ด → ฝากคำเตือนไว้โชว์หลัง rerun
        _active_room_nos = set()
        for _c in st.session_state.get('patient_cases', []):
            if _c.get('status') == 'in_or':
                _r = _c.get('or_room_assigned') or _c.get('room')
                try:
                    _active_room_nos.add(int(float(_r)))
                except (TypeError, ValueError):
                    pass
        _closed_active = [ROOM_INFO[_rm]['name']
                          for _rm, _ri in all_inputs.items()
                          if not _ri['enabled'] and _rm in _active_room_nos]
        if _closed_active:
            st.session_state['_room_close_warn'] = _closed_active
        st.rerun()

    # 🛠️ เครื่องมือผู้ดูแล (อัปโหลด CSV + ล้างกระดาน) ย้ายกลับไปหน้า 📋 ตารางผ่าตัด
    #    แล้ว (14 ก.ค. 2026 — render_csv_upload บนบอร์ด เหนือ ➕ เพิ่มเคส ·
    #    🗑️ ล้างกระดาน = ตัวเลือกใน expander อัปโหลด)

    # 🔗 ลิงก์ติดตั้งจอ (มุคกี้สั่ง 7 ส.ค. 2026 — one stop service)
    render_screen_links(ROOM_INFO)

    st.markdown("---")
    st.markdown("### 🤖 โมเดล AI + สถานะระบบ")
    render_system_status()

    # 📥 นำเข้าข้อมูลย้อนหลังเข้าฐานสถิติ (คืนแบบย่อ 19 ก.ค. 2026 — Maintenance เดิม
    #    ถูกถอด 14 ก.ค. แต่ยังต้องมีช่องเติมเคสรายเดือน เช่น มิ.ย.–ก.ค. ที่ขาด)
    #    ปลอดภัยเรื่องจริยธรรม: ส่วน fine-tune ถูกถอดจาก process_panel ถาวรแล้ว
    #    (ethics lock) — เหลือเฉพาะ นำเข้าเคส + เติมเวลาจริง + mask ชื่อ
    st.markdown("---")
    with st.expander("📥 นำเข้าข้อมูลย้อนหลังเข้าฐานสถิติ (เฉพาะผู้วิจัย) 🔒",
                     expanded=False):
        # 👤 เฉพาะบทบาทผู้ดูแล (login ด้วยรหัสผู้ดูแล) — ไม่ถามรหัสซ้ำ
        if st.session_state.get('role') != 'admin':
            st.info("🔒 ส่วนนี้สำหรับผู้วิจัย : ออกจากระบบแล้วเข้าใหม่"
                    "ด้วยรหัสผู้ดูแลระบบ")
        else:
            try:
                from process_panel import render_process_panel
                render_process_panel()
            except Exception as _pe:
                import traceback
                st.error(f"❌ โหลดส่วนนำเข้าไม่สำเร็จ: {_pe}")
                st.code(traceback.format_exc())


# ============================================================================
# PAGE 2: PLAN SCHEDULE
# ============================================================================

def parse_schedule_csv_to_cases(uploaded_file):
    """อ่านตารางผ่าตัด CSV/Excel (HIS — UTF-16 + quote ซ้อน หรือ CSV ปกติ) → list เคส
    พร้อมทำนายเวลา + ฟิลด์ flow (status='not_arrived') สำหรับโหลดเข้า OR Board ในขั้นตอนเดียว.
    📊 1 ส.ค. 2026: รองรับ .xls/.xlsx — Excel เก็บเป็นเซลล์ comma ในข้อความไม่ทำคอลัมน์เลื่อน
    (ปัญหา CSV จาก HIS ที่ไม่ครอบ quote) · อ่านทุกช่องเป็น text กัน HN เลขศูนย์นำหน้าหาย"""
    import csv as _csv
    import io as _io

    # ---- อ่านเป็น text (รองรับหลาย encoding) ----
    try:
        uploaded_file.seek(0)
        data = uploaded_file.getvalue() if hasattr(uploaded_file, 'getvalue') else uploaded_file.read()
    except (AttributeError, ValueError):
        return []

    # ---- 📊 ไฟล์ Excel? (ดูนามสกุล + magic bytes) → อ่านเป็นแถวตรง ๆ ด้วย pandas
    #      ข้าม two-pass parser (ท่านั้นไว้แกะ quote ซ้อนของ CSV จาก HIS เท่านั้น)
    #      แล้วไหลเข้าตัว map คอลัมน์/ทำนายชุดเดียวกันทุกอย่าง ----
    _fname = str(getattr(uploaded_file, 'name', '') or '').lower()
    _is_excel = (_fname.endswith(('.xls', '.xlsx'))
                 or (isinstance(data, (bytes, bytearray))
                     and (data[:4] == b'PK\x03\x04'                      # .xlsx (zip)
                          or data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')))  # .xls (OLE2)
    _excel_rows = None
    if _is_excel:
        try:
            # dtype=str = ทุกช่องเป็นข้อความ (HN ไม่โดนแปลงเป็นตัวเลข/วันที่ไม่ถูกสลับ)
            _df = pd.read_excel(_io.BytesIO(bytes(data)), dtype=str)
        except Exception:
            try:    # HIS บางรุ่น export .xls ที่ข้างในเป็นตาราง HTML → อ่านอีกวิธี
                _df = pd.read_html(_io.BytesIO(bytes(data)))[0].astype(str)
            except Exception:
                return []
        _excel_rows = ([[str(c) for c in _df.columns]]
                       + _df.fillna('').astype(str).values.tolist())

    text = None
    if _excel_rows is None:
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

    # ---- two-pass parse: แกะ quote ชั้นนอกของ HIS (no-op สำหรับ CSV ปกติ)
    #      📊 ไฟล์ Excel ข้ามส่วนนี้ — ได้แถวมาแล้วจาก pandas ----
    if _excel_rows is not None:
        rows = _excel_rows
    else:
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

        # 🛡️ 1 ส.ค. 2026: กันคอลัมน์เลื่อน (HIS ใส่ comma ในช่องหัตถการโดยไม่มี quote
        #    → ช่องแตก คอลัมน์ขยับ ข้อความวินิจฉัยไหลไปโผล่ช่องแพทย์ เช่น 'mass at buttock')
        #    ชื่อแพทย์ไทยต้องมีอักษรไทยเสมอ — ไม่มี = ถือว่าว่าง (บอร์ดแสดง '-')
        import re as _re
        surgeon_val = (get('surgeon') or '').strip()
        if surgeon_val and not _re.search(r'[ก-๙]', surgeon_val):
            surgeon_val = ''

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
        from fam_code import gen_fam_code
        _case_id = "CSV_" + _hl.md5(_seed.encode('utf-8')).hexdigest()[:10]
        case = {
            'id': _case_id, 'fam_code': gen_fam_code(_case_id),
            'hn': get('hn') or '', 'name': get('name') or 'ไม่ระบุ',
            'age': age_val, 'diagnosis': get('diagnosis') or '-',
            'procedure': (get('procedure') or 'UNKNOWN').strip().upper(),
            'anesthesia': '-', 'surgeon': surgeon_val, 'room': room_val,
            'division': get('division') or '75', 'ororder': order_val,
            'case_type': 'Emergency' if is_emer else 'Elective',
            'is_emergency': is_emer,
            'ward': ward_val,
            'sched_date': sched_date, 'sched_hour': sched_h, 'sched_min': sched_m,
            'is_tf': is_tf, 'is_after_note': is_after,
            'procnote': raw_note, 'predicted_min': None, 'confidence': None,
        }
        # 🔧 15 ก.ค. 2026: เดิมไม่ส่ง diagnosis/ward → โมเดล v2 ขาด feature
        #    (ทายเพี้ยนไปทางค่ากลางทุกเคสที่มาจาก CSV) — ส่งให้ครบเท่าที่ไฟล์มี
        pred = predict_surgical_time(
            case['procedure'], case['age'], case['surgeon'], case['division'],
            case['sched_hour'] if case['sched_hour'] < 23 else 9,
            diagnosis=case['diagnosis'] if case['diagnosis'] != '-' else '',
            ward=case['ward'])
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


# ============================================================================
# (page_plan_schedule ถูกถอดออก 4 ก.ค. 2026 — ไม่ถูก route จากเมนูแล้ว
#  งานอัปโหลด CSV ทำที่หน้า 📋 ตารางผ่าตัด (render_csv_upload → parse_schedule_csv_to_cases)
#  ต้องการคืน → ดู git history ก่อน commit "chore: ตัดโค้ดตาย")
# ============================================================================



# ============================================================================
# MAIN
# ============================================================================

# ═══════════════════════════════════════════════════════════════════════════
# 🛡️ กันเดารหัสผ่าน (11 ส.ค. 2026 · ผลการตรวจระบบข้อ 1)
# ───────────────────────────────────────────────────────────────────────────
# ปัญหา: แอปอยู่บน URL สาธารณะของ Streamlit Cloud + ใช้รหัสร่วมกันทั้งหน่วย
# แล้วเดาได้ไม่จำกัดครั้งโดยระบบไม่รู้ตัว
# กันสองชั้น เพราะชั้นเดียวไม่พอ:
#   ① ต่อ session (เบราว์เซอร์ที่นั่งกดอยู่) — พลาดครบโควตา = ล็อกชั่วคราว
#   ② ทั้งแอป — กันคนเลี่ยงชั้นแรกด้วยการเปิด session ใหม่ทุกครั้ง
#      ใช้แค่ "หน่วงเวลาตอบ" ไม่ล็อกทั้งระบบ เพราะห้ามกันพยาบาลตัวจริงเข้าใช้งาน
# ⛔ ไม่แตะ IP ตามกติกาข้อ 2 ของโปรเจกต์ (ทุกเครื่องออกเน็ตผ่าน NAT เดียวกัน
#    IP จึงแยกคนไม่ได้จริง แถมเป็นข้อมูลส่วนบุคคล)
# ═══════════════════════════════════════════════════════════════════════════
_LOGIN_MAX_TRY = 5          # พลาดกี่ครั้งต่อ session ถึงล็อก
_LOGIN_LOCK_SEC = 60        # ล็อกนานเท่าไร (ครั้งถัดไปคูณสอง สูงสุด 15 นาที)
_LOGIN_LOCK_MAX = 900
_GLOBAL_FAIL_WINDOW = 300   # นับความพยายามพลาดทั้งแอปย้อนหลังกี่วินาที
_GLOBAL_FAIL_LOG: list = []  # เวลา (monotonic) ของความพยายามที่พลาด — ทั้ง process


def _login_recent_global_fails() -> int:
    """จำนวนครั้งที่ 'ใครก็ตาม' กรอกรหัสผิดในหน้าต่างเวลาล่าสุด"""
    import time as _t
    _cut = _t.monotonic() - _GLOBAL_FAIL_WINDOW
    while _GLOBAL_FAIL_LOG and _GLOBAL_FAIL_LOG[0] < _cut:
        _GLOBAL_FAIL_LOG.pop(0)
    return len(_GLOBAL_FAIL_LOG)


def _login_lock_left() -> int:
    """เหลือถูกล็อกอีกกี่วินาที (0 = ไม่ได้ถูกล็อก)"""
    import time as _t
    _until = float(st.session_state.get('_login_lock_until') or 0.0)
    return max(0, int(round(_until - _t.monotonic())))


def _login_note_fail() -> None:
    """บันทึกว่ากรอกผิด 1 ครั้ง + ล็อกถ้าครบโควตา + หน่วงเวลาตอบ"""
    import time as _t
    _n = int(st.session_state.get('_login_fail_n') or 0) + 1
    st.session_state['_login_fail_n'] = _n
    _GLOBAL_FAIL_LOG.append(_t.monotonic())
    _g = _login_recent_global_fails()
    # หน่วงตอบเสมอ: ทำให้การไล่เดาอัตโนมัติช้าลงมาก แต่คนพิมพ์ผิดแทบไม่รู้สึก
    #   (ยิ่งทั้งแอปพลาดถี่ ยิ่งหน่วงนาน — เพดาน 3 วิ ไม่ให้กระทบคนใช้จริง)
    _t.sleep(min(3.0, 0.4 + 0.1 * _g))
    if _n >= _LOGIN_MAX_TRY:
        _rounds = _n - _LOGIN_MAX_TRY          # ล็อกรอบที่เท่าไร (0 = รอบแรก)
        _dur = min(_LOGIN_LOCK_SEC * (2 ** _rounds), _LOGIN_LOCK_MAX)
        st.session_state['_login_lock_until'] = _t.monotonic() + _dur
    if _g >= 20:
        # ผิดถี่ผิดปกติทั้งแอป — ทิ้งร่องรอยไว้ให้ผู้วิจัยเห็นใน log ของ Cloud
        print(f"[login] ⚠️ กรอกรหัสผิด {_g} ครั้งใน {_GLOBAL_FAIL_WINDOW//60} นาที "
              f"— อาจมีคนพยายามเดารหัส")


# ═══════════════════════════════════════════════════════════════════════════
# ⏳ สิทธิ์ผู้วิจัยหมดอายุเมื่อทิ้งไว้เฉย ๆ (11 ส.ค. 2026 · ตรวจระบบข้อ 5)
# ───────────────────────────────────────────────────────────────────────────
# จอในห้อง/จอรับ-ส่ง เปิดค้างทั้งวัน = ตั้งใจให้เป็นแบบนั้น ห้ามไปยุ่ง
# แต่สิทธิ์ 'admin' เห็นผลวิจัย ส่งออกข้อมูล และล้างข้อมูลได้ ถ้าเปิดค้างบน
# เครื่องส่วนกลางแล้วลืมออก คนถัดไปที่มานั่งได้สิทธิ์เต็มทันที → ให้หมดอายุเอง
# ═══════════════════════════════════════════════════════════════════════════
_ADMIN_IDLE_SEC = 45 * 60


def _touch_activity() -> None:
    """ประทับเวลา 'มีการใช้งานจริง' — เรียกตอน login และทุก action บนบอร์ด
    (ปุ่มบนบอร์ดอยู่ใน fragment ซึ่งไม่ทำให้ main() รันใหม่ จึงต้องประทับที่นั่นด้วย
    ดู _mark_board_dirty ใน main_or_pages.py — ไม่งั้นผู้วิจัยจะหลุดทั้งที่กำลังทำงาน)"""
    try:
        import time as _t
        st.session_state['_last_activity'] = _t.monotonic()
    except Exception:
        pass


def _enforce_idle_timeout() -> None:
    """ตัดสิทธิ์ admin ที่ทิ้งหน้าจอไว้นานเกิน — role อื่นไม่แตะ"""
    try:
        import time as _t
        if st.session_state.get('role') != 'admin':
            return
        _last = st.session_state.get('_last_activity')
        if _last is None:
            _touch_activity()
            return
        if (_t.monotonic() - float(_last)) < _ADMIN_IDLE_SEC:
            _touch_activity()   # หน้าถูกโหลดใหม่ = ยังใช้งานอยู่
            return
        for _k in ('authenticated', 'role', '_maint_unlocked', '_clear_unlocked',
                   '_last_activity'):
            st.session_state.pop(_k, None)
        st.session_state['_idle_logged_out'] = True
    except Exception as _ex:
        print(f"[auth] ตรวจ idle timeout ไม่สำเร็จ (ข้าม): {_ex}")


def _pwd_match(entered, expected) -> bool:
    """เทียบรหัสแบบเวลาคงที่ — ให้เหมือน token จอห้อง/จอญาติที่ใช้ hmac อยู่แล้ว
    (เทียบด้วย == จะตอบเร็ว/ช้าตามจำนวนตัวอักษรที่ตรง = ใบ้รหัสให้คนเดา)"""
    import hmac as _hmac
    if not expected:
        return False
    return _hmac.compare_digest(str(entered or ''), str(expected))


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
                "⛔ ระบบยังไม่ได้ตั้งรหัสผ่าน (app_password) : ปิดการเข้าถึงไว้ก่อนเพื่อความปลอดภัย\n\n"
                "ผู้วิจัย: ไปที่ Streamlit Cloud → App settings → Secrets แล้วเพิ่ม\n"
                "`app_password = \"รหัสที่ต้องการ\"` จากนั้น reboot แอป")
            return False
        # local dev (SQLite) — allow access · ถือเป็นผู้ดูแล (เครื่องพัฒนา)
        if not st.session_state.get('role'):
            st.session_state['role'] = 'admin'
            st.session_state['_maint_unlocked'] = True
            st.session_state['_clear_unlocked'] = True
        return True

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
        if st.session_state.pop('_idle_logged_out', False):
            st.info("⏳ ออกจากระบบอัตโนมัติ เพราะไม่มีการใช้งานนานเกิน "
                    f"{_ADMIN_IDLE_SEC // 60} นาที : เข้าสู่ระบบใหม่ได้เลย")
        st.markdown(
            '<div style="text-align:center;margin:60px 0 24px;">'
            '<div style="font-size:48px;">🔐</div>'
            '<div style="display:inline-block;margin:12px 0 4px;background:#eef4ff;'
            'color:#2563eb;font-size:var(--fs-meta);font-weight:600;padding:6px 16px;'
            'border-radius:999px;border:1px solid #d6e4ff;">🎓 ส่วนหนึ่งของงานวิจัย</div>'
            '<div style="font-size:24px;font-weight:700;color:#1f2937;'
            'margin-top:4px;">OR Flow</div>'
            '<div style="font-size:18px;color:#5b6b7b;margin-top:5px;'
            'line-height:1.5;">ระบบบริหารห้องผ่าตัดและทำนายเวลาผ่าตัดด้วย '
            'Machine Learning</div>'
            '<div style="font-size:var(--fs-meta);color:#90a0ae;margin-top:7px;'
            'line-height:1.5;">วิทยานิพนธ์ หลักสูตรพยาบาลศาสตรมหาบัณฑิต '
            'สาขาการบริหารการพยาบาล<br>ห้องผ่าตัดศัลยกรรมทั่วไป · '
            'โรงพยาบาลตำรวจ</div></div>',
            unsafe_allow_html=True)

        _lock_left = _login_lock_left()
        with st.form("login_form", clear_on_submit=False):
            pwd = st.text_input("รหัสผ่าน", type="password",
                                placeholder="••••••••",
                                label_visibility='collapsed',
                                disabled=bool(_lock_left))
            submit = st.form_submit_button(
                "🔓 เข้าสู่ระบบ", use_container_width=True, type='primary',
                disabled=bool(_lock_left))
            if submit and _lock_left:
                # 🛡️ ยังอยู่ในช่วงล็อก — ไม่ตรวจรหัสเลย (กันไล่เดาต่อ)
                st.error(f"⏳ กรอกผิดหลายครั้งเกินไป : ลองใหม่ในอีก {_lock_left} วินาที")
            elif submit:
                # 👤 role-based login (มุคกี้สั่ง 19 ก.ค. 2026 — production):
                #    app_password = ผู้ใช้ทั่วไป · admin_pin = ผู้ดูแล (Mukky)
                #    ใส่รหัสของตัวเองครั้งเดียวที่หน้านี้ — ไม่ถามซ้ำอีกทุกจุด
                _admin_pwd = None
                try:
                    from main_or_db import get_admin_pin as _gap
                    _admin_pwd = _gap()
                except Exception:
                    pass
                if _pwd_match(pwd, _admin_pwd):
                    st.session_state['authenticated'] = True
                    st.session_state['role'] = 'admin'
                    st.session_state['_maint_unlocked'] = True
                    st.session_state['_clear_unlocked'] = True
                    st.session_state['_login_fail_n'] = 0
                    _touch_activity()
                    st.rerun()
                elif _pwd_match(pwd, _pwd_set):
                    st.session_state['authenticated'] = True
                    st.session_state['role'] = 'user'
                    st.session_state['_login_fail_n'] = 0
                    _touch_activity()
                    st.rerun()
                else:
                    _login_note_fail()
                    _left = _login_lock_left()
                    if _left:
                        st.error(f"⏳ กรอกผิดหลายครั้งเกินไป : "
                                 f"ลองใหม่ในอีก {_left} วินาที")
                        st.rerun()   # เริ่มนับถอยหลัง + ปิดช่องกรอกทันที
                    else:
                        _n_left = _LOGIN_MAX_TRY - int(
                            st.session_state.get('_login_fail_n') or 0)
                        st.error("❌ รหัสผ่านไม่ถูกต้อง"
                                 + (f" (เหลืออีก {_n_left} ครั้งก่อนถูกล็อกชั่วคราว)"
                                    if _n_left <= 2 else ""))

        # 🖥️ แอป demo: แถบเหลือง-ดำเล็กบนหน้า login — "Demonstration mode"
        #    (มุคกี้สั่ง 2 ส.ค. 2026: เลิกใช้กรอบฟ้า st.info ให้เข้าชุดแถบใหญ่)
        try:
            if str(st.secrets.get('instance_mode', '')).lower() == 'demo':
                st.markdown(
                    '<div style="background:repeating-linear-gradient(45deg,'
                    '#FACC15 0 20px,#1F2937 20px 40px);border-radius:8px;'
                    'padding:8px 12px;text-align:center;margin:4px 0 10px 0;">'
                    '<span style="background:rgba(0,0,0,0.62);color:#FFFFFF;'
                    'font-size:18px;font-weight:800;letter-spacing:.5px;'
                    'padding:5px 18px;border-radius:6px;white-space:nowrap;">'
                    '🖥️ Demonstration mode</span></div>',
                    unsafe_allow_html=True)
                st.caption("รูปแบบการใช้งานเหมือนระบบจริงทุกประการ · "
                           "ข้อมูลการผ่าตัดเป็นข้อมูลสมมติ")
        except Exception:
            pass
        st.caption("🔑 รหัสผ่านจากเจ้าของระบบ — สำหรับบุคลากรที่ได้รับอนุญาตเท่านั้น")

    return False


def main():
    # ========================================================================
    # 🧪 2 ส.ค. 2026: รองรับเส้นทาง demo_app.py (ประตูที่สองของแอป DEMO)
    #    Python cache การ import → โค้ดระดับบนสุดของไฟล์นี้ไม่รันซ้ำใน rerun
    #    ต้องตั้ง page config + init session ที่นี่ด้วย (idempotent ทั้งคู่ —
    #    เส้นทางปกติที่รันไฟล์นี้ตรง ๆ ไม่กระทบ)
    # ========================================================================
    try:
        st.set_page_config(**_page_config_kwargs())
    except Exception:
        pass    # ถูกตั้งไปแล้วตอนรันไฟล์นี้ตรง ๆ (เรียกซ้ำใน run เดียวกันไม่ได้)
    init_session_state()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)   # CSS ต้องฉีดทุก run (เส้นทาง demo)
    # 🐛 5 ก.ย. 2026: เส้นทาง demo_app.py import โมดูลนี้ครั้งเดียว → inject_theme()
    #    ระดับโมดูลไม่รันซ้ำทุก rerun แอป DEMO จึงไม่มีธีมเลย (แท็บเป็นวงกลม radio
    #    ปุ่มใหญ่ ช่องว่างกว้าง) ทั้งที่ production ปกติ — ฉีดซ้ำใน main() ทุก run
    try:
        from ui_theme import inject_theme as _inject_theme_main
        _inject_theme_main()
    except Exception:
        pass

    # 🖥️ แถบเหลือง-ดำคาดหัว "ทุกหน้า" ของแอป DEMO (รวมหน้า login/จอญาติ/จอห้อง)
    try:
        _is_demo_app = str(st.secrets.get('instance_mode', '')).lower() == 'demo'
    except Exception:
        _is_demo_app = False
    if _is_demo_app:
        st.markdown(
            '<div style="background:repeating-linear-gradient(45deg,'
            '#FACC15 0 26px,#1F2937 26px 52px);border-radius:10px;'
            'padding:10px 14px;text-align:center;margin:0 0 10px 0;">'
            '<span style="background:rgba(0,0,0,0.62);color:#FFFFFF;'
            'font-size:20px;font-weight:800;letter-spacing:.5px;'
            'padding:4px 20px;border-radius:8px;white-space:nowrap;">'
            '🖥️ ระบบสาธิตการใช้งาน OR Flow</span></div>',
            unsafe_allow_html=True)

    # ========================================================================
    # 📺 โหมดจอญาติ (kiosk) — URL: ?view=family&k=<family_board_token>
    #    ดัก "ก่อน" password gate: ทีวีหน้า OR เห็นหน้าสถานะหน้าเดียวแล้วจบ (st.stop)
    #    ใครลบ query param ออก → ตกลงมาเจอหน้า login ตามปกติ (หน้าอื่นล็อกเหมือนเดิม)
    #    🔒 fail-closed: ไม่ได้ตั้ง family_board_token ใน secrets = โหมดนี้ปิดสนิท
    # ========================================================================
    try:
        _view = st.query_params.get('view', '')
    except Exception:
        _view = ''
    if _view == 'family':
        import hmac
        try:
            _fam_tok = str(st.secrets.get('family_board_token', '') or '')
        except Exception:
            _fam_tok = ''
        _k = str(st.query_params.get('k', '') or '')
        if _fam_tok and hmac.compare_digest(_k, _fam_tok):
            # 🟢 นับจอญาติเข้าแถบ "ใครออนไลน์" — ต้องเรียกที่นี่ เพราะเส้นทางนี้
            #    st.stop() ก่อนถึงจุด beat() ของเส้นทางปกติ (จอญาติ refresh เอง 30 วิ)
            try:
                from presence import beat as _presence_beat
                _presence_beat('family')
            except Exception as _fbx:
                print(f"[main] presence (จอญาติ) ข้าม: {_fbx}")
            from family_board import render_family_board
            render_family_board()
        else:
            st.error("📺 จอสถานะไม่พร้อมใช้งาน : กรุณาติดต่อเจ้าหน้าที่")
        st.stop()   # ⛔ จบที่นี่เสมอ — ไม่มีทางไปถึงเมนู/หน้าอื่น

    # ========================================================================
    # 🚪 โหมดจอประจำห้องผ่าตัด — URL: ?room=<เลขห้อง>&k=<token ของห้อง>
    #    (เคาะดีไซน์ 2 ส.ค. 2026 หลัก "ล็อกที่มือ ไม่ล็อกที่ตา")
    #    shortcut ติดตั้งค้างถาวรบนเครื่องในห้อง เปิดปุ๊บใช้ได้ ไม่ต้อง login
    #    เห็นทุกห้อง (read-only) · กดได้เฉพาะเคสห้องตัวเอง (เสร็จ/✏️เวลา/↩️)
    #    เมนูเหลือ 3 แท็บ · token รายห้องใน secrets [room_tokens] เพิกถอนรายห้องได้
    #    ทางหนีไฟ: เครื่องห้องเปิดลิงก์ปกติ + login รหัสหน่วยงาน = master ได้เสมอ
    # ========================================================================
    try:
        _room_q = str(st.query_params.get('room', '') or '')
    except Exception:
        _room_q = ''
    if _room_q and not st.session_state.get('authenticated'):
        import hmac as _hmac_r
        try:
            _rtoks = dict(st.secrets.get('room_tokens', {}))
        except Exception:
            _rtoks = {}
        _rtok = str(_rtoks.get(_room_q, '') or '')
        _rk = str(st.query_params.get('k', '') or '')
        try:
            _rn = int(float(_room_q))
        except (TypeError, ValueError):
            _rn = None
        if _rtok and _rn is not None and _hmac_r.compare_digest(_rk, _rtok):
            st.session_state['authenticated'] = True
            st.session_state['role'] = 'room'
            st.session_state['room_scope'] = _rn
        else:   # 🔒 fail-closed: ไม่ตั้ง token / token ผิด = เข้าไม่ได้
            st.error("🚪 จอประจำห้องไม่พร้อมใช้งาน : กรุณาติดต่อผู้วิจัย (Mukky)")
            st.stop()

    # ⏳ ตัดสิทธิ์ผู้วิจัยที่ทิ้งหน้าจอไว้นานเกิน — ต้องอยู่ "ก่อน" password gate
    #    เพื่อให้ตกลงไปเจอหน้า login ในรอบเดียวกัน ไม่ใช่รอบถัดไป
    _enforce_idle_timeout()

    # 🔒 Password gate ก่อนทุก action
    if not _check_password():
        st.stop()

    # Initialize DB on startup — ต่อไม่ได้ให้ขึ้นข้อความอ่านรู้เรื่อง ไม่ใช่ traceback แดงใส่พยาบาล
    # 🔌 10+ users: รันครั้งเดียวต่อ session พอ (เดิมรันทุก rerun = ยืม connection ฟรีทุก 30 วิ)
    try:
        if not st.session_state.get('_db_inited'):
            init_db()
            # 🔐 cloud ไม่มี staff_mapping.csv → ดึงจากตาราง staff_map มาเขียนไฟล์
            #    (โมเดลเห็นตัวแพทย์ + dropdown มีรายชื่อ) · เครื่อง รพ. มีไฟล์ = ข้ามเฉย ๆ
            try:
                from staff_map_sync import ensure_staff_mapping
                ensure_staff_mapping()
            except Exception as _sm_ex:
                print(f"[main] staff_map_sync ข้าม: {_sm_ex}")
            st.session_state['_db_inited'] = True
    except Exception as _db_err:
        st.error(
            "⛔ เชื่อมต่อฐานข้อมูลไม่สำเร็จ\n\n"
            "ลองกดรีเฟรชหน้า (F5) อีกครั้งใน 1 นาที : ถ้ายังไม่หาย "
            "แจ้งผู้วิจัย (Mukky) พร้อมภาพหน้าจอนี้")
        with st.expander("รายละเอียดทางเทคนิค (สำหรับผู้วิจัย)"):
            st.code(str(_db_err)[:600])
        st.stop()

    # 🟢 แถบ "ตอนนี้ใครออนไลน์อยู่บ้าง" (11 ส.ค. 2026 — มุคกี้สั่ง)
    #    beat ก่อน counts เสมอ ไม่งั้นเครื่องตัวเองหายไปจากยอด
    #    ⚠️ full run เกิดเฉพาะตอนมี interaction — เครื่องที่เปิดบอร์ดทิ้งไว้เฉย ๆ
    #    อาศัย beat() ใน _board_fragment / _room_focus_fragment ที่เด้งเองทุก 30 วิ
    try:
        from presence import beat as _presence_beat, chips_html as _presence_chips
        _presence_beat()
        _online_chips = _presence_chips()
    except Exception as _pres_err:
        print(f"[main] presence ข้าม: {_pres_err}")
        _online_chips = ''

    # ========================================================================
    # แถบเมนูบนสุด (แทน sidebar — กันปัญหา sidebar พับแล้วกางไม่ได้บน Streamlit Cloud)
    # ========================================================================
    _hdr_l, _hdr_r = st.columns([5, 1])
    with _hdr_l:
        from datetime import datetime as _dtm, timedelta as _td
        from datetime import timezone as _tzu
        _now_hdr = _dtm.now(_tzu(_td(hours=7))).strftime('%d/%m/%Y')
        # (ชิป DEMO เล็กในแถวนี้ถูกถอด 3 ส.ค. 2026 — แถบเหลืองดำ + หน้า login
        #  ประกาศชัดอยู่แล้ว ไม่ต้องย้ำซ้ำให้รกหัวจอ)
        # 🧹 5 ก.ย. 2026 (ชั้น A): แถบหัวเหลือเฉพาะสิ่งที่คู่มือรูปที่ 1 ระบุ —
        #    ป้ายโมเดล (ข้อ 1) + ป้ายออนไลน์ (ข้อ 2) · ชิปวิทยานิพนธ์/เวลาเปิดใช้/
        #    วันที่ ไม่มีใครใช้ระหว่างเวร (มีอยู่แล้วที่หน้า login และ ⚙️ ตั้งค่า)
        try:
            from ui_theme import compact_ui as _compact_ui
            _hdr_compact = _compact_ui()
        except Exception:
            _hdr_compact = False
        _hdr_extra = ('' if _hdr_compact else
                      '<span class="or-chip">🎓 ส่วนหนึ่งของวิทยานิพนธ์การบริหารทางการพยาบาล</span>')
        _hdr_extra2 = ('' if _hdr_compact else
                       '<span class="or-chip">🕗 OR Flow เปิดใช้งานเวลา 08:00–16:00 น.</span>'
                       f'<span class="or-chip">📅 ปรับล่าสุด {_now_hdr}</span>')
        st.markdown(
            '<div class="or-chips" style="margin-top:6px;">'
            + _hdr_extra
            + '<span class="or-chip">🤖 AI: thesis_ML_v2 · 13 features</span>'
            + _hdr_extra2
            + _online_chips
            + ('<span class="or-chip" style="background:#fff3e0;color:#e65100;">'
               '👤 ผู้วิจัย</span>'
               if st.session_state.get('role') == 'admin' else '')
            + (('<span class="or-chip" style="background:#e3f0fb;color:#1565c0;">'
                f'🚪 จอประจำห้อง {__import__("room_config").room_label(st.session_state.get("room_scope"))}'
                '</span>')
               if st.session_state.get('role') == 'room' else '')
            + '</div>',
            unsafe_allow_html=True,
        )
    with _hdr_r:
        # 🚪 โหมดจอห้อง: ไม่มีปุ่มออกจากระบบ (เข้าด้วย token ประจำเครื่อง ไม่ใช่ login)
        if (st.session_state.get('authenticated')
                and st.session_state.get('role') != 'room'):
            if st.button("🔒 ออกจากระบบ", use_container_width=True,
                         key='_logout_btn'):
                st.session_state['authenticated'] = False
                # 👤 ล้างบทบาท/กุญแจทั้งหมด — login ใหม่กำหนดบทบาทใหม่
                for _k in ('role', '_maint_unlocked', '_clear_unlocked'):
                    st.session_state.pop(_k, None)
                st.rerun()

    # เมนูหลัก = แท็บแนวนอนบนสุด · เก็บค่าใน URL ให้รอด refresh (รันเฉพาะหน้าที่เลือก)
    # 🤖 ผลวิจัย AI ซ่อนจากเมนู 14 ก.ค. 2026 (มุคกี้สั่ง "ซ่อนไปก่อน") —
    #    โค้ดหน้า (page_admin('ai')) + route ด้านล่างยังอยู่ครบ
    #    คืนเมนูเมื่อไร = เติม "🤖 ผลวิจัย AI" กลับใน list นี้บรรทัดเดียวจบ
    # 🎯 จอห้องผ่าตัดแบบโฟกัส — หน้าเดียว การตัดสินใจเดียว (Hick's Law ตาม skill)
    #    มุคกี้สั่ง 4 ส.ค. 2026: เปิดใช้ทั้ง demo และ production
    #    (พร้อม ✏️ แก้เวลา + คิวรอของห้อง — ตรงตามคู่มือข้อ 1.6)
    _room_focus_mode = st.session_state.get('role') == 'room'
    if _room_focus_mode:
        from main_or_pages import page_room_focus
        page_room_focus(st.session_state.get('room_scope'))
        st.stop()

    _page_options = ["📋 ตารางผ่าตัด", "🗓️ จัดคิว AI", "📊 ภาพรวมวันนี้",
                     "📈 สถิติย้อนหลัง", "📺 จอญาติ (Demo)", "⚙️ ตั้งค่า"]
    # 🚪 โหมดจอประจำห้อง: เหลือ 3 แท็บ (ทำงาน + รับรู้สถานการณ์ + ดูสถิติ)
    #    จัดคิว AI / จอญาติ / ตั้งค่า = สิทธิ์ master (จอรับ-ส่ง, หัวหน้าเวร) เท่านั้น
    if st.session_state.get('role') == 'room':
        _page_options = ["📋 ตารางผ่าตัด", "📊 ภาพรวมวันนี้", "📈 สถิติย้อนหลัง"]
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
    elif page == "🗓️ จัดคิว AI":
        from or_scheduler import page_scheduler
        page_scheduler()
    elif page == "📊 ภาพรวมวันนี้":
        page_admin('today')
    elif page == "📈 สถิติย้อนหลัง":
        page_admin('history')
    elif page == "🤖 ผลวิจัย AI":
        page_admin('ai')
    elif page == "📺 จอญาติ (Demo)":
        # 👀 พรีวิวหน้าจอญาติในแอปหลัก — พยาบาลเห็นชุดเดียวกับทีวีหน้า OR เป๊ะ ๆ
        #    (render เดียวกับ kiosk route ต่างแค่อยู่หลัง login และยังมีเมนูให้กดออก)
        from family_board import render_family_board
        render_family_board()
    elif page == "⚙️ ตั้งค่า":
        page_room_settings()


if __name__ == "__main__":
    main()
