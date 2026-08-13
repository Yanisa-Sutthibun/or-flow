"""
tracking_board.py — กระดานติดตามเคสผ่าตัดแบบตารางเดียว (production tracking board)

ทุกเคส = 1 แถว · สถานะเป็นชิปสี · แถวไม่ย้ายที่เมื่อสถานะเปลี่ยน
ค้นหา/กรองห้อง/กรองสถานะ · layout ปุ่มต่อแถว: [✏️ แก้เวลา] [ปุ่มหลัก] [↩ ย้อนกลับ]

✏️ (มี ⓘ hover) แก้ "เวลาทำนายใช้ห้องผ่าตัด" — human override คนชนะ AI
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

_EDIT_HELP = ("แก้เวลาทำนายใช้ห้องผ่าตัด (นาที) แทนค่า AI ได้ — "
              "เวลาใช้ห้องนับตั้งแต่ room in ถึง room out")

# CSS ไฟฉุกเฉิน: จุดแดงกะพริบแบบวงคลื่น (pulse ring) + ป้ายฉุกเฉิน
_EMG_CSS = (
    "@keyframes emgPulse{0%{box-shadow:0 0 0 0 rgba(224,49,46,.45)}"
    "70%{box-shadow:0 0 0 7px rgba(224,49,46,0)}"
    "100%{box-shadow:0 0 0 0 rgba(224,49,46,0)}}"
    ".emg-dot{display:inline-block;width:8px;height:8px;border-radius:50%;"
    "background:#e0312e;margin-right:5px;vertical-align:1px;"
    "animation:emgPulse 1.4s ease-out infinite}"
    ".emg-tag{color:#c0392b;background:#fbe9e8;border-radius:10px;padding:4px 14px;"
    "font-size:18px;font-weight:600;letter-spacing:.3px;margin-right:8px;"
    "white-space:nowrap;display:inline-block;vertical-align:1px}"
)
_EMG_BADGE = ('<span class="emg-dot"></span><span class="emg-tag">ฉุกเฉิน</span>'
              # 🚪 เคสฉุกเฉินอยู่นอกขอบเขตวิจัย (elective เท่านั้น) — ชิปเทาแจ้งจาง ๆ
              '<span style="color:#6b7280;background:#f3f4f6;border:1px solid #e5e7eb;'
              'border-radius:10px;padding:4px 14px;font-size:18px;margin-right:8px;'
              'white-space:nowrap;display:inline-block;vertical-align:1px;">'
              'นอกขอบเขตวิจัย</span>')

# 💜 ปุ่ม "เสร็จ → พักฟื้น" สีม่วงอ่อน #EDD2FF — สีประจำวิสัญญี (PACU อยู่ใต้วิสัญญี)
#    เลือกด้วย class st-key-tb_f2_* (Streamlit ≥1.37 ใส่ class ตาม key ให้อัตโนมัติ
#    — รุ่นเก่ากว่านั้นจะเป็นปุ่มขาวปกติ ไม่พัง)
_PACU_BTN_CSS = (
    # 📐 9 ส.ค. 2026: ปุ่มบนแถวบอร์ดแคบลง (คืนพื้นที่ให้คอลัมน์เวลา) — ลด padding
    #    แนวนอนและขนาดตัวอักษรลงเล็กน้อย เพื่อให้ "เสร็จ → รับ-ส่ง" ยังอยู่บรรทัดเดียว
    #    ไม่ตัดคำ (ถ้าตัดคำ ปุ่มจะสูงขึ้นแล้วหลุดแนวกับแถว)
    '[class*="st-key-tb_"] button{padding:8px 6px !important;font-size:16px !important;'
    'white-space:nowrap !important;}'
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
        return (f'<span title="TF = To Follow (ตามหลัง) : ไม่กำหนดเวลานัด '
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
    # 14px: บรรทัดล่างของคอลัมน์นัด เป็นข้อมูลรอง — ขนาดเดียวกับ HN ใต้ชื่อผู้ป่วย
    return (f'{base}<br><span title="ล็อคคิว : ลำดับจัดมาจากตารางผ่าตัด" '
            f'style="font-size:14px;color:#94a3b8;'
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
        # 📐 9 ส.ค. 2026: ย่อคำเป็น "รหัส" + tooltip — คอลัมน์ผู้ป่วยในบอร์ดตาราง
        #    กว้างจำกัด คำเต็มทำให้รหัสจริงโดนตัดหาย ซึ่งเป็นตัวที่ต้องอ่านออก
        _c = (f'<span title="รหัสผู้รับบริการ : ใช้บอกญาติ ตรงกับที่ขึ้นจอสถานะ" '
              f'style="cursor:help;">รหัส {_esc(code)}</span>')
        meta = f"{meta} · {_c}" if meta else _c
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
                f'padding:4px 14px;font-size:18px;font-weight:600;margin-left:7px;'
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
    # 🔔 เคส "คิวถัดไปที่ต้องเรียก" ของแต่ละห้อง + เวลาเรียก (AI/ที่แก้)
    #    คำนวณสดทุกรอบ — ยังไม่กดเรียก/ไม่แก้มือ เวลาจึงขยับตามสถานการณ์จริงเอง
    try:
        from call_queue import next_call_map
        call_map = next_call_map(cases, now, tov_map)
    except Exception as _cx:
        print(f"[call_queue] คำนวณคิวเรียกไม่สำเร็จ (บอร์ดทำงานต่อ): {_cx}")
        call_map = {}

    # ---------- หัวตาราง ----------
    # 📐 ต้องวางใน st.columns สัดส่วนเดียวกับแถว ([8, .8, 1.5, .8] ใน _render_row)
    #    ไม่งั้นหัวคอลัมน์จะเหลื่อมกับข้อมูลข้างล่าง (เดิมวาดเต็มความกว้าง = เหลื่อมอยู่)
    _hc0, _hc1, _hc2, _hc3 = st.columns(_BOARD_COLS)
    with _hc0:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;padding:2px 12px 7px;'
            'font-size:13px;font-weight:700;color:#94a3b8;letter-spacing:.7px;'
            'border-bottom:2px solid #e2e8f0;margin-bottom:4px;">'
            f'<span style="width:{_COL_RM}px;flex:none;">ห้อง</span>'
            f'<span style="width:{_COL_Q}px;flex:none;">นัด</span>'
            f'<span style="width:{_COL_NM}px;flex:none;">ผู้ป่วย</span>'
            '<span style="flex:1;min-width:0;">หัตถการ / ศัลยแพทย์</span>'
            f'<span style="width:{_COL_ST}px;flex:none;text-align:center;">สถานะ</span>'
            f'<span style="width:{_COL_TM}px;flex:none;text-align:right;">เวลา</span>'
            '</div>',
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
        """หัวข้อกลุ่มบนบอร์ด — แบบ A (เคาะ 9 ส.ค. 2026): แถบสีตั้งหน้าหัวข้อ
        + เส้นคาดใต้เต็มความกว้าง · เดิม 18px เท่าเนื้อหาพอดี หัวข้อเลยจมหาย
        (ชุดเดียวกับ ui_theme.render_section แต่รับสีประจำโซนมาจากผู้เรียก
        จึงเขียน inline — inline style ทำ ::before ไม่ได้ ใช้ span ซ้อนแทน)"""
        st.markdown(
            f'<div style="display:flex;align-items:baseline;justify-content:space-between;'
            f'gap:12px;border-bottom:2px solid #e2e8f0;padding:0 2px 9px;margin:26px 0 12px;">'
            f'<span style="position:relative;padding-left:15px;'
            f'font-size:var(--fs-section);font-weight:700;color:#0f172a;'
            f'letter-spacing:-.4px;">'
            f'<span style="position:absolute;left:0;top:.18em;bottom:.18em;width:5px;'
            f'border-radius:3px;background:{color};"></span>{title}</span>'
            f'<span style="font-size:var(--fs-meta);font-weight:500;color:#64748b;'
            f'white-space:nowrap;">{n} เคส</span></div>',
            unsafe_allow_html=True)

    def _sub_head(txt):
        st.markdown(f'<div style="font-size:var(--fs-meta);color:#94a3b8;'
                    f'margin:6px 0 0 4px;">{txt}</div>', unsafe_allow_html=True)

    def _rows(rs):
        for idx, c, disp, eff, elapsed in rs:
            _render_row(idx, c, disp, eff, elapsed, now, rid(c), busy_rooms,
                        do_arrive, do_enter, do_finish, do_undo, loc, tlabel,
                        room_opts, mark_dirty, tov_map, dup_badges, call_map)

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
                f'padding:10px 16px;margin:4px 0;font-size:18px;color:#94a3b8;">'
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


# ⏰ เวลาเตรียม/เคลื่อนย้ายผู้ป่วยก่อนห้องว่าง (นาที) สำหรับ Call next —
#    ย้ายค่าไปไว้ที่ call_queue.py (13 ส.ค. 2026) ให้ระบบเรียกคิวใช้เลขเดียวกัน
from call_queue import CALL_LEAD_MIN as _CALL_LEAD_MIN


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




# ════════════════════════════════════════════════════════════════════════════
# 📐 บอร์ดแบบตาราง (มุคกี้เคาะ 9 ส.ค. 2026 — ดู docs/wireframe_board_table.html)
# ════════════════════════════════════════════════════════════════════════════
# ปัญหาเดิม: แต่ละแถวจัดวางอิสระ ชื่อผู้ป่วย/หัตถการ/ชิป ไหลตามความยาวข้อความ
# ไม่ตรงกันสักแถว ตาต้องอ่านใหม่ทีละแถว = เกะกะ · แนวทางบอร์ด OR จริง (Epic
# OpTime status board, LiveData) คือ "คอลัมน์ตรงกันทุกแถว + สถานะบอกด้วยสี"
#
# กติกา:
#   · ทุกคอลัมน์ตรึงความกว้าง ยกเว้น "หัตถการ/ศัลยแพทย์" ที่ยืดได้คอลัมน์เดียว
#   · หัตถการล็อกบรรทัดเดียว ยาวเกินตัด "…" (ชี้ค้างเห็นเต็ม) → ทุกแถวสูงเท่ากัน
#     = บอกความสูง iframe ล่วงหน้าได้แม่น ไม่มีเนื้อหาโดนกรอบตัดทิ้งเงียบ ๆ
#   · แก้ความกว้างที่ค่าคงที่ด้านล่างที่เดียว — หัวตารางกับแถวใช้ชุดเดียวกัน
#     ถ้าแก้ไม่ครบ คอลัมน์จะเหลื่อมทันที
#   · คอลัมน์เวลากว้างเป็นพิเศษ เพราะเป็นที่อยู่ของผลลัพธ์ AI ซึ่งเป็นหัวใจของงาน:
#     บรรทัดบน = เวลาที่ใช้/เกินไปกี่นาที · บรรทัดล่าง = ออกห้อง ~ช่วง + เรียกเคสถัดไป
#     (9 ส.ค. 2026 มุคกี้ทัก: เคยย้ายสองอย่างนี้ไปเป็น tooltip = หายไปจากสายตา ห้ามทำอีก)
#     (คำเต็ม "ออกห้อง ~HH:MM-HH:MM · เรียกคิวถัดไป ~HH:MM" ต้องพอดีบรรทัดเดียว
#      ที่ 13px = ~292px · ถ้าย่อคอลัมน์นี้ลงอีก ข้อความจะโดนตัดหายทันที)
_COL_RM, _COL_Q, _COL_NM, _COL_ST, _COL_TM = 88, 58, 150, 108, 292
# สัดส่วนคอลัมน์ Streamlit ต่อแถว: [เนื้อแถว, ✏️, ปุ่มหลัก, ↩️]
#   9 ส.ค. 2026: หั่นปุ่มลง (8/.8/1.5/.8 -> 10/.7/1.35/.7) คืนพื้นที่ ~6% ให้เนื้อแถว
#   เพื่อขยายคอลัมน์เวลา — เดิม 'เกินไปกี่นาที' ถูกกรอบตัดหาย
#   ⚠️ หัวตารางกับแถวต้องใช้ค่านี้ตัวเดียวกัน ไม่งั้นหัวคอลัมน์เหลื่อมกับข้อมูล
_BOARD_COLS = [10, 0.7, 1.35, 0.7]
_ROW_H = 70                 # ความสูงแถว (px) — iframe ต้องสูงกว่านี้เล็กน้อย
_ROW_IFRAME_H = _ROW_H + 8


def _cell_room(c, loc, fg='#1565c0'):
    """ห้อง: ชื่อห้องบรรทัดบน · สาขาบรรทัดล่าง — เดิม 'OR7 · PLASTIC' บรรทัดเดียว
    ยาวจนล้นไปชนคอลัมน์ถัดไป"""
    head, _, sub = str(loc(c) or '').partition(' · ')
    _sub = (f'<span style="display:block;font-size:14px;font-weight:500;color:#94a3b8;'
            f'line-height:1.2;letter-spacing:.3px;white-space:nowrap;overflow:hidden;'
            f'text-overflow:ellipsis;">{_esc(sub)}</span>') if sub else ''
    return (f'<span style="width:{_COL_RM}px;flex:none;overflow:hidden;">'
            f'<span style="display:block;font-size:20px;font-weight:600;color:{fg};'
            f'line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
            f'{_esc(head)}</span>{_sub}</span>')


def _cell_q(c, tlabel, emer=False):
    """นัด/คิว — เคสฉุกเฉินแทนที่ด้วยป้ายฉุกเฉิน (ย้ายมาจากคอลัมน์ผู้ป่วย ซึ่งเดิม
    ป้ายกว้างจนเบียดชื่อ) · เหตุผลที่อยู่นอกขอบเขตวิจัยย้ายไปเป็น tooltip"""
    if emer:
        return (f'<span style="width:{_COL_Q}px;flex:none;font-size:15px;color:#c0392b;'
                f'font-weight:600;white-space:nowrap;overflow:hidden;cursor:help;" '
                f'title="เคสฉุกเฉิน : อยู่นอกขอบเขตวิจัย (เก็บเฉพาะ elective ในเวลา)">'
                f'<span class="emg-dot"></span>ฉุกเฉิน</span>')
    return (f'<span style="width:{_COL_Q}px;flex:none;font-size:16px;color:#64748b;'
            f'line-height:1.25;white-space:nowrap;overflow:hidden;">'
            f'{_sched_order_html(c, tlabel)}</span>')


def _cell_patient(c, dup_badge='', fg='#0f172a'):
    """ผู้ป่วย: ชื่อ (mask แล้ว) บรรทัดบน · HN + รหัสรับบริการ บรรทัดล่าง"""
    return (f'<span style="width:{_COL_NM}px;flex:none;overflow:hidden;">'
            f'<span style="display:block;font-size:18px;font-weight:600;color:{fg};'
            f'line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
            f'{_pt_name(c)}{dup_badge}</span>'
            f'<span style="display:block;font-size:14px;color:#94a3b8;line-height:1.2;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
            f'{_pt_meta(c)}</span></span>')


def _cell_op(c, fg='#334155'):
    """หัตถการ/ศัลยแพทย์ — คอลัมน์เดียวของตารางที่ยืดได้ (กินพื้นที่ที่เหลือทั้งหมด)"""
    _p = _esc(c.get('procedure') or '-')
    _d = _esc(c.get('surgeon') or '-')
    return (f'<span style="flex:1;min-width:0;overflow:hidden;">'
            f'<span title="{_p}" style="display:block;font-size:18px;color:{fg};'
            f'line-height:1.32;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
            f'cursor:help;">{_p}</span>'
            f'<span style="display:block;font-size:16px;color:#94a3b8;line-height:1.3;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_d}</span>'
            f'</span>')


def _cell_chip(label, fg, bg, el_id=''):
    """ชิปสถานะ — ความกว้างเท่ากันทุกแถวเสมอ (จุดที่ทำให้ตากวาดลงเป็นแนวได้)"""
    _id = f' id="{el_id}"' if el_id else ''
    return (f'<span style="width:{_COL_ST}px;flex:none;">'
            f'<span{_id} style="display:block;background:{bg};color:{fg};border-radius:999px;'
            f'padding:5px 10px;font-size:16px;font-weight:600;white-space:nowrap;'
            f'text-align:center;overflow:hidden;text-overflow:ellipsis;">{label}</span></span>')


def _cell_time(main, sub='', title=''):
    """เวลา 2 บรรทัด ชิดขวา (เข้าชุดกับคอลัมน์อื่นที่เป็น 2 บรรทัดเหมือนกัน)
      บรรทัดบน = ตัวเลขหลัก (รอกี่นาที / ใช้ไปกี่นาที / เกินไปกี่นาที)
      บรรทัดล่าง = ผลลัพธ์ AI: ออกห้อง ~ช่วง + เรียกเคสถัดไป (เคสกำลังผ่า)
                   หรือ หลักฐานที่ AI ใช้ทำนาย (เคสที่ยังไม่เข้าห้อง)
    tabular-nums = ตัวเลขความกว้างเท่ากัน หลักจึงตรงกันทุกแถว กวาดตาลงคอลัมน์เดียว
    รู้ทันทีว่าใครรอนานสุด"""
    _t = f' title="{title}"' if title else ''
    _sub = (f'<span style="display:block;font-size:13px;color:#8a96a3;line-height:1.3;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{sub}</span>'
            ) if sub else ''
    return (f'<span{_t} style="width:{_COL_TM}px;flex:none;text-align:right;'
            f'overflow:hidden;font-variant-numeric:tabular-nums;">'
            f'<span style="display:block;font-size:18px;color:#475569;line-height:1.3;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{main}</span>'
            f'{_sub}</span>')


def _callnext_short(c, eff, tov_map, call_info=None):
    """ผลลัพธ์ AI แบบสั้นสำหรับบรรทัดล่างของคอลัมน์เวลา — คืน (สั้น, เต็มไว้ทำ tooltip)
    🚪 ช่วงเวลาออกห้อง (กว้างตามความยาวเคส) · ⏰ เวลาที่ควรเรียกเคสถัดไปขึ้นมารอ
    call_info = (เคสถัดไป, เวลาเรียก, 'override'|'ai') จาก call_queue.next_call_map —
    ถ้าคิวถัดไปถูกเรียกแล้ว/ถูกแก้เวลา บรรทัดนี้ต้องพูดเลขเดียวกัน ไม่ใช่สูตรดิบ"""
    ent = c.get('time_entered_or')
    if ent is None or not hasattr(ent, 'hour'):
        return '', ''
    from datetime import timedelta as _td
    try:
        rm = int(float(c.get('room')))
    except (TypeError, ValueError):
        rm = None
    tov = (tov_map or {}).get(rm) or (tov_map or {}).get('_global') or 15
    _hw = _band_halfwidth(eff)
    lo = (ent + _td(minutes=max(int(eff) - _hw, 5))).strftime('%H:%M')
    hi = (ent + _td(minutes=int(eff) + _hw)).strftime('%H:%M')
    cn = (ent + _td(minutes=int(eff) + float(tov) - _CALL_LEAD_MIN)).strftime('%H:%M')
    # ไม่ใส่อีโมจิในบรรทัดนี้: ที่ 13px มันกลายเป็นก้อนสีมัว ๆ อ่านไม่ออก เพิ่มความรก
    # เปล่า ๆ — ใช้สีเขียวทำหน้าที่ชี้ว่า "อันนี้คือสิ่งที่ต้องลงมือทำ" แทน
    _cn_html = f'<span style="color:#2f7d52;font-weight:600;">เรียกคิวถัดไป ~{cn}</span>'
    _cn_full = (f'เรียกคิวถัดไปขึ้นมารอ ~{cn} น. '
                f'(เผื่อเวลาเตรียมห้อง {int(tov)} นาที)')
    if call_info:
        _nc, _cdt, _csrc = call_info[0], call_info[1], call_info[2]
        _ct = _nc.get('call_time')
        if _ct is not None and hasattr(_ct, 'hour'):
            # 📣 เรียกไปแล้ว — งานนี้จบแล้ว บรรทัดนี้เปลี่ยนหน้าที่เป็น "ยืนยันผล"
            _cn_html = (f'<span style="color:#1565c0;font-weight:600;">'
                        f'เรียกคิวถัดไปแล้ว {_ct.strftime("%H:%M")} ✓</span>')
            _cn_full = f'เรียกคิวถัดไปไปแล้วเมื่อ {_ct.strftime("%H:%M")} น.'
        elif _csrc == 'override' and _cdt is not None:
            _cn_html = (f'<span style="color:#2f7d52;font-weight:600;">'
                        f'เรียกคิวถัดไป {_cdt.strftime("%H:%M")} (ปรับแล้ว)</span>')
            _cn_full = (f'เวลาเรียกคิวถัดไปถูกปรับด้วยมือเป็น '
                        f'{_cdt.strftime("%H:%M")} น. (ค่า AI ~{cn} น.)')
    short = f'ออกห้อง ~{lo}-{hi} · {_cn_html}'
    full = (f'ออกห้อง ~{lo}-{hi} น. (ช่วง ±{_hw} นาที กว้างตามความยาวเคส : '
            f'คาลิเบรตจากเคสจริงปี 2567 ครอบราว 5-6 ใน 10 เคส) · '
            f'{_cn_full} · ช่วงมั่นใจ 90% ของเคสนี้ดูในปุ่มแก้เวลา')
    return short, full



def _call_line_html(c, dt, src, now):
    """🔔 แถวเรียกคิวถัดไป ต่อท้ายการ์ดเคส "ยังไม่มา" ที่เป็นคิวถัดไปของห้อง
    (wireframe rev.2 มุคกี้เคาะ 13 ส.ค. 2026) — ภาษาสีชุดเดิมของบอร์ด:
    เขียว = สิ่งที่ต้องลงมือทำ · น้ำเงิน = ทำแล้ว · เหลือง = ปัญหาเวลา
    (แดงสงวนให้เคสฉุกเฉิน — เลยเวลาเรียกจึงเป็นเหลือง ไม่ใช่แดง)"""
    _base = ('display:flex;align-items:center;gap:8px;padding:5px 12px 6px;'
             'border-top:1px dashed #e2e8f0;font-size:15px;color:#64748b;'
             'font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;')
    ct = c.get('call_time')
    if ct is not None and hasattr(ct, 'hour'):
        from call_queue import call_from_label
        return (f'<div style="{_base}background:#f3f9f5;">📣 '
                f'<span style="color:#1565c0;font-weight:700;">'
                f'เรียกแล้ว {ct.strftime("%H:%M")}</span>'
                f'<span>กดจาก{call_from_label(c.get("call_from"))} · '
                f'โทรตาม ward แล้วรอกดรับเข้า · กดผิดยกเลิกได้ใน ✏️</span></div>')
    if dt is None or not hasattr(dt, 'hour'):
        return ''
    diff = int((dt - now).total_seconds() // 60)
    _ov = ('<span style="background:#e3f0fb;color:#1565c0;border-radius:8px;'
           'padding:1px 9px;font-size:13px;font-weight:600;">ปรับแล้ว</span>'
           if src == 'override' else '')
    _t_prefix = '' if src == 'override' else '~'
    if diff < 0:
        # ⏰ เลยเวลาเรียก — เหลืองทั้งแถบ (ภาษาสี: ปัญหาเวลา) ให้เห็นข้ามห้อง
        return (f'<div style="{_base}background:#fff8e1;">⏰ '
                f'<span style="color:#9a6700;font-weight:700;">เรียกคิว '
                f'{_t_prefix}{dt.strftime("%H:%M")} : เลยมา {-diff} น.</span>{_ov}'
                f'<span>โทรเรียกแล้วกด 📣 บันทึก หรือเลื่อนเวลาที่ ✏️</span></div>')
    _state = (f'<span style="color:#9a6700;font-weight:600;">อีก {diff} น.</span>'
              if diff <= 10 else f'<span>อีก {_dur_str(diff)}</span>')
    return (f'<div style="{_base}background:#fafcff;">🔔 '
            f'<span style="color:#2f7d52;font-weight:700;">เรียกคิวถัดไป '
            f'{_t_prefix}{dt.strftime("%H:%M")}</span>{_ov}{_state}'
            f'<span style="cursor:help;" title="เวลาเรียก = คาดว่าห้องจะพร้อมรับ '
            f'- {_CALL_LEAD_MIN} นาที (เผื่อโทร/เดินทาง) : ผู้ป่วยขึ้นมารอไม่เกิน '
            f'1 ชั่วโมง · แก้เวลาได้ที่ ✏️ · โทรแล้วกด 📣 บันทึก">ⓘ</span></div>')


def _progress_bar(pct, label, color='#22a565', wrap_id='', fill_id='', label_id=''):
    """แถบความคืบหน้า + ตัวเลข (มุคกี้สั่ง 9 ส.ค. 2026) — เคสกำลังผ่าอ่าน
    'ไปถึงไหนแล้ว' จากสัดส่วนได้ทันที ไม่ต้องเอาเลขสองตัวมาหารในหัว

    ตัวเลขอยู่ "ข้างแถบ" ไม่ใช่ "ในแถบ": ถ้าวางในแถบ ตัวเลขจะคาบเส้นระหว่าง
    พื้นที่เต็มกับพื้นที่ว่าง contrast เปลี่ยนไปตามความคืบหน้าของแต่ละเคส
    (ตรวจด้วยภาพจริงแล้ว อ่านยากจริง) · วางแถบไว้ซ้าย เลขชิดขวา เลขจึงยัง
    ตรงแนวกับทุกแถวในคอลัมน์เหมือนเดิม
    ⚠️ พอเกินเวลาแล้วสัดส่วนหมดความหมาย (เต็มไปแล้ว) → ผู้เรียกสลับเป็นตัวเลขนาที"""
    _w = f' id="{wrap_id}"' if wrap_id else ''
    _f = f' id="{fill_id}"' if fill_id else ''
    _l = f' id="{label_id}"' if label_id else ''
    # แถบตรึงความกว้าง 88px ไม่ใช่ flex — ถ้าปล่อยให้ยืดตามที่เหลือ แถบของเคส
    # เกินเวลา (ป้ายยาวกว่า) จะสั้นกว่าเคสปกติ ทั้งที่เต็ม 100% กลายเป็นอ่านผิด
    # ว่าคืบหน้าน้อยกว่า · ป้ายชิดขวาเสมอ เลขจึงตรงแนวกับทุกแถวในคอลัมน์
    return (f'<span{_w} style="display:flex;align-items:center;gap:9px;">'
            f'<span style="width:88px;flex:none;height:12px;border-radius:6px;'
            f'background:#eef2f6;overflow:hidden;">'
            f'<span{_f} style="display:block;height:100%;width:{pct}%;'
            f'background:{color};border-radius:6px;"></span></span>'
            f'<span{_l} style="flex:1;min-width:0;text-align:right;font-size:18px;'
            f'font-weight:700;color:#0f172a;white-space:nowrap;overflow:hidden;'
            f'text-overflow:ellipsis;">{label}</span></span>')


def _row_shell(inner, bg, border_css, row_id='row', prog='', extra=''):
    """extra = แถบต่อท้ายการ์ด (แถวเรียกคิวถัดไป — wireframe rev.2 13 ส.ค. 2026)
    มี extra → กรอบ/พื้นย้ายไปอยู่ที่กล่องนอก การ์ดสูงขึ้นตามเนื้อหา
    ⚠️ ส่ง extra ได้เฉพาะแถวที่ render ด้วย st.markdown (ยังไม่มา) — แถว iframe
    ประกาศความสูงล่วงหน้าไว้ที่ _ROW_IFRAME_H ถ้าสูงขึ้นเนื้อหาจะโดนตัดเงียบ ๆ"""
    _skin = '' if extra else f'{border_css}background:{bg};'
    row = (f'<div id="{row_id}" style="display:flex;align-items:center;gap:10px;'
           f'{_skin}border-radius:10px;padding:8px 12px;'
           f'height:{_ROW_H}px;position:relative;overflow:hidden;">{prog}{inner}</div>')
    if not extra:
        return row
    return (f'<div style="{border_css}background:{bg};border-radius:10px;'
            f'overflow:hidden;">{row}{extra}</div>')


def _iframe_doc(body):
    return ('<html><head><style>'
            '*{margin:0;padding:0;box-sizing:border-box}'
            "body{font-family:'Sarabun','IBM Plex Sans Thai','Segoe UI',sans-serif;"
            'background:transparent}'
            f'{_EMG_CSS}</style></head><body>{body}</body></html>')



def _time_static(c, disp, eff, elapsed, now, tov_map=None):
    """เนื้อหาคอลัมน์เวลาของแถวที่ไม่มีนาฬิกาเดินสด — คืน (บรรทัดบน, บรรทัดล่าง, tooltip)
    บรรทัดล่างคือผลลัพธ์ AI ที่ทีมใช้ตัดสินใจ (ช่วงออกห้อง/เรียกเคสถัดไป หรือ
    หลักฐานที่ใช้ทำนาย) — ต้องเห็นบนแถว ห้ามยุบไปเป็น tooltip"""
    ai0 = c.get('ai_predicted_min') or c.get('predicted_min')
    ov = c.get('user_override_min')
    if disp in ('holding_post', 'recovery'):
        ex = c.get('time_exited_or')
        # 🔤 9 ส.ค. 2026: เดิมใช้ "—" ผิดกติกา UI (ห้าม em dash) และขีดเปล่าไม่บอกอะไร
        #    ข้อความบอกสาเหตุตรง ๆ ช่วยให้พยาบาลรู้ว่าต้องไปกด ✏️ เติมเวลาย้อนหลัง
        _m = (f'เสร็จ {ex.strftime("%H:%M")} น.'
              if (ex is not None and hasattr(ex, 'hour')) else 'ยังไม่บันทึกเวลา')
        return _m, f'ใช้ห้องจริง {_dur_str(elapsed)}' if elapsed else '', ''
    if disp == 'discharged':
        dc = c.get('time_discharged')
        _m = (f'จำหน่าย {dc.strftime("%H:%M")} น.'
              if (dc is not None and hasattr(dc, 'hour')) else 'ยังไม่บันทึกเวลา')
        return _m, f'ใช้ห้องจริง {_dur_str(elapsed)}' if elapsed else '', ''
    if disp in ('in_or', 'overrun'):
        _short, _full = _callnext_short(c, eff, tov_map)
        if disp == 'overrun':
            # 🔴 เกินเวลา = แถบแดงเต็ม + "เกินไปเท่าไร" อย่างเดียว (มุคกี้สั่ง 9 ส.ค. 2026)
            _over = (f'เกิน {_dur_str(elapsed - eff)}' if elapsed > eff else 'เกินเวลา')
            return (_progress_bar(100, f'<span style="color:#c0392b;">{_over}</span>',
                                  color='#e24b4a'), _short, _full)
        _pct = min(int(elapsed / eff * 100), 100) if eff else 0
        _col = '#e3920b' if (eff and (eff - elapsed) <= 5) else '#22a565'
        return _progress_bar(_pct, f'{elapsed} / {eff} น.', color=_col), _short, _full
    # ยังไม่มา — เวลาที่ AI คาดว่าจะใช้ห้อง + หลักฐานที่ใช้ทำนาย
    _bits = []
    _n = c.get('proc_n')
    if _n is not None:
        _bits.append(f'จาก {int(_n)} เคส' if _n else 'ไม่มีเคสใกล้เคียง')
    _rng = c.get('predicted_range')
    if c.get('range_method') == 'conformal' and _rng:
        _bits.append(f'ช่วง {int(_rng[0])}-{int(_rng[1])} น.')
    _tip = ('ช่วง 90% = เคสลักษณะนี้ราว 9 ใน 10 ใช้เวลาอยู่ในช่วงนี้ · '
            'ช่วงแคบ = ค่อนข้างแน่นอน · ช่วงกว้าง = เวลาแกว่งได้มาก ควรเผื่อเวลา')
    if ov:
        return (f'<b style="font-weight:700;color:#0f172a;">{_dur_str(eff)}</b>',
                f'พยาบาลแก้ · 🤖 ทำนาย {_dur_str(ai0) if ai0 else "?"}', _tip)
    # 🤖 = ค่าที่มาจากโมเดล (ไม่ใช่คนกรอก) · "ใช้ห้อง" ระบุชัดว่าเป็นเวลาครองห้อง
    #     room-in ถึง room-out ไม่ใช่เวลาลงมีด — คนละตัวกัน ทีมเคยสับสน
    return (f'🤖 ใช้ห้อง ~{_dur_str(ai0) if ai0 else "? น."}',
            ' · '.join(_bits), _tip)


def _holding_row_iframe(c, loc, tlabel, now, dup_badge=''):
    """แถวรอผ่าตัดทั้งแถวเป็น HTML สด — นาฬิกานับเดินหน้าฝังในช่องเวลา (ไม่กินบรรทัดเพิ่ม)."""
    arr = c.get('time_arrived_holding')
    # ⏱ TZ-proof: คำนวณ "รอแล้วกี่วินาที" ฝั่ง Python (เวลา BKK สม่ำเสมอ)
    # แล้วให้ JS เดินต่อจากค่านี้ด้วย Date.now() ของเครื่องเอง (ไม่พึ่ง .timestamp()
    # ที่เพี้ยนเมื่อ server คนละ timezone) — ทุกเครื่องเห็นเลขเริ่มต้นเท่ากัน
    el0 = max((now - arr).total_seconds(), 0) if (arr is not None and hasattr(arr, 'hour')) else 0
    ov = c.get('user_override_min')
    ov_badge = ('<span style="background:#e3f0fb;color:#1565c0;border-radius:8px;'
                'padding:3px 12px;font-size:18px;margin-left:6px;">ปรับแล้ว</span>'
                if ov else '')
    emer = _is_emer(c)
    # แถบสีซ้าย 5px = สถานะแบบเห็นจากไกล (เทา=รอ · แดง=ฉุกเฉิน · เหลือง=รอเกินเวลา ใส่ทีหลังด้วย JS)
    border_css = ('border:1px solid #f5c6c5;border-left:5px solid #e0312e;'
                  if emer else 'border:1px solid #eef2f6;border-left:5px solid #cbd5e1;')
    # 🎨 demo (มุคกี้เคาะ 4 ส.ค. 2026 รอบสุดท้าย): เกณฑ์เดียว = 60 นาที
    #    รอเกิน 60 → แถบเหลืองครีมทั้งแถว + ชิปนาฬิกาเปลี่ยนเป็นสีแดง
    #    แถบแดงทั้งแถวสงวนให้เคสฉุกเฉินเท่านั้น · production JS เดิมเป๊ะ
    # ⏱ เวลารออยู่คอลัมน์เวลา (ข้อความชิดขวา) ไม่ใช่ชิปสีลอย ๆ เหมือนเดิม —
    #    ชิปสถานะมีคอลัมน์ของตัวเองแล้ว · เกิน 60 นาที = เหลือง (ภาษาสีเดิม:
    #    เหลือง = ปัญหาเวลา · แดงสงวนให้ฉุกเฉิน) ทั้งชิป เวลา และแถบซ้าย
    _js = (
        f'<script>var el0={el0:.0f},t0=Date.now(),emer={1 if emer else 0},'
        't=document.getElementById("t"),ch=document.getElementById("ch"),'
        'row=document.getElementById("row"),late=0;'
        'function u(){var el=el0+(Date.now()-t0)/1000,d=Math.floor(el/60),'
        'ss=Math.floor(el%60);'
        # ⏱ ไอคอนนาฬิกาจับเวลา — บอกว่าเลขนี้ "เดินเอง" ไม่ใช่ค่านิ่ง
        'if(d>=1440){t.textContent="⏱ รอนานมาก";t.style.color="#c0392b";return}'
        # ⏱ วินาทีเดินเฉพาะเคสที่รอเกิน 60 นาที (มุคกี้เคาะ 9 ส.ค. 2026):
        #   บอร์ดมี 9 แถว ถ้าเลขทุกแถวกระพริบทุกวินาทีจะดึงสายตาตลอดเวลา
        #   → ปกติเดินทีละนาที · เคสที่ต้องรีบจริงเท่านั้นที่เดินวินาที
        #   ใช้ padStart กันเลขเปลี่ยนความกว้างทุกวินาที (แถวจะกระตุก)
        't.textContent=(d>=60?"⏱ รอ "+d+":"+String(ss).padStart(2,"0")+" นาที"'
        ':"⏱ รอ "+d+" นาที");'
        'if(d>=60&&!late){late=1;t.style.color="#c0392b";t.style.fontWeight="700";'
        'ch.textContent="รอเกินเวลา";ch.style.background="#fdf3dd";ch.style.color="#9a6700";'
        + ('if(!emer){row.style.background="#fffdf5";'
           'row.style.borderLeft="5px solid #e3920b";}' if _demo_fx_tb() else '')
        + '}}u();setInterval(u,1000)</script>'
    )
    return _iframe_doc(
        _row_shell(
            _cell_room(c, loc)
            + _cell_q(c, tlabel, emer)
            + _cell_patient(c, dup_badge)
            + _cell_op(c)
            + _cell_chip('รอผ่าตัด', '#64748b', '#f1f5f9', el_id='ch')
            # บรรทัดล่าง = เวลาที่ AI ทำนายว่าจะใช้ห้อง (เห็นก่อนเข้าห้องจริง)
            + _cell_time('<span id="t"></span>' + ov_badge,
                         # 15px (ใหญ่กว่าบรรทัดล่างมาตรฐาน 13px): ข้อความสั้น มีที่เหลือ
                         # และไอคอน 🤖 ที่ 13px จะเละเป็นก้อนสี อ่านไม่ออก
                         sub=(f'<span style="font-size:15px;">🤖 ใช้ห้อง '
                              f'~{_dur_str(c.get("ai_predicted_min") or c.get("predicted_min"))}</span>'
                              if (c.get('ai_predicted_min') or c.get('predicted_min')) else '')),
            bg=('#fdeeee' if emer else '#ffffff'),
            border_css=border_css)
        + _js)


def _inroom_row_iframe(c, loc, tlabel, eff, border_css, ov_badge, now,
                       callnext=None, dup_badge=''):
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
        _iframe_doc(
            _row_shell(
                _cell_room(c, loc)
                + _cell_q(c, tlabel, _emer)
                + _cell_patient(c, dup_badge)
                + _cell_op(c)
                + _cell_chip('กำลังผ่า', '#1b7f4b', '#e6f6ec', el_id='ch')
                # callnext_html = คู่ (สั้น, เต็ม) จาก _callnext_short — บรรทัดล่างคือ
                # ผลลัพธ์ AI ที่ทีมใช้ตัดสินใจจริง ต้องเห็นบนแถว ไม่ใช่ซ่อนใน tooltip
                # ปกติ = แถบความคืบหน้าพร้อมตัวเลขในตัว · เกินเวลา = สลับเป็นตัวเลข
                # นาทีล้วน (JS สลับ display ให้) เพราะสัดส่วนหมดความหมายเมื่อเต็มแล้ว
                + _cell_time(_progress_bar(0, '', wrap_id='pw', fill_id='b',
                                           label_id='pl') + ov_badge,
                             sub=(callnext[0] if callnext else ''),
                             title=(callnext[1] if callnext else '')),
                bg=_bg, border_css=border_css, row_id='rw')
        ).replace('</body></html>', '')
        + f'<script>var el0={el0:.0f},t0=Date.now(),eff={int(eff)}'
        + (f',emer={1 if _emer else 0}' if _demo_fx_tb() else '') + ';'
        'var b=document.getElementById("b"),pl=document.getElementById("pl"),'
        'ch=document.getElementById("ch"),rw=document.getElementById("rw");'
        'function z(x){return String(x).padStart(2,"0")}'
        'function u(){var el=Math.floor(el0+(Date.now()-t0)/1000),'
        'm=Math.floor(el/60),ss=el%60,rem=eff*60-el;'
        'b.style.width=Math.min(el/(eff*60)*100,100)+"%";'
        # 📊 9 ส.ค. 2026 (มุคกี้สั่ง): ยังไม่เกินเวลา = อ่านจากแถบ (เลขอยู่ในแถบ)
        #    · เกินเวลาแล้ว = สลับเป็นตัวเลขนาที เพราะสัดส่วนเต็มไปแล้ว ไม่บอกอะไรต่อ
        'pl.textContent=m+" / "+eff+" น.";'
        'if(rem>300){b.style.background="#22a565";}'
        + 'else if(rem>0){b.style.background="#e3920b";}'
        # 🔴 เกินเวลา (มุคกี้สั่ง 9 ส.ค. 2026): ยังเป็นแถบเหมือนเดิม แต่แดงเต็มแถบ
        #    — เห็นจากไกลว่าห้องนี้ล้นแล้ว · ตัวเลขข้างแถบบอกว่าเกินไปเท่าไร
        'else{var ov=-rem;'
        'b.style.width="100%";b.style.background="#e24b4a";pl.style.color="#c0392b";'
        # ป้ายเหลือแค่ "เกิน mm:ss" — ไม่ต้องบอก "128 / 90 น." อีกแล้ว เพราะแถบ
        # แดงเต็มสื่อว่าเลยเวลาที่ทำนายไว้ไปแล้ว สิ่งที่ต้องรู้ต่อคือเกินไปเท่าไร
        # (เดิม 2 เวอร์ชัน demo/production ต่างกันแค่ส่วนที่ตัดออกนี้ — ยุบเหลือชุดเดียว)
        'pl.textContent="เกิน "+Math.floor(ov/60)+":"+z(ov%60);'
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
                room_opts=None, mark_dirty=None, tov_map=None, dup_badges=None,
                call_map=None):
    room_opts = room_opts or []
    dup_badge = (dup_badges or {}).get(id(c), '')
    # 🔔 เคสนี้คือ "คิวถัดไปที่ต้องเรียก" ของห้องหรือเปล่า (identity เทียบ object
    #    ตรง ๆ — call_map สร้างจาก list เดียวกันในรอบ render นี้เสมอ)
    _ci = (call_map or {}).get(R)
    _is_next_call = bool(_ci) and (_ci[0] is c)
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
                'padding:3px 12px;font-size:18px;margin-left:6px;">ปรับแล้ว</span>'
                if ov else '')
    # จำหน่ายแล้ว → แถบเทาจาง ทุกอย่างหรี่ลง (ไฟฉุกเฉินดับด้วย — เคสจบแล้ว ไม่รกตา)
    muted = (disp == 'discharged')
    emer = _is_emer(c) and not muted
    # แถบสีซ้าย 5px = สถานะแบบเห็นจากไกล (คู่กับชิปในคอลัมน์สถานะ)
    # (ป้าย _EMG_BADGE เดิมถูกถอด — ย้ายไปเป็นป้ายในคอลัมน์นัดโดย _cell_q แล้ว
    #  เพราะป้ายเดิมกว้างจนเบียดชื่อผู้ป่วยจนอ่านไม่ออก)
    _bar = {'holding_pre': '#cbd5e1', 'in_or': '#22a565', 'overrun': '#e3920b',
            'holding_post': '#1565c0', 'recovery': '#a855f7',
            'discharged': '#e2e8f0'}.get(disp, '#cbd5e1')
    border_css = ('border:1px solid #f5c6c5;border-left:5px solid #e0312e;'
                  if emer else f'border:1px solid #eef2f6;border-left:5px solid {_bar};')
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
    c0, c1, c2, c3 = st.columns(_BOARD_COLS)

    with c0:
        if disp == 'holding_pre':
            components.html(_holding_row_iframe(c, loc, tlabel, now, dup_badge),
                            height=_ROW_IFRAME_H)
        elif (disp in ('in_or', 'overrun')
              and c.get('time_entered_or') is not None
              and hasattr(c.get('time_entered_or'), 'timestamp')):
            # แถวกำลังผ่าแบบสด — นาฬิกาเดินหน้า + สลับเกินเวลาอัตโนมัติ
            # 🔔 ส่งสถานะเรียกของคิวถัดไปในห้องนี้ไปด้วย — บรรทัด "เรียกคิวถัดไป"
            #    ท้ายแถวต้องพูดเลขเดียวกับแถบเรียกคิว (เรียกแล้ว/ปรับแล้ว)
            components.html(
                _inroom_row_iframe(c, loc, tlabel, max(int(eff), 5),
                                   border_css, ov_badge, now,
                                   _callnext_short(c, eff, tov_map, _ci), dup_badge),
                height=_ROW_IFRAME_H)
        else:
            # ความคืบหน้าอยู่ในแถบของคอลัมน์เวลาแล้ว (_progress_bar) ไม่ต้องมีแถบ
            # ที่ขอบล่างแถวซ้ำอีก — สองแถบบอกเรื่องเดียวกันคือความรก
            _tm_html, _tm_sub, _tm_tip = _time_static(c, disp, eff, elapsed, now, tov_map)
            # 🔔 แถวเรียกคิวถัดไป ต่อท้ายการ์ด — เฉพาะเคสคิวถัดไปของห้อง
            #    (เคสไม่ได้จัดคิว = แถวนี้ว่าง ตาม wireframe rev.2)
            _call_extra = (_call_line_html(c, _ci[1], _ci[2], now)
                           if _is_next_call and disp == 'not_arrived' else '')
            st.markdown(
                _row_shell(
                    _cell_room(c, loc, fg=room_fg)
                    + _cell_q(c, tlabel, emer)
                    + _cell_patient(c, dup_badge if not muted else '', fg=name_fg)
                    + _cell_op(c, fg=sub_fg)
                    + _cell_chip(label, fg, chipbg)
                    + _cell_time(_tm_html + ov_badge, sub=_tm_sub, title=_tm_tip),
                    bg=bg, border_css=border_css, extra=_call_extra),
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
                st.caption("เวลาทำนายใช้ห้องผ่าตัด (นาที) — แก้แทนค่า AI ได้ "
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
                    # ✏️ กันพิมพ์ผิดหลัก (30 → 300) ก่อนค่าจะชนะ AI บนบอร์ด
                    #    และก่อนไหลลง override_log ซึ่งเป็นข้อมูลวิจัย
                    _ovk = f"_ov_confirm_{c.get('id') or idx}"
                    _ovwarn = ''
                    if int(new_t) != eff:
                        try:
                            from main_or_core import override_sanity_warning
                            _ovwarn = override_sanity_warning(int(new_t), _ai0)
                        except Exception as _wx:
                            print(f"[override] ตรวจค่าผิดปกติไม่สำเร็จ: {_wx}")
                    if _ovwarn and st.session_state.get(_ovk) != int(new_t):
                        # ครั้งแรก: เตือนคาไว้ตรงนี้ รอกดยืนยันอีกครั้ง
                        # ⚠️ ห้าม st.stop() ที่นี่ — อยู่ใน fragment จะตัดแถวที่เหลือ
                        #    ของบอร์ดทิ้งทั้งหมด (บอร์ดหายไปครึ่งจอ)
                        st.session_state[_ovk] = int(new_t)
                        st.warning(_ovwarn)
                    else:
                        st.session_state.pop(_ovk, None)
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

                # 🔔 เวลาเรียกคิวถัดไป (wireframe rev.2 มุคกี้เคาะ 13 ส.ค. 2026)
                #    แก้ที่ดินสอตัวเดียวตามที่เคาะ · สิทธิ์ = _own อยู่แล้ว
                #    (จอรับ-ส่งแก้ได้ทุกเคส · จอห้องเฉพาะเคสห้องตัวเอง)
                if _is_next_call and disp == 'not_arrived':
                    from call_queue import (fmt_hhmm as _cq_fmt,
                                            CALL_EDIT_REASONS as _CQ_REASONS)
                    st.markdown("---")
                    _ct = c.get('call_time')
                    if _ct is not None and hasattr(_ct, 'hour'):
                        from call_queue import call_from_label as _cq_lbl
                        st.caption(f"📣 เรียกคิวแล้ว {_ct.strftime('%H:%M')} น. "
                                   f"(กดจาก{_cq_lbl(c.get('call_from'))})")
                        if st.button("↩️ ยกเลิกการเรียก (กดผิด)",
                                     key=f"tb_cu_{idx}", width='stretch'):
                            from call_queue import apply_undo_call as _cq_undo
                            if _cq_undo(c):
                                try:
                                    from main_or_db import log_call_event
                                    log_call_event(c, 'undo')
                                except Exception as _ex:
                                    print(f"[call_log] log undo ล้มเหลว: {_ex}")
                                try:
                                    from research_log import log_case_state
                                    log_case_state(c)
                                except Exception as _rx:
                                    print(f"[research_log] ข้าม: {_rx}")
                                if mark_dirty:
                                    mark_dirty(c)
                                try:
                                    from main_or_pages import _toast_ok
                                    _toast_ok("ยกเลิกการเรียกแล้ว ↩️")
                                except Exception:
                                    pass
                            _rerun_board()
                    else:
                        st.caption("🔔 เวลาเรียกคิวถัดไป (เคสนี้เป็นคิวถัดไปของห้อง) "
                                   ": ค่าเริ่มต้นจาก AI แก้แทนได้ · ค่าที่แก้จะล็อก "
                                   "ไม่ขยับตามสถานการณ์อีก")
                        _ai_dt = _ci[3]
                        if _ai_dt is not None:
                            st.caption(f"🤖 AI แนะนำเรียก ~{_ai_dt.strftime('%H:%M')} น. "
                                       f"(ห้องพร้อม - เผื่อเดินทาง {_CALL_LEAD_MIN} นาที)")
                        _tv = st.time_input(
                            "เวลาเรียก", value=(_ci[1].time() if _ci[1] else None),
                            key=f"tb_ct_{idx}", step=300,
                            label_visibility="collapsed")
                        _rsn = st.selectbox("เหตุผลที่แก้", _CQ_REASONS,
                                            key=f"tb_cr_{idx}")
                        _cur_hhmm = _cq_fmt(_ci[1]) or ''
                        if (_tv is not None
                                and _tv.strftime('%H:%M') != _cur_hhmm
                                and st.button("💾 บันทึกเวลาเรียก",
                                              key=f"tb_cs_{idx}", width='stretch')):
                            _newv = _tv.strftime('%H:%M')
                            c['call_override_hhmm'] = _newv
                            c['call_override_reason'] = _rsn
                            c['call_ai_hhmm'] = _cq_fmt(_ai_dt)
                            try:
                                from main_or_db import log_call_event
                                log_call_event(c, 'edit', ai_hhmm=_cq_fmt(_ai_dt),
                                               new_hhmm=_newv, reason=_rsn)
                            except Exception as _ex:
                                print(f"[call_log] log edit ล้มเหลว: {_ex}")
                            if mark_dirty:
                                mark_dirty(c)
                            try:
                                from main_or_pages import _toast_ok
                                _toast_ok(f"เวลาเรียกคิว {_newv} ✓")
                            except Exception:
                                pass
                            _rerun_board()
                        if c.get('call_override_hhmm'):
                            if st.button("↺ คืนค่า AI", key=f"tb_ca_{idx}",
                                         width='stretch',
                                         help="เลิกใช้เวลาที่แก้ กลับไปให้ AI "
                                              "ขยับเวลาตามสถานการณ์เหมือนเดิม"):
                                c.pop('call_override_hhmm', None)
                                c.pop('call_override_reason', None)
                                try:
                                    from main_or_db import log_call_event
                                    log_call_event(c, 'reset',
                                                   ai_hhmm=_cq_fmt(_ai_dt))
                                except Exception as _ex:
                                    print(f"[call_log] log reset ล้มเหลว: {_ex}")
                                if mark_dirty:
                                    mark_dirty(c)
                                try:
                                    from main_or_pages import _toast_ok
                                    _toast_ok("กลับไปใช้ค่า AI แล้ว ✓")
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
            # 📣 บันทึกว่าโทรเรียกคิวแล้ว — เฉพาะเคสคิวถัดไปที่ยังไม่ถูกเรียก
            #    (จอรับ-ส่งเป็นคนโทรตาม ward · จอห้องสั่งเรียกผ่านกระดิ่ง 🔔
            #    ที่หน้าจอห้องแทน — เคาะจาก wireframe rev.2 ข้อ ⑤)
            if _is_next_call and c.get('call_time') is None:
                if st.button("📣 เรียกแล้ว", key=f"tb_call_{idx}", width='stretch',
                             help="โทรเรียกผู้ป่วยจาก ward แล้ว : บันทึกเวลาที่เรียก"):
                    from call_queue import apply_call as _cq_call
                    from call_queue import fmt_hhmm as _cq_fmt
                    if _cq_call(c, _now(), 'board',
                                planned_hhmm=_cq_fmt(_ci[1])):
                        try:
                            from main_or_db import log_call_event
                            log_call_event(c, 'call', ai_hhmm=_cq_fmt(_ci[3]),
                                           new_hhmm=_cq_fmt(c.get('call_time')))
                        except Exception as _ex:
                            print(f"[call_log] log call ล้มเหลว: {_ex}")
                        try:    # 📊 called_at ลงตารางวิจัย (เคสในขอบเขตเท่านั้น)
                            from research_log import log_case_state
                            log_case_state(c)
                        except Exception as _rx:
                            print(f"[research_log] ข้าม: {_rx}")
                        if mark_dirty:
                            mark_dirty(c)
                        try:
                            from main_or_pages import _toast_ok
                            _toast_ok("บันทึกเรียกคิวแล้ว 📣")
                        except Exception:
                            pass
                    _rerun_board()
        elif disp == 'holding_pre' and _scope is None:
            _busy = R in busy_rooms
            if st.button("ห้องไม่ว่าง" if _busy else "เข้าห้อง", key=f"tb_e_{idx}",
                         type="secondary" if _busy else "primary",
                         width='stretch', disabled=_busy,
                         help=("ห้องนี้มีเคสกำลังผ่าอยู่ — ต้องกด 'ผ่าเสร็จ' "
                               "เคสแรกก่อนจึงเข้าห้องได้" if _busy else None)):
                if R in busy_rooms:
                    # 🔇 หมายเหตุ: กิ่งนี้ปกติกดไม่ถึง เพราะปุ่มถูก disabled=_busy
                    # ไว้แล้วด้านบน — คงไว้เป็น defense-in-depth เผื่อ guard เปลี่ยน
                    try:
                        from main_or_pages import _toast_err_sound
                        _toast_err_sound()
                    except Exception:
                        pass
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
