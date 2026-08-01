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
  - 🎨 โหมดทีวี: แบนเนอร์ gradient + นาฬิกาสด + การ์ด fade-in + จุดสถานะเต้น + ECG
  - 🛗 auto-scroll: เคสเยอะจนล้นจอ → เลื่อนขึ้น-ลงเองช้า ๆ (ทีวีไม่มีเมาส์)
    เปิดเฉพาะ kiosk (?view=family) — แท็บพรีวิวในแอปพยาบาลไม่เลื่อนเอง
"""
import html
import json
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta, timezone

_BKK = timezone(timedelta(hours=7))
_THAI_DAYS = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
_THAI_MONTHS = ['', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
                'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']

# status ดิบบนบอร์ด → (ป้ายสำหรับญาติ, สีตัวอักษร, สีพื้นชิป, ขั้นที่ [0-4], ไอคอน)
# ขั้น: รอเรียก → เตรียมตัว → ผ่าตัด → พักฟื้น → จำหน่ายผู้ป่วย
_FAMILY_STATUS = {
    'not_arrived':  ('รอเรียกเข้าห้องผ่าตัด',      '#475569', '#f1f5f9', 0, '🕐'),
    'holding_pre':  ('เตรียมความพร้อมก่อนผ่าตัด',  '#9a6700', '#fdf3dd', 1, '📋'),
    'in_or':        ('กำลังผ่าตัด',                 '#1b7f4b', '#e6f6ec', 2, '⚕️'),
    'overrun':      ('กำลังผ่าตัด',                 '#1b7f4b', '#e6f6ec', 2, '⚕️'),  # 🔕 ไม่โชว์ "เกินเวลา" ให้ญาติ
    'holding_post': ('ผ่าตัดเสร็จแล้ว',             '#1565c0', '#e3f0fb', 3, '🛏️'),
    'recovery':     ('พักฟื้นหลังผ่าตัด',           '#6b21a8', '#f0e4fb', 3, '🛏️'),
    'discharged':   ('จำหน่ายผู้ป่วยแล้ว',           '#475569', '#eceff3', 4, '🏠'),
}
_STEPS = [('🕐', 'รอเรียก'), ('📋', 'เตรียมตัว'), ('⚕️', 'ผ่าตัด'),
          ('🛏️', 'พักฟื้น'), ('🏠', 'จำหน่ายผู้ป่วย')]

_CSS = """
<style>
/* 📺 kiosk: ซ่อน chrome ของ Streamlit ทั้งหมด */
[data-testid="stHeader"], [data-testid="stToolbar"],
[data-testid="stSidebar"], #MainMenu, footer {display:none !important;}
.stApp {background:linear-gradient(180deg,#eef7fb 0%,#f6f9fc 40%,#f8fafc 100%);}
.block-container {padding-top:1rem; padding-bottom:1rem; max-width:1760px;}

/* ── แบนเนอร์หัวจอ ── */
.fam-banner {background:linear-gradient(120deg,#0e7490 0%,#0891b2 45%,#2563eb 100%);
             border-radius:20px; padding:20px 30px; color:#fff;
             display:flex; justify-content:space-between; align-items:center; gap:16px;
             box-shadow:0 8px 24px rgba(8,145,178,.25);}
.fam-title {font-size:2.4rem; font-weight:800; margin:0; line-height:1.15;
            text-shadow:0 1px 3px rgba(0,0,0,.15);}
.fam-sub   {font-size:1.2rem; margin:.25rem 0 0 0; color:#e0f2fe;}
.fam-live  {display:inline-flex; align-items:center; gap:8px; background:rgba(255,255,255,.16);
            border:1px solid rgba(255,255,255,.35); border-radius:999px;
            padding:6px 16px; font-size:1.05rem; font-weight:700; white-space:nowrap;}
.fam-dot   {width:11px; height:11px; border-radius:50%; background:#4ade80;
            animation:famPulse 1.2s ease-in-out infinite;}
@keyframes famPulse {0%,100%{transform:scale(1);opacity:1} 50%{transform:scale(1.55);opacity:.55}}

/* ── ชิปสรุปยอด ── */
.fam-sum {display:flex; flex-wrap:wrap; gap:10px; margin:14px 2px 4px 2px;}
.fam-sumchip {border-radius:999px; padding:7px 18px; font-size:1.12rem; font-weight:700;
              background:#fff; border:1px solid #e2e8f0; color:#475569;
              box-shadow:0 1px 2px rgba(15,23,42,.05);}

/* ── การ์ดผู้ป่วย ── */
.fam-grid {display:grid; grid-template-columns:repeat(auto-fill, minmax(500px, 1fr));
           gap:14px; margin-top:.7rem;}
.fam-card {background:#fff; border:1px solid #e2e8f0; border-radius:18px;
           padding:18px 22px; box-shadow:0 2px 6px rgba(15,23,42,.06);
           animation:famUp .45s ease both;}
.fam-card.active {border:2px solid #86efac; animation:famUp .45s ease both, famGlow 2.4s ease-in-out infinite;}
@keyframes famUp {from{opacity:0; transform:translateY(14px)} to{opacity:1; transform:none}}
@keyframes famGlow {0%,100%{box-shadow:0 2px 6px rgba(15,23,42,.06)}
                    50%{box-shadow:0 0 0 6px rgba(34,197,94,.14), 0 2px 10px rgba(34,197,94,.25)}}
.fam-card:nth-child(1){animation-delay:.02s}.fam-card:nth-child(2){animation-delay:.06s}
.fam-card:nth-child(3){animation-delay:.10s}.fam-card:nth-child(4){animation-delay:.14s}
.fam-card:nth-child(5){animation-delay:.18s}.fam-card:nth-child(6){animation-delay:.22s}
.fam-card:nth-child(7){animation-delay:.26s}.fam-card:nth-child(8){animation-delay:.30s}
.fam-card:nth-child(n+9){animation-delay:.34s}

.fam-row1 {display:flex; justify-content:space-between; align-items:baseline; gap:12px;}
.fam-name {font-size:1.65rem; font-weight:700; color:#0f172a;}
.fam-hn   {font-size:1.1rem; color:#64748b; white-space:nowrap;}
.fam-chip {display:inline-flex; align-items:center; gap:9px; margin-top:10px;
           padding:8px 20px; border-radius:999px; font-size:1.3rem; font-weight:700;}
.fam-chipdot {width:10px; height:10px; border-radius:50%; background:#16a34a;
              animation:famPulse 1.2s ease-in-out infinite;}

/* ── ขั้นตอน: วงกลม + เส้นเชื่อม ── */
.fam-track {display:flex; align-items:flex-start; margin-top:16px;}
.st-col  {display:flex; flex-direction:column; align-items:center; width:64px; flex:none;}
.st-c    {width:38px; height:38px; border-radius:50%; display:flex; align-items:center;
          justify-content:center; font-size:1.05rem; background:#f1f5f9;
          border:2px solid #e2e8f0; filter:grayscale(1); opacity:.55;}
.st-c.done {background:#16a34a; border-color:#16a34a; color:#fff; filter:none; opacity:1;
            font-size:1.15rem; font-weight:800;}
.st-c.now  {background:#fff; border-color:#16a34a; filter:none; opacity:1;
            box-shadow:0 0 0 0 rgba(34,197,94,.5); animation:famRing 1.6s ease-out infinite;}
@keyframes famRing {0%{box-shadow:0 0 0 0 rgba(34,197,94,.45)} 100%{box-shadow:0 0 0 12px rgba(34,197,94,0)}}
.st-l    {font-size:.85rem; color:#94a3b8; margin-top:5px; text-align:center; line-height:1.1;}
.st-l.on {color:#15803d; font-weight:800;}
.st-line {flex:1; height:5px; border-radius:3px; background:#e2e8f0; margin-top:17px;}
.st-line.on {background:linear-gradient(90deg,#16a34a,#4ade80);}

/* ── หน้าว่าง + ท้ายจอ ── */
.fam-empty {text-align:center; padding:2.2rem 0 1rem 0;}
.fam-empty-txt {font-size:1.7rem; color:#475569; font-weight:600; margin-top:1rem;}
.fam-empty-sub {font-size:1.15rem; color:#94a3b8; margin-top:.4rem;}
.fam-foot  {font-size:1.02rem; color:#94a3b8; margin-top:1.5rem; text-align:center;}

/* 💓 เส้นชีพจร ECG */
.fam-ecg path {stroke-dasharray:640; stroke-dashoffset:640; animation:famEcg 3.2s linear infinite;}
@keyframes famEcg {to {stroke-dashoffset:-640;}}
</style>
"""

_ECG_SVG = """
<svg class="fam-ecg" width="640" height="110" viewBox="0 0 640 110" fill="none"
     xmlns="http://www.w3.org/2000/svg" style="max-width:92%;">
  <path d="M0 55 H180 L205 55 L220 20 L240 90 L255 40 L268 55 H400 L420 55 L432 35 L448 75 L460 55 H640"
        stroke="#0891b2" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

# 🛗 auto-scroll (เฉพาะจอทีวี): พัก 6 วิบนสุด → เลื่อนลงช้า ๆ → พัก 6 วิล่างสุด →
#    เลื่อนกลับขึ้น → วนซ้ำ · ถ้าเนื้อหาไม่ล้นจอ = ไม่เลื่อนเลย
#    (รันใน iframe ของ components.html → คุม scroll ของหน้าแม่ผ่าน window.parent)
_AUTOSCROLL_JS = """
<script>
(function () {
  var SPEED = 0.9;          // px ต่อเฟรม (~54px/วินาที) — ช้าพออ่านทัน
  var PAUSE_MS = 6000;      // หยุดพักบน/ล่างสุด
  var dir = 1, pauseUntil = Date.now() + PAUSE_MS, cached = null;

  // ทดสอบ "ดันจริง": เลื่อนได้จริงไหม (กัน element ที่ overflow แต่ scroll ไม่ขยับ)
  function canScroll(el) {
    if (!el || el.scrollHeight <= el.clientHeight + 60) return false;
    var b = el.scrollTop;
    el.scrollTop = b + 2;
    var ok = el.scrollTop !== b;
    el.scrollTop = b;
    return ok;
  }

  // หากล่อง scroll ของ Streamlit — ชื่อ element ต่างกันตามรุ่น จึงลองหลาย selector
  // แล้วปิดท้ายด้วยการไล่สแกน section/div ทั้งหน้า (ครอบคลุมรุ่นอนาคต)
  function find() {
    try {
      var P = window.parent.document;
      var sels = ['[data-testid="stMain"]', 'section.stMain', 'section.main',
                  '[data-testid="stAppViewContainer"]'];
      for (var i = 0; i < sels.length; i++) {
        var e = P.querySelector(sels[i]);
        if (canScroll(e)) return e;
      }
      var se = P.scrollingElement || P.documentElement;
      if (canScroll(se)) return se;
      var all = P.querySelectorAll('section,div');
      for (var j = 0; j < all.length; j++) { if (canScroll(all[j])) return all[j]; }
    } catch (err) {}
    return null;
  }

  function tick() {
    if (!cached || !cached.isConnected) cached = find();
    var el = cached;
    if (el && Date.now() > pauseUntil) {
      el.scrollTop += SPEED * dir;
      if (dir === 1 && el.scrollTop + el.clientHeight >= el.scrollHeight - 4) {
        dir = -1; pauseUntil = Date.now() + PAUSE_MS;
      } else if (dir === -1 && el.scrollTop <= 2) {
        dir = 1; pauseUntil = Date.now() + PAUSE_MS;
      }
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
</script>
"""

# นาฬิกาสด (JS เดินทุกวินาที) — แสดงในการ์ดขาว วางคู่แบนเนอร์
_CLOCK_HTML = """
<div style="font-family:'Source Sans Pro','Segoe UI',Tahoma,sans-serif; background:#ffffff;
            border:1px solid #e2e8f0; border-radius:20px; height:104px;
            display:flex; flex-direction:column; align-items:center; justify-content:center;
            box-shadow:0 8px 24px rgba(8,145,178,.12);">
  <div id="t" style="font-size:2.7rem; font-weight:800; color:#0e7490;
                     font-variant-numeric:tabular-nums; line-height:1;">--:--:--</div>
  <div style="font-size:.95rem; color:#94a3b8; margin-top:4px;">เวลาขณะนี้</div>
</div>
<script>
  function u(){
    const d = new Date();
    const p = n => String(n).padStart(2,'0');
    document.getElementById('t').textContent = p(d.getHours())+":"+p(d.getMinutes())+":"+p(d.getSeconds());
  }
  u(); setInterval(u, 1000);
</script>
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


def _track(step: int) -> str:
    """แถวขั้นตอน: วงกลมไอคอน 5 ขั้น + เส้นเชื่อม (ผ่านแล้ว=✓เขียว · ปัจจุบัน=วงแหวนเต้น)"""
    out = []
    for i, (icon, lbl) in enumerate(_STEPS):
        if i < step:
            c, l = 'st-c done', 'st-l'
            inner = '✓'
        elif i == step:
            c, l = 'st-c now', 'st-l on'
            inner = icon
        else:
            c, l = 'st-c', 'st-l'
            inner = icon
        out.append(f'<div class="st-col"><div class="{c}">{inner}</div>'
                   f'<div class="{l}">{lbl}</div></div>')
        if i < len(_STEPS) - 1:
            out.append(f'<div class="st-line{" on" if i < step else ""}"></div>')
    return '<div class="fam-track">' + ''.join(out) + '</div>'


def _card(c) -> str:
    """HTML การ์ด 1 เคส — ใช้เฉพาะ name/hn/status (mask มาแล้วจากต้นทาง)"""
    label, fg, bg, step, icon = _FAMILY_STATUS.get(c.get('status'),
                                                   _FAMILY_STATUS['not_arrived'])
    name = html.escape(str(c.get('name') or 'ไม่ระบุชื่อ'))
    hn = html.escape(str(c.get('hn') or ''))
    operating = c.get('status') in ('in_or', 'overrun')
    dot = '<span class="fam-chipdot"></span>' if operating else ''
    card_cls = 'fam-card active' if operating else 'fam-card'
    return (f'<div class="{card_cls}">'
            f'<div class="fam-row1"><span class="fam-name">{name}</span>'
            f'<span class="fam-hn">HN {hn}</span></div>'
            f'<span class="fam-chip" style="color:{fg};background:{bg};">'
            f'{dot}{icon} {label}</span>'
            f'{_track(step)}'
            f'</div>')


def _summary_chips(cases) -> str:
    """ชิปสรุปยอดรายสถานะ (โชว์เฉพาะที่มี) + ยอดรวม"""
    counts = {}
    for c in cases:
        label, fg, bg, _step, icon = _FAMILY_STATUS.get(c.get('status'),
                                                        _FAMILY_STATUS['not_arrived'])
        key = (label, fg, bg, icon)
        counts[key] = counts.get(key, 0) + 1
    chips = [f'<span class="fam-sumchip">👥 ทั้งหมด {len(cases)} ราย</span>']
    for (label, fg, bg, icon), n in counts.items():
        chips.append(f'<span class="fam-sumchip" style="color:{fg};background:{bg};'
                     f'border-color:transparent;">{icon} {label} {n}</span>')
    return '<div class="fam-sum">' + ''.join(chips) + '</div>'


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
    thai_date = (f"วัน{_THAI_DAYS[now.weekday()]}ที่ {now.day} "
                 f"{_THAI_MONTHS[now.month]} {now.year + 543}")

    col_banner, col_clock = st.columns([4.2, 1.1])
    with col_banner:
        st.markdown(
            f'<div class="fam-banner">'
            f'<div><p class="fam-title">🏥 สถานะผู้ป่วยผ่าตัดวันนี้</p>'
            f'<p class="fam-sub">ห้องผ่าตัดศัลยกรรมทั่วไป · {thai_date}</p></div>'
            f'<span class="fam-live"><span class="fam-dot"></span>อัปเดตอัตโนมัติ</span>'
            f'</div>',
            unsafe_allow_html=True)
    with col_clock:
        components.html(_CLOCK_HTML, height=112)

    cases, err = _load_today_cases()
    if err:
        st.markdown(
            f'<div class="fam-empty">{_ECG_SVG}'
            f'<p class="fam-empty-txt">⏳ ระบบกำลังปรับปรุงข้อมูล กรุณารอสักครู่</p>'
            f'<p class="fam-empty-sub">หรือสอบถามเจ้าหน้าที่หน้าห้องผ่าตัด</p></div>',
            unsafe_allow_html=True)
        return
    # กรองแถวว่าง (ไม่มีทั้งชื่อและ HN) — กันการ์ดเปล่าบนจอ
    cases = [c for c in cases if (c.get('name') or c.get('hn'))]
    if not cases:
        st.markdown(
            f'<div class="fam-empty">{_ECG_SVG}'
            f'<p class="fam-empty-txt">ระบบอยู่ระหว่างเตรียมเปิดใช้งาน</p>'
            f'<p class="fam-empty-sub">มีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่หน้าห้องผ่าตัด</p></div>',
            unsafe_allow_html=True)
        return

    st.markdown(_summary_chips(cases), unsafe_allow_html=True)
    st.markdown('<div class="fam-grid">' + ''.join(_card(c) for c in cases) + '</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="fam-foot">ข้อมูลอัปเดตอัตโนมัติทุก 30 วินาที · '
        'แสดงชื่อย่อและเลข HN 4 ตัวท้ายเพื่อคุ้มครองข้อมูลส่วนบุคคล · '
        'มีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่หน้าห้องผ่าตัด</p>',
        unsafe_allow_html=True)

    # 🛗 auto-scroll เฉพาะโหมดทีวี (?view=family) — แท็บพรีวิวในแอปไม่เลื่อนเอง
    #    ปิดชั่วคราวได้ด้วย &scroll=0 (เช่น เปิดตรวจงานบน notebook)
    try:
        _is_kiosk = st.query_params.get('view', '') == 'family'
        _no_scroll = st.query_params.get('scroll', '') == '0'
    except Exception:
        _is_kiosk, _no_scroll = False, False
    if _is_kiosk and not _no_scroll:
        components.html(_AUTOSCROLL_JS, height=0)
