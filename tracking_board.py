"""
tracking_board.py — กระดานติดตามเคสผ่าตัดแบบตารางเดียว (production tracking board)

ทุกเคส = 1 แถว · สถานะเป็นชิปสี · แถวไม่ย้ายที่เมื่อสถานะเปลี่ยน
ค้นหา/กรองห้อง/กรองสถานะ · layout ปุ่มต่อแถว: [✏️ แก้เวลา] [ปุ่มหลัก] [↩ ย้อนกลับ]

✏️ (มี ⓘ hover) แก้ "เวลาคาดการณ์ใช้ห้องผ่าตัด" — human override คนชนะ AI
⏱ เคสรอผ่าตัด: นาฬิกานับเดินหน้าสดฝังในแถว (ไม่กินบรรทัดเพิ่ม)
🚫 กันเข้าห้องซ้ำ: ห้องที่มีเคสกำลังผ่าอยู่ ปุ่ม "เข้าห้อง" กดไม่ได้จนกว่าเคสแรกจะออก
↩️ ย้อนสถานะกลับหนึ่งขั้น — ปุ่มเห็นตลอดท้ายแถว (ชี้ค้างบอกว่าย้อนเป็นอะไร)
"""
import html
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta, timezone

# ⚡ rerun เฉพาะ fragment บอร์ด (perf fix ก.ค. 2026) — บอร์ดถูกครอบด้วย
# st.fragment ใน main_or_pages แล้ว ปุ่มบนบอร์ดจึงต้องใช้ rerun_board แทน st.rerun
from main_or_core import rerun_board as _rerun_board

# 🕐 เวลามาตรฐานกรุงเทพ — กันเพี้ยนเมื่อ deploy บน cloud ต่าง timezone
_BKK = timezone(timedelta(hours=7))


def _now():
    return datetime.now(_BKK).replace(tzinfo=None)

# disp_key → (label, สีตัวอักษร, สีพื้นชิป, สีพื้นแถว)
_STATUS_META = {
    'not_arrived':  ('ยังไม่มา',     '#64748b', '#f1f5f9', ''),
    'holding_pre':  ('รอผ่าตัด',     '#9a6700', '#fdf3dd', '#fffcf3'),
    'in_or':        ('กำลังผ่า',     '#1b7f4b', '#e6f6ec', '#f4fbf7'),
    'overrun':      ('เกินเวลา',     '#c0392b', '#fbe9e8', '#fdf3f3'),
    'holding_post': ('ห้องรับ-ส่ง',  '#1565c0', '#e3f0fb', ''),
    'recovery':     ('ห้องพักฟื้น',  '#6b21a8', '#edd2ff', ''),   # 💜 สีวิสัญญี
    'discharged':   ('จำหน่ายแล้ว',  '#94a3b8', '#eceff3', '#f6f8fa'),
}

_STATUS_GROUP = {
    'not_arrived': 'ยังไม่มา', 'holding_pre': 'รอผ่าตัด',
    'in_or': 'กำลังผ่า', 'overrun': 'กำลังผ่า',
    'holding_post': 'รอจำหน่าย', 'recovery': 'รอจำหน่าย',
    'discharged': 'จำหน่ายแล้ว',
}

# สถานะ → ย้อนกลับไปเป็นอะไร (label สำหรับ tooltip ปุ่ม ↩)
_UNDO_TARGET = {
    'holding_pre': 'ยังไม่มา', 'in_or': 'รอผ่าตัด', 'overrun': 'รอผ่าตัด',
    'holding_post': 'กำลังผ่า', 'recovery': 'กำลังผ่า', 'discharged': 'รอจำหน่าย',
}

_EDIT_HELP = ("แก้เวลาคาดการณ์ใช้ห้องผ่าตัด (นาที) แทนค่า AI ได้ — "
              "เวลาใช้ห้องนับตั้งแต่ room in ถึง room out")

# CSS ไฟฉุกเฉิน: จุดแดงกะพริบแบบวงคลื่น (pulse ring) + ป้ายฉุกเฉิน
_EMG_CSS = (
    "@keyframes emgPulse{0%{box-shadow:0 0 0 0 rgba(224,49,46,.45)}"
    "70%{box-shadow:0 0 0 7px rgba(224,49,46,0)}"
    "100%{box-shadow:0 0 0 0 rgba(224,49,46,0)}}"
    ".emg-dot{display:inline-block;width:8px;height:8px;border-radius:50%;"
    "background:#e0312e;margin-right:5px;vertical-align:1px;"
    "animation:emgPulse 1.4s ease-out infinite}"
    ".emg-tag{color:#c0392b;background:#fbe9e8;border-radius:8px;padding:1px 8px;"
    "font-size:11.5px;font-weight:600;letter-spacing:.3px;margin-right:6px;"
    "white-space:nowrap;display:inline-block;vertical-align:1px}"
)
_EMG_BADGE = ('<span class="emg-dot"></span><span class="emg-tag">ฉุกเฉิน</span>'
              # 🚪 เคสฉุกเฉินอยู่นอกขอบเขตวิจัย (elective เท่านั้น) — ชิปเทาแจ้งจาง ๆ
              '<span style="color:#6b7280;background:#f3f4f6;border:1px solid #e5e7eb;'
              'border-radius:8px;padding:1px 7px;font-size:10.5px;margin-right:6px;'
              'white-space:nowrap;display:inline-block;vertical-align:1px;">'
              'นอกขอบเขตวิจัย</span>')

# 💜 ปุ่ม "เสร็จ → พักฟื้น" สีม่วงอ่อน #EDD2FF — สีประจำวิสัญญี (PACU อยู่ใต้วิสัญญี)
#    เลือกด้วย class st-key-tb_f2_* (Streamlit ≥1.37 ใส่ class ตาม key ให้อัตโนมัติ
#    — รุ่นเก่ากว่านั้นจะเป็นปุ่มขาวปกติ ไม่พัง)
_PACU_BTN_CSS = (
    '[class*="st-key-tb_f2_"] button{'
    'background:#EDD2FF !important;border:1px solid #D8B4FE !important;'
    'color:#5B2C87 !important;font-weight:600;}'
    '[class*="st-key-tb_f2_"] button:hover{'
    'background:#E2C0FC !important;border-color:#C084FC !important;'
    'color:#4A1D6E !important;}'
)


def _dur_str(m) -> str:
    """นาที → ข้อความอ่านง่าย: ≤60 = 'X น.' · เกิน = 'X ชม. Y น.' (มุคกี้สั่ง 19 ก.ค. 2026)"""
    try:
        m = int(round(float(m)))
    except (TypeError, ValueError):
        return '? น.'
    h, mm = divmod(m, 60)
    if h and mm:
        return f'{h} ชม. {mm} น.'
    return f'{h} ชม.' if h else f'{mm} น.'


def _is_emer(c):
    """เคสฉุกเฉิน/เร่งด่วน — ดูจาก flag หรือข้อความประเภทเคส (emergency/urgency)"""
    if c.get('is_emergency'):
        return True
    t = str(c.get('case_type') or c.get('op_type') or c.get('optype') or '').lower()
    return ('emer' in t) or ('urg' in t) or ('ฉุกเฉิน' in t) or ('เร่งด่วน' in t)


def _demo_fx_tb() -> bool:
    """🎨 ลูกเล่น UI (คู่กับ main_or_admin._demo_fx) — ยกเข้า production แล้ว
    (มุคกี้สั่ง 4 ส.ค. 2026 หลังเคาะ UX ครบ: ภาษาสี เหลือง=ปัญหาเวลา
    แดง=ฉุกเฉิน · ชิปนาฬิกา · 🔒 ล็อคคิว — ใช้เก็บภาพหน้าจอลงเล่มวิจัย)
    คงฟังก์ชันไว้เป็นสวิตช์จุดเดียว เผื่ออยากแยกพฤติกรรมสองแอปอีกในอนาคต"""
    return True


def _sched_order_html(c, tlabel):
    """🎨 demo: คอลัมน์ "นัด" แสดงลำดับคิว 🔒 ใต้เวลา (hover = ล็อคคิว)
    เงื่อนไขโชว์ล็อก (มุคกี้เคาะ 4 ส.ค. 2026):
    · เฉพาะเคสที่ลำดับมาจากไฟล์ HIS — เคสเพิ่ม Manual (99) ไม่ติดล็อก
    · เคส TF ไม่ติดล็อก ขึ้น TF เฉย ๆ (ตามหลังคิว = คิวยังไม่ล็อก)
    · เลขคิวในห้องเดียวกันซ้ำ (เช่นมา 1 ทั้งห้อง = HIS ยังไม่จัดคิว
      จะจัดหน้างานวันผ่าจริง) → ซ่อนล็อกทั้งห้อง กันเลขหลอกตา
    production แสดงเวลานัดเดิมล้วน (ยกเว้น hover TF — มีทั้งสองระบบ)"""
    base = tlabel(c)
    if c.get('is_tf'):
        # 🕓 TF hover (มุคกี้สั่ง 4 ส.ค. 2026): อธิบายความหมายทั้ง demo และ
        #    production — To Follow = ตามหลัง เริ่มเมื่อเคสก่อนหน้าในห้องเสร็จ
        return (f'<span title="TF = To Follow (ตามหลัง) — ไม่กำหนดเวลานัด '
                f'เริ่มผ่าเมื่อเคสก่อนหน้าในห้องเดียวกันเสร็จ" '
                f'style="cursor:help;">{base}</span>')
    if not _demo_fx_tb():
        return base
    try:
        o = int(c.get('ororder'))
    except (TypeError, ValueError):
        return base
    if not o or o == 99:
        return base
    # ลำดับ "มีความหมาย" เมื่อเลขในห้องไม่ซ้ำกัน — O(n) ต่อแถว บอร์ด ≤ ~30 เคส
    try:
        orders = []
        for x in (st.session_state.get('patient_cases') or []):
            if x.get('room') != c.get('room') or x.get('is_tf'):
                continue
            try:
                xo = int(x.get('ororder'))
            except (TypeError, ValueError):
                continue
            if xo and xo != 99:
                orders.append(xo)
        if len(orders) != len(set(orders)):
            return base
    except Exception:
        pass
    return (f'{base}<br><span title="ล็อคคิว — ลำดับจัดมาจากตารางผ่าตัด" '
            f'style="font-size:10.5px;color:#94a3b8;'
            f'white-space:nowrap;cursor:help;">🔒 คิว {o}</span>')


def _esc(v) -> str:
    """🔒 M-01: หนี HTML กันค่าจาก CSV (ชื่อ/หัตถการ/แพทย์) ฝัง <script> หรือทำการ์ดพังใน iframe"""
    return html.escape(str(v)) if v is not None else ''


def _pt_name(c) -> str:
    """ชื่อผู้ป่วยที่แสดงบนบอร์ด — mask เสมอ (นโยบาย 11 มิ.ย. 2026 · มาตรา 3.6.4):
    คำนำหน้า + ชื่อต้น + นามสกุลย่อ เช่น 'น.ส. ญาณิศา ส.' — ไม่มีโหมดชื่อเต็มอีกต่อไป"""
    nm = c.get('name') or '-'
    from main_or_db import mask_patient_name
    return _esc(mask_patient_name(nm))


def _pt_meta(c) -> str:
    """ข้อมูลระบุตัวรอง: HN — แสดง 4 ตัวท้ายเสมอ (มาตรา 3.6.4) · ไม่แสดงอายุ
    + รหัสรับบริการ (fam_code) ที่จอญาติใช้ — ให้เจ้าหน้าที่บอกญาติได้"""
    hn = c.get('hn') or ''
    from main_or_db import mask_hn
    _h = mask_hn(hn)
    meta = f"HN {_esc(_h)}" if _h else ''
    code = c.get('fam_code')
    if code:
        meta = (f"{meta} · รหัสรับบริการ {_esc(code)}" if meta
                else f"รหัสรับบริการ {_esc(code)}")
    return meta


def _dup_name_badges(cases, loc) -> dict:
    """หาเคสที่ 'ชื่อเต็มจริง' (ก่อน mask) ตรงกันเป๊ะกับเคส active อื่นวันนี้
    (ไม่รวมจำหน่ายแล้ว) — คืน {id(case): badge_html} กันหยิบผิดคนตอนชื่อชนกัน
    เทียบจากชื่อจริง ไม่ใช่ข้อความที่ mask แล้ว เพราะนามสกุลบนจอย่อเหลือตัวเดียว
    ชนกันโดยบังเอิญบ่อยมาก (มุคกี้ตัดสินใจ 9 ส.ค. 2026: เช็กแค่ชื่อเต็มตรงกันพอ)"""
    from collections import defaultdict
    groups = defaultdict(list)
    for c in cases:
        if c.get('status') == 'discharged':
            continue
        nm = (c.get('name') or '').strip()
        if nm and nm != 'ไม่ระบุ':
            groups[nm].append(c)
    badges = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        for c in group:
            other_rooms = sorted({str(loc(o)) for o in group if o is not c})
            rooms_txt = _esc(', '.join(other_rooms)) if other_rooms else ''
            badges[id(c)] = (
                f'<span title="ชื่อซ้ำกับอีกเคสวันนี้{(" · " + rooms_txt) if rooms_txt else ""}'
                f' · ตรวจ HN ก่อนดำเนินการ" style="display:inline-flex;align-items:center;'
                f'gap:6px;background:#fdf3dd;color:#9a6700;border-radius:999px;'
                f'padding:3px 12px;font-size:16px;font-weight:600;margin-left:7px;'
                f'white-space:nowrap;">👥 ชื่อซ้ำ{(" · " + rooms_txt) if rooms_txt else ""}</span>')
    return badges


def render_tracking_board(cases, do_arrive, do_enter, do_finish, do_undo,
                          loc, rid, tlabel, sched_min, room_opts=None,
                          mark_dirty=None):
    """วาดกระดานติดตามแบบ 3 โซนตามพื้นที่จริง (spec approve 3 ก.ค. 2026):
    🚪 ห้องรับ-ส่ง (ก่อนผ่า + หลังผ่ารอจำหน่าย) → 🏥 ห้องผ่าตัด → 🛏️ ห้องพักฟื้น
    + จำหน่ายแล้วพับท้ายบอร์ด · state machine เดิมทุกอย่าง แค่จัด render ใหม่
    room_opts = [(room_no, ชื่อห้อง)] ห้องที่เปิดใช้ — สำหรับ dropdown ย้ายห้องใน ✏️"""
    now = _now()
    room_opts = room_opts or []
    st.markdown(f'<style>{_EMG_CSS}{_PACU_BTN_CSS}</style>', unsafe_allow_html=True)

    # ---------- ค้นหา + กรอง ----------
    fc1, fc2, fc3 = st.columns([3, 1.4, 1.6])
    q = fc1.text_input("ค้นหา", key="tb_q", placeholder="ค้นหา ชื่อ / HN / หัตถการ",
                       label_visibility="collapsed")
    rooms_avail = sorted({loc(c) for c in cases})
    # 🚪🛏️ โซนกายภาพอยู่บนสุด (เหนือ OR1) — กรอง "ที่ที่ผู้ป่วยอยู่ตอนนี้" ไม่ใช่ห้องผ่า
    _Z_HOLD, _Z_RECOV = '🚪 ห้องรับ-ส่ง', '🛏️ ห้องพักฟื้น'
    # 🚪 โหมดจอประจำห้อง: seed ตัวกรองครั้งแรก = ห้องตัวเอง (สลับดูห้องอื่นได้ read-only)
    _scope_room = (st.session_state.get('room_scope')
                   if st.session_state.get('role') == 'room' else None)
    if _scope_room and not st.session_state.get('_tb_room_seeded'):
        try:
            from room_config import room_label as _rlbl
            _own_lbl = _rlbl(_scope_room)
            if _own_lbl in rooms_avail:
                st.session_state['tb_room'] = _own_lbl
        except Exception:
            pass
        st.session_state['_tb_room_seeded'] = True
    room_f = fc2.selectbox("ห้อง", ["ทุกห้อง", _Z_HOLD, _Z_RECOV] + rooms_avail,
                           key="tb_room", label_visibility="collapsed")
    status_f = fc3.selectbox("สถานะ", ["ทุกสถานะ", "ยังไม่มา", "รอผ่าตัด", "กำลังผ่า",
                                       "รอจำหน่าย", "จำหน่ายแล้ว"], key="tb_status",
                             label_visibility="collapsed")
    ql = (q or '').strip().lower()

    # ห้องที่มีเคสกำลังผ่าอยู่ → ห้ามเข้าห้องซ้ำ
    busy_rooms = {rid(c) for c in cases if c['status'] == 'in_or' and rid(c)}
    tov_map = _turnover_map()
    dup_badges = _dup_name_badges(cases, loc)

    # ---------- หัวตาราง ----------
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:4px 12px 6px;'
        'font-size:12.5px;font-weight:500;color:#64748b;">'
        '<span style="min-width:78px;">ห้อง</span>'
        '<span style="min-width:46px;">นัด</span>'
        '<span style="flex:1;">ผู้ป่วย · หัตถการ</span>'
        '<span style="min-width:80px;">สถานะ</span>'
        '<span style="min-width:110px;">เวลา</span></div>',
        unsafe_allow_html=True)

    # ---------- เตรียมแถว: กรอง + คำนวณสถานะแสดงผล ----------
    # เรียง ห้อง → ฉุกเฉินก่อนในห้อง → เวลานัด → ลำดับ (ลำดับนิ่ง แถวไม่ขยับเมื่อกดปุ่ม)
    ordered = list(enumerate(cases))
    # 🎨 เคสรอเกิน 60 นาทีลอยขึ้นบนสุด — ยกเข้า production แล้ว (4 ส.ค. 2026
    #    ตาม _demo_fx_tb: function เหมือน demo ทุกจุด)
    _demo_float = _demo_fx_tb()
    if _demo_float:
        # 🎨 มุคกี้ปรับ 3 ส.ค. 2026 รอบ 2: เด้งขึ้นบนสุด "เฉพาะ" เคสรอเกิน 60 นาที
        #    (แถวอื่นคงลำดับนิ่งตามหลักเดิมของบอร์ด)
        def _wait_m(c):
            _a = c.get('time_arrived_holding')
            try:
                return ((now - _a).total_seconds() / 60
                        if (_a is not None and hasattr(_a, 'hour')) else -1.0)
            except Exception:
                return -1.0
        def _crit(c):
            return c.get('status') == 'holding_pre' and _wait_m(c) > 60
        ordered.sort(key=lambda t: (
            0 if _crit(t[1]) else 1,
            -_wait_m(t[1]) if _crit(t[1]) else 0,
            (rid(t[1]) or 999),
            (0 if _is_emer(t[1]) else 1),
            (sched_min(t[1]) or 9999),
            t[1].get('ororder') or 999))
    else:
        ordered.sort(key=lambda t: ((rid(t[1]) or 999),
                                    (0 if _is_emer(t[1]) else 1),
                                    (sched_min(t[1]) or 9999),
                                    t[1].get('ororder') or 999))
    rows = []
    for idx, c in ordered:
        if c.get('status') == 'removed':
            continue   # 🗑️ tombstone — ถูกลบจากกระดานแล้ว (คง idx เดิมของเคสอื่นไว้)
        if ql and (ql not in str(c.get('name', '')).lower()
                   and ql not in str(c.get('hn', '')).lower()
                   and ql not in str(c.get('procedure', '')).lower()):
            continue
        if room_f == _Z_HOLD:
            if c['status'] not in ('not_arrived', 'holding_pre', 'holding_post'):
                continue
        elif room_f == _Z_RECOV:
            if c['status'] != 'recovery':
                continue
        elif room_f != 'ทุกห้อง' and loc(c) != room_f:
            continue

        eff = c.get('effective_min') or c.get('ai_predicted_min') or c.get('predicted_min') or 30
        eff = int(eff)
        disp = c['status']
        elapsed = None
        if disp == 'in_or':
            ent = c.get('time_entered_or')
            if ent is not None and hasattr(ent, 'hour'):
                elapsed = max(int((now - ent).total_seconds() / 60), 0)
                if elapsed > eff:
                    disp = 'overrun'
        if status_f != 'ทุกสถานะ' and _STATUS_GROUP.get(disp) != status_f:
            continue
        rows.append((idx, c, disp, eff, elapsed))

    if not rows:
        st.caption("ไม่พบเคสตามเงื่อนไขที่กรอง")
        return

    def _pick(*statuses):
        return [r for r in rows if r[2] in statuses]

    def _zone_head(title, n, color):
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;margin:14px 0 2px;'
            f'padding:6px 12px;background:#f8fafc;border-left:4px solid {color};'
            f'border-radius:0;font-size:14px;font-weight:700;color:#334155;">{title}'
            f'<span style="font-size:11.5px;font-weight:500;color:#94a3b8;">'
            f'{n} เคส</span></div>',
            unsafe_allow_html=True)

    def _sub_head(txt):
        st.markdown(f'<div style="font-size:12px;color:#94a3b8;margin:6px 0 0 4px;">'
                    f'{txt}</div>', unsafe_allow_html=True)

    def _rows(rs):
        for idx, c, disp, eff, elapsed in rs:
            _render_row(idx, c, disp, eff, elapsed, now, rid(c), busy_rooms,
                        do_arrive, do_enter, do_finish, do_undo, loc, tlabel,
                        room_opts, mark_dirty, tov_map, dup_badges)

    z_pre = _pick('not_arrived', 'holding_pre')
    z_or = _pick('in_or', 'overrun')
    z_post = _pick('holding_post')
    z_rec = _pick('recovery')
    z_done = _pick('discharged')
    # สถานะนอกเหนือ (snapshot รุ่นเก่า) — ไม่ให้เคสหายจากบอร์ด
    z_other = [r for r in rows if r[2] not in (
        'not_arrived', 'holding_pre', 'in_or', 'overrun',
        'holding_post', 'recovery', 'discharged')]

    # ---------- โซน 1: ห้องรับ-ส่ง ----------
    _zone_head('🚪 ห้องรับ-ส่ง', len(z_pre) + len(z_post), '#f1c40f')
    if z_pre:
        _sub_head('ก่อนผ่าตัด')
        _rows(z_pre)
    if z_post:
        _sub_head('หลังผ่าตัด — รอจำหน่าย')
        _rows(z_post)
    if not z_pre and not z_post:
        st.caption("ไม่มีผู้ป่วยในห้องรับ-ส่ง")

    # ---------- โซน 2: ห้องผ่าตัด ----------
    _zone_head('🏥 ห้องผ่าตัด', len(z_or), '#2196f3')
    _rows(z_or)
    # ห้องเปิดใช้ที่ยังว่าง — แถวจาง (เฉพาะตอนไม่ได้กรอง จะได้ไม่รกผลค้นหา)
    if room_f == 'ทุกห้อง' and status_f == 'ทุกสถานะ' and not ql:
        _busy_now = {rid(c1_) for _, c1_, d_, _, _ in z_or if rid(c1_)}
        _free = [(rn, lbl) for rn, lbl in room_opts if rn not in _busy_now]
        if _free:
            _names = ' · '.join(lbl for _, lbl in _free)
            st.markdown(
                f'<div style="border:1px dashed #e2e8f0;border-radius:10px;'
                f'padding:8px 12px;margin:4px 0;font-size:12.5px;color:#94a3b8;">'
                f'ห้องว่าง: {_names}</div>', unsafe_allow_html=True)
    elif not z_or:
        st.caption("ไม่มีเคสกำลังผ่าตัด")

    # ---------- โซน 3: ห้องพักฟื้น (💜 สีม่วง = วิสัญญี) ----------
    _zone_head('🛏️ ห้องพักฟื้น', len(z_rec), '#c084fc')
    if z_rec:
        _rows(z_rec)
    else:
        st.caption("ไม่มีผู้ป่วยพักฟื้น")

    if z_other:
        _rows(z_other)

    # ---------- จำหน่ายแล้ว (พับท้ายบอร์ด) ----------
    if z_done:
        with st.expander(f"✅ จำหน่ายแล้ววันนี้ ({len(z_done)} ราย)", expanded=False):
            _rows(z_done)


_CALL_LEAD_MIN = 30  # เวลาเตรียม/เคลื่อนย้ายผู้ป่วยก่อนห้องว่าง (นาที) สำหรับ Call next


@st.cache_data(ttl=1800)
def _turnover_map():
    """median turnover รายห้องจากข้อมูลจริง (fallback _global) — cache 30 นาที"""
    try:
        from main_or_db import get_room_turnover_map
        return get_room_turnover_map() or {}
    except Exception:
        return {}


def _band_halfwidth(eff):
    """ครึ่งความกว้างช่วง "ออกห้อง" แบบขั้นบันไดตามความยาวเคส (adaptive band)
    คาลิเบรตจาก |error| จริงของ thesis_ML บน hold-out ปี 2567 (n=1,939):
      ทำนาย <60 น.  → ±15 (ครอบจริง 66%)   · 60–120 → ±30 (58%)
      120–240      → ±45 (53%)             · >240   → ±60 (57%)
    ทุกกลุ่มครอบ ~5-6 ใน 10 เคสสม่ำเสมอ — ดีกว่า ±30 คงที่ที่ครอบเคสสั้นเกินจริง (88%)
    แต่เคสยาวผิดบ่อยกว่าถูก (22-39%)"""
    e = int(eff)
    return 15 if e < 60 else 30 if e < 120 else 45 if e < 240 else 60


def _callnext_html(c, eff, tov_map):
    """บรรทัด '🚪 ออกห้อง ~ช่วงเวลา · ⏰ Call next' — ออกห้องบอกเป็น "ช่วง" ไม่ใช่จุดเดียว
    ความกว้างช่วงปรับตามความยาวเคส (_band_halfwidth) · ช่วง 90% formal อยู่ในปุ่ม ✏️"""
    ent = c.get('time_entered_or')
    if ent is None or not hasattr(ent, 'hour'):
        return ''
    from datetime import timedelta as _td
    try:
        rm = int(float(c.get('room')))
    except (TypeError, ValueError):
        rm = None
    tov = (tov_map or {}).get(rm) or (tov_map or {}).get('_global') or 15
    _hw = _band_halfwidth(eff)
    lo_dt = ent + _td(minutes=max(int(eff) - _hw, 5))
    hi_dt = ent + _td(minutes=int(eff) + _hw)
    call_dt = ent + _td(minutes=int(eff) + float(tov) - _CALL_LEAD_MIN)
    return ('<div style="font-size:11px;color:#8a96a3;margin-top:2px;white-space:nowrap;" '
            f'title="ช่วงคาดการณ์ ±{_hw} นาที (กว้างตามความยาวเคส — คาลิเบรตจากเคสจริงปี 2567 '
            'ครอบราว 5-6 ใน 10 เคส) · ช่วงมั่นใจ 90% ของเคสนี้ดูในปุ่ม ✏️">'
            '🚪 ออกห้อง ~' + lo_dt.strftime('%H:%M') + '–' + hi_dt.strftime('%H:%M')
            + ' · <span style="color:#2f7d52;font-weight:600;">⏰ เรียกเคสถัดไป ~'
            + call_dt.strftime('%H:%M') + ' น.</span></div>')


def _time_cell(c, disp, eff, elapsed, now):
    ai0 = c.get('ai_predicted_min') or c.get('predicted_min')
    ov = c.get('user_override_min')
    if disp == 'overrun':
        over = elapsed - eff
        bar = (f'<span style="display:block;height:4px;background:#eef2f6;border-radius:2px;'
               f'overflow:hidden;margin-top:3px;"><span style="display:block;height:100%;'
               f'width:100%;background:#e24b4a;"></span></span>')
        return f'<span style="color:#c0392b;">{elapsed} / {eff} น. · เกิน {over}</span>{bar}'
    if disp == 'in_or':
        pct = min(int(elapsed / eff * 100) if eff else 50, 100)
        bar = (f'<span style="display:block;height:4px;background:#eef2f6;border-radius:2px;'
               f'overflow:hidden;margin-top:3px;"><span style="display:block;height:100%;'
               f'width:{pct}%;background:#22a565;"></span></span>')
        return f'<span style="color:#1b7f4b;">{elapsed} / {eff} น.</span>{bar}'
    if disp in ('holding_post', 'recovery'):
        ex = c.get('time_exited_or')
        return (f'เสร็จ {ex.strftime("%H:%M")}'
                if (ex is not None and hasattr(ex, 'hour')) else '—')
    if disp == 'discharged':
        dc = c.get('time_discharged')
        return (f'จำหน่าย {dc.strftime("%H:%M")}'
                if (dc is not None and hasattr(dc, 'hour')) else '—')
    # not_arrived
    if ov:
        return (f'<b style="font-weight:600;">{_dur_str(eff)}</b> '
                f'<span style="text-decoration:line-through;color:#94a3b8;'
                f'font-size:12px;">AI {_dur_str(ai0) if ai0 else "?"}</span>')
    # 🤖 หลักฐานบนแถว — จำนวนเคสอ้างอิง + ช่วง 90% (28 ก.ค. 2026: ตัดป้าย
    #    "มั่นใจ" heuristic ออก — ให้ช่วง conformal สื่อความไม่แน่นอนแทน
    #    เพราะมีการันตีเชิงสถิติ อธิบายที่มาในเล่มได้)
    _n = c.get('proc_n')
    _ev = ''
    if _n is not None:
        _bits2 = [f'จาก {int(_n)} เคส' if _n else 'ไม่มีเคสใกล้เคียง']
        _rng = c.get('predicted_range')
        if c.get('range_method') == 'conformal' and _rng:
            _bits2.append(f'ช่วง {int(_rng[0])}–{int(_rng[1])} น.')
        _clr = '#27ae60' if _n else '#e74c3c'
        _ev = (f'<br><span style="font-size:11px;color:{_clr};white-space:nowrap;" '
               f'title="ช่วง 90% = เคสลักษณะนี้ราว 9 ใน 10 ใช้เวลาอยู่ในช่วงนี้ · '
               f'ช่วงแคบ = ค่อนข้างแน่นอน · ช่วงกว้าง = เวลาแกว่งได้มาก '
               f'ควรเผื่อเวลา/ปรับด้วย ✏️">{" · ".join(_bits2)}</span>')
    return ('AI ทำนายการใช้ห้อง ~'
            + (_dur_str(ai0) if ai0 else '? น.') + _ev)


def _holding_row_iframe(c, loc, tlabel, now, dup_badge=''):
    """แถวรอผ่าตัดทั้งแถวเป็น HTML สด — นาฬิกานับเดินหน้าฝังในช่องเวลา (ไม่กินบรรทัดเพิ่ม)."""
    arr = c.get('time_arrived_holding')
    # ⏱ TZ-proof: คำนวณ "รอแล้วกี่วินาที" ฝั่ง Python (เวลา BKK สม่ำเสมอ)
    # แล้วให้ JS เดินต่อจากค่านี้ด้วย Date.now() ของเครื่องเอง (ไม่พึ่ง .timestamp()
    # ที่เพี้ยนเมื่อ server คนละ timezone) — ทุกเครื่องเห็นเลขเริ่มต้นเท่ากัน
    el0 = max((now - arr).total_seconds(), 0) if (arr is not None and hasattr(arr, 'hour')) else 0
    ov = c.get('user_override_min')
    ov_badge = ('<span style="background:#e3f0fb;color:#1565c0;border-radius:8px;'
                'padding:2px 10px;font-size:16px;margin-left:6px;">ปรับแล้ว</span>'
                if ov else '')
    emer = _is_emer(c)
    emg_html = _EMG_BADGE if emer else ''
    border_css = ('border:1px solid #f5c6c5;border-left:3px solid #e0312e;'
                  if emer else 'border:1px solid #eef2f6;')
    # 🎨 demo (มุคกี้เคาะ 4 ส.ค. 2026 รอบสุดท้าย): เกณฑ์เดียว = 60 นาที
    #    รอเกิน 60 → แถบเหลืองครีมทั้งแถว + ชิปนาฬิกาเปลี่ยนเป็นสีแดง
    #    แถบแดงทั้งแถวสงวนให้เคสฉุกเฉินเท่านั้น · production JS เดิมเป๊ะ
    if _demo_fx_tb():
        _js = (
            f'<script>var el0={el0:.0f},t0=Date.now(),t=document.getElementById("t"),'
            f'row=document.getElementById("row"),emer={1 if emer else 0};'
            'function u(){var el=el0+(Date.now()-t0)/1000,d=Math.floor(el/60),'
            'sec=Math.floor(el%60),c=d<60?"#22a565":"#e24b4a";'
            'if(d>=1440){t.textContent="⏱ รอนานมาก";t.style.background="#e24b4a";return}'
            't.style.background=c;'
            'if(!emer&&d>=60){row.style.background="#fff8e1";'
            'row.style.border="1px solid #f0deb0";'
            'row.style.borderLeft="3px solid #e3920b";}'
            't.textContent="⏱ รอแล้ว "+d+":"+String(sec).padStart(2,"0")}'
            'u();setInterval(u,1000)</script>'
        )
    else:
        _js = (
            f'<script>var el0={el0:.0f},t0=Date.now(),t=document.getElementById("t");'
            'function u(){var el=el0+(Date.now()-t0)/1000,d=Math.floor(el/60),'
            'sec=Math.floor(el%60),c=d<30?"#22a565":d<60?"#e3920b":"#e24b4a";'
            'if(d>=1440){t.textContent="⏱ รอนานมาก";t.style.background="#e24b4a";return}'
            't.style.background=c;'
            't.textContent="⏱ รอแล้ว "+d+":"+String(sec).padStart(2,"0")}'
            'u();setInterval(u,1000)</script>'
        )
    return (
        '<html><head><style>'
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:'IBM Plex Sans Thai','Sarabun','Segoe UI',sans-serif;background:transparent}"
        f"{_EMG_CSS}"
        '</style></head><body>'
        f'<div id="row" style="display:flex;align-items:center;gap:10px;{border_css}'
        f'background:{(("#fdeeee" if emer else "#ffffff") if _demo_fx_tb() else "#fffcf3")};'
        f'border-radius:10px;padding:9px 12px;">'
        f'<span style="min-width:96px;font-size:18px;font-weight:600;color:#1565c0;">{loc(c)}</span>'
        f'<span style="min-width:56px;font-size:16px;color:#64748b;">{_sched_order_html(c, tlabel)}</span>'
        f'<span style="flex:1;min-width:0;overflow:hidden;">'
        f'{emg_html}'
        f'<span style="font-size:20px;font-weight:600;color:#0f172a;">{_pt_name(c)}</span>'
        f'{dup_badge}'
        f'<span style="font-size:16px;color:#94a3b8;"> {_pt_meta(c)}</span><br>'
        f'<span style="font-size:16px;color:#64748b;white-space:nowrap;">'
        f'{_esc(c["procedure"])} · {_esc(c.get("surgeon", "-"))}</span></span>'
        f'<span style="min-width:104px;"><span style="background:#fdf3dd;color:#9a6700;'
        f'border-radius:10px;padding:4px 14px;font-size:16px;font-weight:500;white-space:nowrap;">รอผ่าตัด</span></span>'
        f'<span style="min-width:132px;"><span id="t" style="color:#fff;padding:3px 11px;'
        f'border-radius:8px;font-size:16px;font-weight:600;display:inline-block;'
        f'white-space:nowrap;"></span>{ov_badge}</span>'
        f'</div>'
        f'{_js}</body></html>'
    )


def _inroom_row_iframe(c, loc, tlabel, eff, emg_html, border_css, ov_badge, now,
                       callnext_html='', dup_badge=''):
    """แถวกำลังผ่าแบบสด (ลูกผสม — บอร์ดสงบ เคสมีปัญหาเด่นเอง):
    - ปกติ: โชว์นาทีล้วน '41 / 60 น.' สีเขียว เดินเองทุกนาที
    - ใกล้ครบ (เหลือ ≤5 นาที): สลับเป็น mm:ss สีส้ม
    - เกินเวลา: mm:ss สีแดง + 'เกิน m:ss' + ชิป/พื้นแถวเปลี่ยนแดงสด ไม่ต้อง refresh
    ⏱ TZ-proof: ส่ง 'ผ่าไปแล้วกี่วินาที' จาก Python (BKK) ให้ JS เดินต่อด้วย
    Date.now() ของเครื่อง — ไม่พึ่ง .timestamp() ที่เพี้ยนข้าม timezone"""
    ent = c.get('time_entered_or')
    el0 = max((now - ent).total_seconds(), 0) if (ent is not None and hasattr(ent, 'hour')) else 0
    # 🎨 demo (มุคกี้เคาะ 4 ส.ค. 2026): เอาแถบเขียวออก — แถวปกติพื้นขาว
    #    แถบสีสงวนไว้สื่อ "ปัญหา" เท่านั้น: เหลือง = เวลา · แดง = ฉุกเฉิน
    _emer = _is_emer(c)
    _bg = ('#fdeeee' if _emer else '#ffffff') if _demo_fx_tb() else '#f4fbf7'
    return (
        '<html><head><style>'
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:'IBM Plex Sans Thai','Sarabun','Segoe UI',sans-serif;background:transparent}"
        f"{_EMG_CSS}"
        '</style></head><body>'
        f'<div id="rw" style="display:flex;align-items:center;gap:10px;{border_css}'
        f'background:{_bg};border-radius:10px;padding:9px 12px;">'
        f'<span style="min-width:96px;font-size:18px;font-weight:600;color:#1565c0;">{loc(c)}</span>'
        f'<span style="min-width:56px;font-size:16px;color:#64748b;">{_sched_order_html(c, tlabel)}</span>'
        f'<span style="flex:1;min-width:0;overflow:hidden;">'
        f'{emg_html}'
        f'<span style="font-size:20px;font-weight:600;color:#0f172a;">{_pt_name(c)}</span>'
        f'{dup_badge}'
        f'<span style="font-size:16px;color:#94a3b8;"> {_pt_meta(c)}</span><br>'
        f'<span style="font-size:16px;color:#64748b;white-space:nowrap;">'
        f'{_esc(c["procedure"])} · {_esc(c.get("surgeon", "-"))}</span></span>'
        f'<span style="min-width:104px;"><span id="ch" style="background:#e6f6ec;color:#1b7f4b;'
        f'border-radius:10px;padding:4px 14px;font-size:16px;font-weight:500;white-space:nowrap;">กำลังผ่า</span></span>'
        f'<span style="min-width:180px;font-size:16px;">'
        f'<span id="t" style="color:#1b7f4b;font-weight:600;"></span>{ov_badge}'
        f'<span style="display:block;height:4px;background:#eef2f6;border-radius:2px;'
        f'overflow:hidden;margin-top:3px;"><span id="b" style="display:block;height:100%;'
        f'width:0%;background:#22a565;"></span></span>{callnext_html}</span>'
        f'</div>'
        f'<script>var el0={el0:.0f},t0=Date.now(),eff={int(eff)}'
        + (f',emer={1 if _emer else 0}' if _demo_fx_tb() else '') + ';'
        'var t=document.getElementById("t"),b=document.getElementById("b"),'
        'ch=document.getElementById("ch"),rw=document.getElementById("rw");'
        'function z(x){return String(x).padStart(2,"0")}'
        'function u(){var el=Math.floor(el0+(Date.now()-t0)/1000),'
        'm=Math.floor(el/60),ss=el%60,rem=eff*60-el;'
        'b.style.width=Math.min(el/(eff*60)*100,100)+"%";'
        'if(rem>300){t.textContent=m+" / "+eff+" น.";'
        't.style.color="#1b7f4b";b.style.background="#22a565";}'
        # 🎨 demo (มุคกี้ปรับ 3 ส.ค. 2026 รอบ 2): เวลาหลักเป็นนาทีล้วนเสมอ (MM/MM น.)
        #    ความละเอียด MM:SS โผล่เฉพาะส่วน "เกิน" ตอนเกินเวลาเท่านั้น · production เดิม
        + ('else if(rem>0){t.textContent=m+" / "+eff+" น.";'
           if _demo_fx_tb() else
           'else if(rem>0){t.textContent=m+":"+z(ss)+" / "+eff+" น.";')
        + 't.style.color="#e3920b";b.style.background="#e3920b";}'
        'else{var ov=-rem;'
        + ('t.textContent=m+" / "+eff+" น. · เกิน "+Math.floor(ov/60)+":"+z(ov%60);'
           if _demo_fx_tb() else
           't.textContent=m+":"+z(ss)+" / "+eff+" น. · เกิน "+Math.floor(ov/60)+":"+z(ov%60);')
        + 't.style.color="#c0392b";b.style.width="100%";b.style.background="#e24b4a";'
        'ch.textContent="เกินเวลา";ch.style.background="#fbe9e8";ch.style.color="#c0392b";'
        # 🎨 demo (มุคกี้เคาะ 4 ส.ค. 2026): ผ่าเกินเวลา = แถบเหลืองครีม
        #    (ภาษาเดียวกับรอนาน) · เคสฉุกเฉินคงแถบแดงไว้ ไม่ทับ · production เดิม
        + ('if(!emer){rw.style.background="#fff8e1";'
           'rw.style.border="1px solid #f0deb0";'
           'rw.style.borderLeft="3px solid #e3920b";}'
           if _demo_fx_tb() else
           'rw.style.background="#fdf3f3";')
        + '}}'
        'u();setInterval(u,1000)</script></body></html>'
    )


def _render_row(idx, c, disp, eff, elapsed, now, R, busy_rooms,
                do_arrive, do_enter, do_finish, do_undo, loc, tlabel,
                room_opts=None, mark_dirty=None, tov_map=None, dup_badges=None):
    room_opts = room_opts or []
    dup_badge = (dup_badges or {}).get(id(c), '')
    # 🚪 โหมดจอประจำห้อง ("ล็อกที่มือ ไม่ล็อกที่ตา"): เห็นทุกห้อง แต่กดได้เฉพาะ
    #    เคสห้องตัวเองตามเขตหน้าที่ — รับเข้า/เข้าห้อง/จำหน่าย/ย้ายห้อง = จอรับ-ส่ง
    _scope = (st.session_state.get('room_scope')
              if st.session_state.get('role') == 'room' else None)
    _own = (_scope is None) or (R == _scope)
    # .get + ค่า default — กัน KeyError ถ้าเจอสถานะแปลก (เช่น snapshot จากเวอร์ชันเก่า)
    label, fg, chipbg, rowbg = _STATUS_META.get(
        disp, (str(disp or 'ไม่ทราบสถานะ'), '#64748b', '#f1f5f9', ''))
    bg = rowbg if rowbg else '#ffffff'
    ov = c.get('user_override_min')
    ov_badge = ('<span style="background:#e3f0fb;color:#1565c0;border-radius:8px;'
                'padding:2px 10px;font-size:16px;margin-left:6px;">ปรับแล้ว</span>'
                if ov else '')
    # จำหน่ายแล้ว → แถบเทาจาง ทุกอย่างหรี่ลง (ไฟฉุกเฉินดับด้วย — เคสจบแล้ว ไม่รกตา)
    muted = (disp == 'discharged')
    emer = _is_emer(c) and not muted
    emg_html = _EMG_BADGE if emer else ''
    border_css = ('border:1px solid #f5c6c5;border-left:3px solid #e0312e;'
                  if emer else 'border:1px solid #eef2f6;')
    # 🎨 demo (มุคกี้เคาะ 4 ส.ค. 2026): แถบสี = ภาษาปัญหาเท่านั้น
    #    ฉุกเฉิน = แถบแดงอ่อน · เกินเวลา = แถบเหลืองครีม · แถวปกติพื้นขาว
    #    (แถบเขียว/ครีมประจำสถานะเอาออก) · จำหน่ายแล้วคงเทาหรี่ · production เดิม
    if _demo_fx_tb() and not muted:
        bg = ('#fdeeee' if emer
              else '#fff8e1' if disp == 'overrun' else '#ffffff')
    room_fg = '#b6c2cf' if muted else '#1565c0'
    name_fg = '#94a3b8' if muted else '#0f172a'
    sub_fg = '#b6c2cf' if muted else '#64748b'
    time_fg = '#b6c2cf' if muted else '#475569'

    # ---------- layout ต่อแถว: [แถว] [✏️] [ปุ่มหลัก] [↩] ----------
    c0, c1, c2, c3 = st.columns([8, 0.8, 1.5, 0.8])

    with c0:
        if disp == 'holding_pre':
            components.html(_holding_row_iframe(c, loc, tlabel, now, dup_badge), height=60)
        elif (disp in ('in_or', 'overrun')
              and c.get('time_entered_or') is not None
              and hasattr(c.get('time_entered_or'), 'timestamp')):
            # แถวกำลังผ่าแบบสด — นาฬิกาเดินหน้า + สลับเกินเวลาอัตโนมัติ
            components.html(
                _inroom_row_iframe(c, loc, tlabel, max(int(eff), 5),
                                   emg_html, border_css, ov_badge, now,
                                   _callnext_html(c, eff, tov_map), dup_badge),
                height=78)
        else:
            time_html = _time_cell(c, disp, eff, elapsed, now)
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;'
                f'{border_css}background:{bg};'
                f'border-radius:10px;padding:9px 12px;margin:2px 0;">'
                f'<span style="min-width:96px;font-size:18px;font-weight:600;color:{room_fg};">{loc(c)}</span>'
                f'<span style="min-width:56px;font-size:16px;color:{sub_fg};">{_sched_order_html(c, tlabel)}</span>'
                f'<span style="flex:1;min-width:0;overflow:hidden;">'
                f'{emg_html}'
                f'<span style="font-size:20px;font-weight:600;color:{name_fg};">{_pt_name(c)}</span>'
                f'{dup_badge if not muted else ""}'
                f'<span style="font-size:16px;color:#94a3b8;"> {_pt_meta(c)}</span><br>'
                f'<span style="font-size:16px;color:{sub_fg};white-space:nowrap;overflow:hidden;'
                f'text-overflow:ellipsis;display:inline-block;max-width:100%;">'
                f'{_esc(c["procedure"])} · {_esc(c.get("surgeon", "-"))}</span></span>'
                f'<span style="min-width:104px;"><span style="background:{chipbg};color:{fg};'
                f'border-radius:10px;padding:4px 14px;font-size:16px;font-weight:500;white-space:nowrap;">{label}</span></span>'
                f'<span style="min-width:132px;font-size:16px;color:{time_fg};">{time_html}{ov_badge}</span>'
                f'</div>',
                unsafe_allow_html=True)

    with c1:
        if disp in ('not_arrived', 'holding_pre', 'in_or', 'overrun') and _own:
            try:
                pop = st.popover("✏️", help=_EDIT_HELP)
            except TypeError:
                pop = st.popover("✏️")
            with pop:
                # 📊 ป้ายขอบเขตวิจัย — ถ้อยคำเดียวทุกกรณี (มุคกี้ปรับ 3 ส.ค. 2026)
                _out_scope = _is_emer(c)
                if not _out_scope:
                    try:
                        from research_log import in_research_scope as _irs
                        _out_scope = (not _irs(c)) and not c.get('_demo')
                    except Exception:
                        _out_scope = False
                if _out_scope:
                    st.caption('เคสที่ "อยู่นอกขอบเขตวิจัย" '
                               'จะไม่ถูกเก็บบันทึกเข้าข้อมูลวิจัย')
                st.caption("เวลาคาดการณ์ใช้ห้องผ่าตัด (นาที) — แก้แทนค่า AI ได้ "
                           "(เวลาใช้ห้องตั้งแต่ room in ถึง room out)")
                # 🤖 ที่มาของคำทำนาย — หลักฐานช่วยตัดสินใจว่าควรเชื่อ AI แค่ไหน
                _ai0 = c.get('ai_predicted_min') or c.get('predicted_min')
                if _ai0:
                    _bits = [f"🤖 AI {_dur_str(_ai0)}"]
                    if c.get('proc_n') is not None:
                        _nev = int(c.get('proc_n') or 0)
                        _bits.append(f"จาก {_nev} เคส" if _nev
                                     else "ไม่มีเคสใกล้เคียง")
                    st.caption(" · ".join(_bits))
                # 📏 ช่วงทำนาย 90% (split conformal — คาลิเบรตจากข้อมูลจริงปี 2567)
                _rng = c.get('predicted_range')
                if c.get('range_method') == 'conformal' and _rng:
                    st.caption(f"📏 โอกาส 9 ใน 10 เคสจะใช้เวลา "
                               f"{int(_rng[0])}–{int(_rng[1])} นาที")
                new_t = st.number_input("นาที", min_value=5, max_value=600,
                                        value=eff, key=f"tb_ov_{idx}",
                                        label_visibility="collapsed")
                # (dropdown "ส่งต่อหลังผ่า" ถอดออกแล้ว — ปลายทางเลือกจากปุ่ม
                #  "เสร็จ → รับ-ส่ง / พักฟื้น" บนแถวโดยตรง · spec 3 ก.ค. 2026)

                # 🔀 ย้ายห้อง — เลือกได้ทุกห้องที่เปิดใช้ (ชื่อล้วน ไม่มีรหัส)
                #    🚪 โหมดจอห้อง: ซ่อน — ย้ายห้อง = การจัดคิว ต้องผ่านจอรับ-ส่ง
                _new_room = None
                if room_opts and _scope is None:
                    _labels = [lbl for _, lbl in room_opts]
                    try:
                        _cur_rn = int(float(c.get('room')))
                    except (TypeError, ValueError):
                        _cur_rn = None
                    _cur_idx = next((i for i, (rn, _) in enumerate(room_opts)
                                     if rn == _cur_rn), 0)
                    st.caption("🔀 ย้ายห้อง")
                    _sel_lbl = st.selectbox("ย้ายห้อง", _labels, index=_cur_idx,
                                            key=f"tb_room_{idx}",
                                            label_visibility="collapsed")
                    _new_room = next((rn for rn, lbl in room_opts
                                      if lbl == _sel_lbl), _cur_rn)

                _room_changed = (_new_room is not None and _new_room != _cur_rn)
                if ((int(new_t) != eff or _room_changed)
                        and st.button("💾 บันทึก", key=f"tb_sv_{idx}",
                                      width='stretch')):
                    if int(new_t) != eff:
                        c['user_override_min'] = int(new_t)
                        c['effective_min'] = int(new_t)
                        try:
                            from main_or_db import log_override
                            log_override(c, int(new_t))
                        except Exception as _ex:
                            print(f"[override_log] log_override ล้มเหลว: {_ex}")
                    if _room_changed:
                        c['room'] = _new_room
                        c['or_room_assigned'] = _new_room
                    if mark_dirty:
                        mark_dirty(c)   # CR-2: ✏️ แก้เวลา/ย้ายห้อง ต้องเซฟขึ้นบอร์ดกลาง
                    try:    # 🎨 demo: ตอบรับทันที (Doherty)
                        from main_or_pages import _toast_ok
                        _toast_ok("บันทึกแล้ว ✓")
                    except Exception:
                        pass
                    _rerun_board()

                # 🌙 เคสที่ผ่าไปแล้วก่อนบอร์ดเปิด (เช่นฉุกเฉินกลางคืน) — มุคกี้สั่ง 19 ก.ค. 2026
                #    มีเฉพาะเคส "ยังไม่มา" · เคสที่เข้า flow แล้วใช้ปุ่มปกติ/↩️ ตามเดิม
                #    🚪 โหมดจอห้อง: ซ่อน (จำหน่ายก่อนบอร์ด/ลบเคส = งานจอรับ-ส่ง)
                if disp == 'not_arrived' and _scope is None:
                    st.markdown("---")
                    st.caption("🌙 เคสผ่าไปแล้วก่อนเปิดบอร์ด หรือไม่ต้องการบนกระดาน")
                    if st.button("✅ จำหน่ายแล้ว",
                                 key=f"tb_pd_{idx}", width='stretch',
                                 help="เคสผ่าเสร็จก่อนบอร์ดเปิด (เช่นเที่ยงคืน) — "
                                      "ย้ายพ้นคิว ไม่บันทึกเวลารอ/เวลาผ่า "
                                      "เพราะไม่ได้เดินผ่านบอร์ด"):
                        c['status'] = 'discharged'
                        c['done_before_board'] = True   # ธงกันสับสน — ไม่ใช่เคสเดินครบ flow
                        if mark_dirty:
                            mark_dirty(c)
                        _rerun_board()
                    _okdel = st.checkbox("ยืนยันลบเคสนี้ออกจากกระดาน",
                                         key=f"tb_delok_{idx}")
                    if st.button("🗑️ ลบออกจากกระดาน", key=f"tb_del_{idx}",
                                 width='stretch', disabled=not _okdel,
                                 help="นำเคสออกจากกระดานทุกเครื่อง — ไม่กระทบ"
                                      "ฐานข้อมูลสถิติ/วิจัยใด ๆ"):
                        # tombstone: คงเคสไว้แต่สถานะ 'removed' (ไม่แสดงทุกหน้า)
                        # — ลบทิ้งจริงจะโดนบอร์ดกลาง merge คืนชีพจากเครื่องอื่น
                        c['status'] = 'removed'
                        if mark_dirty:
                            mark_dirty(c)
                        _rerun_board()

    with c2:
        # 🚪 โหมดจอห้อง: รับเข้า/เข้าห้อง/จำหน่าย เป็นหน้าที่จอรับ-ส่ง — ไม่แสดง
        if disp == 'not_arrived' and _scope is None:
            if st.button("รับเข้า", key=f"tb_a_{idx}", width='stretch'):
                do_arrive(idx)
        elif disp == 'holding_pre' and _scope is None:
            _busy = R in busy_rooms
            if st.button("ห้องไม่ว่าง" if _busy else "เข้าห้อง", key=f"tb_e_{idx}",
                         type="secondary" if _busy else "primary",
                         width='stretch', disabled=_busy,
                         help=("ห้องนี้มีเคสกำลังผ่าอยู่ — ต้องกด 'ผ่าเสร็จ' "
                               "เคสแรกก่อนจึงเข้าห้องได้" if _busy else None)):
                if R in busy_rooms:
                    st.warning("ห้องนี้มีเคสกำลังผ่าอยู่")
                else:
                    do_enter(idx, R)
        elif disp in ('in_or', 'overrun') and _own:
            # ⑂ ผ่าเสร็จ 2 ปลายทาง — กดครั้งเดียวจบ ไม่ต้องเปิด popover เลือก dropdown
            if st.button("เสร็จ → รับ-ส่ง", key=f"tb_f_{idx}", type="primary",
                         width='stretch',
                         help="ผ่าเสร็จ · กลับห้องรับ-ส่ง เพื่อรอจำหน่าย"):
                do_finish(idx, R, "ห้องรับ-ส่ง")
            if st.button("เสร็จ → พักฟื้น", key=f"tb_f2_{idx}", width='stretch',
                         help="ผ่าเสร็จ · ไปห้องพักฟื้น เพื่อรอจำหน่าย"):
                do_finish(idx, R, "ห้องพักฟื้น")
        elif disp in ('holding_post', 'recovery') and _scope is None:
            if st.button("จำหน่าย", key=f"tb_d_{idx}", width='stretch'):
                if c.get('status') != 'discharged':  # กันกดรัว
                    c['status'] = 'discharged'
                    c['time_discharged'] = _now()
                    try:    # 📊 ตารางวิจัยถาวร (wait_post_min ครบตอนจำหน่าย)
                        from research_log import log_case_state
                        log_case_state(c)
                    except Exception as _rx:
                        print(f"[research_log] ข้าม: {_rx}")
                    if mark_dirty:
                        mark_dirty(c)   # CR-2: จำหน่าย ต้องเซฟขึ้นบอร์ดกลาง
                    try:    # 🎨 demo: ตอบรับทันที (Doherty)
                        from main_or_pages import _toast_ok
                        _toast_ok("จำหน่ายแล้ว ✓")
                    except Exception:
                        pass
                _rerun_board()

    with c3:
        # 🚪 โหมดจอห้อง: ↩️ ได้เฉพาะย้อนผลการกด "เสร็จ" ของห้องตัวเอง
        #    (ย้อนรับเข้า/เข้าห้อง/จำหน่าย เป็นของจอรับ-ส่ง)
        _undo_ok = (_scope is None) or (_own and disp in ('holding_post', 'recovery'))
        if disp in _UNDO_TARGET and _undo_ok:
            if st.button("↩️", key=f"tb_un_{idx}", width='stretch',
                         help=f"ย้อนกลับเป็น '{_UNDO_TARGET[disp]}' (กันกดพลาด)"):
                do_undo(idx)
