"""
family_board.py — 📺 จอสถานะสำหรับญาติผู้ป่วย (kiosk mode หน้าห้องผ่าตัด)

เปิดผ่าน URL: ?view=family&k=<family_board_token>  
หลักการ:
  - อ่าน board_state วันนี้จาก DB (ชุดเดียวกับบอร์ดพยาบาล) — read-only 100%
  - PDPA: payload ใน DB ถูก mask ตั้งแต่ต้นทางแล้ว (ชื่อต้น+นามสกุลย่อ · HN 4 ตัวท้าย)
    หน้านี้ "ไม่แสดง" การวินิจฉัย/หัตถการ/แพทย์/เวลา — สถานะอย่างเดียว
  - สถานะ overrun (เกินเวลา) แสดงเป็น "กำลังผ่าตัด" — ไม่ทำให้ญาติกังวล
  - แถวเรียงตามลำดับบนบอร์ดพยาบาล (ไม่สลับที่เมื่อสถานะเปลี่ยน — ญาติหาเจอง่าย)
  - refresh อัตโนมัติทุก 30 วิ (streamlit-autorefresh · fallback = JS reload)
"""
import html
import json
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta, timezone

_BKK = timezone(timedelta(hours=7))

# status ดิบบนบอร์ด → (ป้ายสำหรับญาติ, สีตัวอักษร, สีพื้นชิป, ขั้นที่ [0-4])
# ขั้น: รอเรียก → เตรียมตัว → ผ่าตัด → พักฟื้น → กลับหอผู้ป่วย
_FAMILY_STATUS = {
    'not_arrived':  ('รอเรียกเข้าห้องผ่าตัด',      '#475569', '#f1f5f9', 0),
    'holding_pre':  ('เตรียมความพร้อมก่อนผ่าตัด',  '#9a6700', '#fdf3dd', 1),
    'in_or':        ('กำลังผ่าตัด',                 '#1b7f4b', '#e6f6ec', 2),
    'overrun':      ('กำลังผ่าตัด',                 '#1b7f4b', '#e6f6ec', 2),  # 🔕 ไม่โชว์ "เกินเวลา" ให้ญาติ
    'holding_post': ('ผ่าตัดเสร็จแล้ว',             '#1565c0', '#e3f0fb', 3),
    'recovery':     ('พักฟื้นหลังผ่าตัด',           '#6b21a8', '#f0e4fb', 3),
    'discharged':   ('กลับหอผู้ป่วยแล้ว',           '#475569', '#eceff3', 4),
}
_STEP_LABELS = ['รอเรียก', 'เตรียมตัว', 'ผ่าตัด', 'พักฟื้น', 'กลับหอผู้ป่วย']

_CSS = """
<style>
/* 📺 kiosk: ซ่อน chrome ของ Streamlit ทั้งหมด */
[data-testid="stHeader"], [data-testid="stToolbar"],
[data-testid="stSidebar"], #MainMenu, footer {display:none !important;}
.block-container {padding-top:1.2rem; padding-bottom:1rem; max-width:1720px;}

.fam-title {font-size:2.6rem; font-weight:800; color:#0f172a; margin:0;}
.fam-sub   {font-size:1.25rem; color:#475569; margin:.2rem 0 1rem 0;}

.fam-grid {display:grid; grid-template-columns:repeat(auto-fill, minmax(520px, 1fr));
           gap:14px; margin-top:.6rem;}
.fam-card {background:#ffffff; border:1px solid #e2e8f0; border-radius:16px;
           padding:18px 22px; box-shadow:0 1px 3px rgba(15,23,42,.06);}
.fam-row1 {display:flex; justify-content:space-between; align-items:baseline; gap:12px;}
.fam-name {font-size:1.7rem; font-weight:700; color:#0f172a;}
.fam-hn   {font-size:1.15rem; color:#64748b; white-space:nowrap;}
.fam-chip {display:inline-block; margin-top:10px; padding:8px 20px;
           border-radius:999px; font-size:1.35rem; font-weight:700;}
.fam-steps {display:flex; gap:6px; margin-top:14px; align-items:center;}
.fam-step  {flex:1; height:8px; border-radius:4px; background:#e2e8f0;}
.fam-step.on {background:#16a34a;}
.fam-steplbl {display:flex; gap:6px; margin-top:4px;}
.fam-steplbl span {flex:1; font-size:.82rem; color:#94a3b8; text-align:center;}
.fam-steplbl span.on {color:#16a34a; font-weight:700;}

.fam-empty {font-size:1.6rem; color:#64748b; text-align:center; padding:4rem 0;}
.fam-foot  {font-size:1.05rem; color:#94a3b8; margin-top:1.4rem; text-align:center;}
</style>
"""


def _load_today_cases():
    """อ่านบอร์ดกลางวันนี้จาก DB — คืน (cases:list, err:str|None) · read-only"""
    today = datetime.now(_BKK).date().isoformat()
    try:
        from main_or_db import load_board_state
        raw = load_board_state(today)
        if not raw:
            return [], None
        payload = json.loads(raw)
        if payload.get('date') != today:
            return [], None                      # ของวันอื่น — ไม่แสดง
        return payload.get('cases', []) or [], None
    except Exception as ex:
        return [], str(ex)[:200]


def _card(c) -> str:
    """HTML การ์ด 1 เคส — ใช้เฉพาะ name/hn/status (mask มาแล้วจากต้นทาง)"""
    label, fg, bg, step = _FAMILY_STATUS.get(c.get('status'), _FAMILY_STATUS['not_arrived'])
    name = html.escape(str(c.get('name') or 'ไม่ระบุชื่อ'))
    hn = html.escape(str(c.get('hn') or ''))
    bars = ''.join(f'<div class="fam-step{" on" if i <= step else ""}"></div>'
                   for i in range(len(_STEP_LABELS)))
    lbls = ''.join(f'<span class="{"on" if i == step else ""}">{s}</span>'
                   for i, s in enumerate(_STEP_LABELS))
    return (f'<div class="fam-card">'
            f'<div class="fam-row1"><span class="fam-name">{name}</span>'
            f'<span class="fam-hn">HN {hn}</span></div>'
            f'<span class="fam-chip" style="color:{fg};background:{bg};">{label}</span>'
            f'<div class="fam-steps">{bars}</div>'
            f'<div class="fam-steplbl">{lbls}</div>'
            f'</div>')


def render_family_board():
    """📺 หน้าจอญาติ — เรียกจาก kiosk route ใน main_or_app.main() เท่านั้น"""
    # ⏱ refresh อัตโนมัติทุก 30 วิ — fallback: JS สั่ง reload ทั้งหน้า
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=30_000, key='_family_refresh')
    except Exception:
        components.html(
            "<script>setTimeout(()=>window.parent.location.reload(), 30000);</script>",
            height=0)

    st.markdown(_CSS, unsafe_allow_html=True)

    now = datetime.now(_BKK)
    thai_date = f"{now.day}/{now.month}/{now.year + 543}"
    st.markdown(
        f'<p class="fam-title">🏥 สถานะผู้ป่วยผ่าตัดวันนี้</p>'
        f'<p class="fam-sub">ห้องผ่าตัดศัลยกรรมทั่วไป · {thai_date} · '
        f'ข้อมูล ณ เวลา {now.strftime("%H:%M")} น.</p>',
        unsafe_allow_html=True)

    cases, err = _load_today_cases()
    if err:
        st.markdown('<p class="fam-empty">⏳ ระบบกำลังปรับปรุงข้อมูล กรุณารอสักครู่<br>'
                    'หรือสอบถามเจ้าหน้าที่หน้าห้องผ่าตัด</p>', unsafe_allow_html=True)
        return
    # กรองแถวว่าง (ไม่มีทั้งชื่อและ HN) — กันการ์ดเปล่าบนจอ
    cases = [c for c in cases if (c.get('name') or c.get('hn'))]
    if not cases:
        st.markdown('<p class="fam-empty">ระบบอยู่ระหว่างเตรียมเปิดใช้งาน</p>',
                    unsafe_allow_html=True)
        return

    st.markdown('<div class="fam-grid">' + ''.join(_card(c) for c in cases) + '</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="fam-foot">ข้อมูลอัปเดตอัตโนมัติทุก 30 วินาที · '
        'แสดงชื่อย่อและเลข HN 4 ตัวท้ายเพื่อคุ้มครองข้อมูลส่วนบุคคล · '
        'มีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่หน้าห้องผ่าตัด</p>',
        unsafe_allow_html=True)
