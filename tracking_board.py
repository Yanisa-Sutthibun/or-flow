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
    'recovery':     ('ห้องพักฟื้น',  '#1565c0', '#e3f0fb', ''),
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
_EMG_BADGE = '<span class="emg-dot"></span><span class="emg-tag">ฉุกเฉิน</span>'


def _is_emer(c):
    """เคสฉุกเฉิน/เร่งด่วน — ดูจาก flag หรือข้อความประเภทเคส (emergency/urgency)"""
    if c.get('is_emergency'):
        return True
    t = str(c.get('case_type') or c.get('op_type') or c.get('optype') or '').lower()
    return ('emer' in t) or ('urg' in t) or ('ฉุกเฉิน' in t) or ('เร่งด่วน' in t)


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
    """ข้อมูลระบุตัวรอง: HN — แสดง 4 ตัวท้ายเสมอ (มาตรา 3.6.4) · ไม่แสดงอายุ"""
    hn = c.get('hn') or ''
    from main_or_db import mask_hn
    _h = mask_hn(hn)
    return f"HN {_esc(_h)}" if _h else ''


def render_tracking_board(cases, do_arrive, do_enter, do_finish, do_undo,
                          loc, rid, tlabel, sched_min, room_opts=None,
                          mark_dirty=None):
    """วาดกระดานติดตามทั้งหมด (เรียกจาก page_or_board).
    room_opts = [(room_no, ชื่อห้อง)] ห้องที่เปิดใช้ — สำหรับ dropdown ย้ายห้องใน ✏️"""
    now = _now()
    room_opts = room_opts or []
    st.markdown(f'<style>{_EMG_CSS}</style>', unsafe_allow_html=True)

    # ---------- ค้นหา + กรอง ----------
    fc1, fc2, fc3 = st.columns([3, 1.4, 1.6])
    q = fc1.text_input("ค้นหา", key="tb_q", placeholder="ค้นหา ชื่อ / HN / หัตถการ",
                       label_visibility="collapsed")
    rooms_avail = sorted({loc(c) for c in cases})
    room_f = fc2.selectbox("ห้อง", ["ทุกห้อง"] + rooms_avail, key="tb_room",
                           label_visibility="collapsed")
    status_f = fc3.selectbox("สถานะ", ["ทุกสถานะ", "ยังไม่มา", "รอผ่าตัด", "กำลังผ่า",
                                       "รอจำหน่าย", "จำหน่ายแล้ว"], key="tb_status",
                             label_visibility="collapsed")
    ql = (q or '').strip().lower()

    # ห้องที่มีเคสกำลังผ่าอยู่ → ห้ามเข้าห้องซ้ำ
    busy_rooms = {rid(c) for c in cases if c['status'] == 'in_or' and rid(c)}
    tov_map = _turnover_map()

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

    # ---------- แถว (เรียง ห้อง → ฉุกเฉินก่อนในห้อง → เวลานัด → ลำดับ) ----------
    # เคสฉุกเฉินลอยขึ้นบนสุดของแต่ละห้อง · is_emergency เป็นค่าคงที่ →
    # ลำดับยังนิ่ง (แถวไม่ขยับเมื่อสถานะเปลี่ยน) ตามหลักการเดิม
    rows = list(enumerate(cases))
    rows.sort(key=lambda t: ((rid(t[1]) or 999),
                             (0 if _is_emer(t[1]) else 1),
                             (sched_min(t[1]) or 9999),
                             t[1].get('ororder') or 999))
    shown = 0
    for idx, c in rows:
        if ql and (ql not in str(c.get('name', '')).lower()
                   and ql not in str(c.get('hn', '')).lower()
                   and ql not in str(c.get('procedure', '')).lower()):
            continue
        if room_f != 'ทุกห้อง' and loc(c) != room_f:
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

        _render_row(idx, c, disp, eff, elapsed, now, rid(c), busy_rooms,
                    do_arrive, do_enter, do_finish, do_undo, loc, tlabel,
                    room_opts, mark_dirty, tov_map)
        shown += 1

    if shown == 0:
        st.caption("ไม่พบเคสตามเงื่อนไขที่กรอง")


_CALL_LEAD_MIN = 30  # เวลาเตรียม/เคลื่อนย้ายผู้ป่วยก่อนห้องว่าง (นาที) สำหรับ Call next


@st.cache_data(ttl=1800)
def _turnover_map():
    """median turnover รายห้องจากข้อมูลจริง (fallback _global) — cache 30 นาที"""
    try:
        from main_or_db import get_room_turnover_map
        return get_room_turnover_map() or {}
    except Exception:
        return {}


def _callnext_html(c, eff, tov_map):
    """บรรทัด 'ออกห้อง ~HH:MM · Call next ~HH:MM' (คิด turnover รายห้อง + lead)"""
    ent = c.get('time_entered_or')
    if ent is None or not hasattr(ent, 'hour'):
        return ''
    from datetime import timedelta as _td
    try:
        rm = int(float(c.get('room')))
    except (TypeError, ValueError):
        rm = None
    tov = (tov_map or {}).get(rm) or (tov_map or {}).get('_global') or 15
    out_dt = ent + _td(minutes=int(eff))
    call_dt = ent + _td(minutes=int(eff) + float(tov) - _CALL_LEAD_MIN)
    return ('<div style="font-size:11px;color:#8a96a3;margin-top:2px;white-space:nowrap;">'
            '🚪 ออกห้อง ~' + out_dt.strftime('%H:%M')
            + ' · <span style="color:#2f7d52;font-weight:600;">⏰ Call next ~'
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
        return (f'<b style="font-weight:600;">{eff} น.</b> '
                f'<span style="text-decoration:line-through;color:#94a3b8;'
                f'font-size:12px;">AI {ai0 or "?"}</span>')
    return f'AI ~{ai0 or "?"} น.'


def _holding_row_iframe(c, loc, tlabel, now):
    """แถวรอผ่าตัดทั้งแถวเป็น HTML สด — นาฬิกานับเดินหน้าฝังในช่องเวลา (ไม่กินบรรทัดเพิ่ม)."""
    arr = c.get('time_arrived_holding')
    # ⏱ TZ-proof: คำนวณ "รอแล้วกี่วินาที" ฝั่ง Python (เวลา BKK สม่ำเสมอ)
    # แล้วให้ JS เดินต่อจากค่านี้ด้วย Date.now() ของเครื่องเอง (ไม่พึ่ง .timestamp()
    # ที่เพี้ยนเมื่อ server คนละ timezone) — ทุกเครื่องเห็นเลขเริ่มต้นเท่ากัน
    el0 = max((now - arr).total_seconds(), 0) if (arr is not None and hasattr(arr, 'hour')) else 0
    ov = c.get('user_override_min')
    ov_badge = ('<span style="background:#e3f0fb;color:#1565c0;border-radius:8px;'
                'padding:0 6px;font-size:11.5px;margin-left:4px;">ปรับแล้ว</span>'
                if ov else '')
    emer = _is_emer(c)
    emg_html = _EMG_BADGE if emer else ''
    border_css = ('border:1px solid #f5c6c5;border-left:3px solid #e0312e;'
                  if emer else 'border:1px solid #eef2f6;')
    return (
        '<html><head><style>'
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:'IBM Plex Sans Thai','Sarabun','Segoe UI',sans-serif;background:transparent}"
        f"{_EMG_CSS}"
        '</style></head><body>'
        f'<div style="display:flex;align-items:center;gap:10px;{border_css}'
        f'background:#fffcf3;border-radius:10px;padding:9px 12px;">'
        f'<span style="min-width:78px;font-size:14px;font-weight:600;color:#1565c0;">{loc(c)}</span>'
        f'<span style="min-width:46px;font-size:13px;color:#64748b;">{tlabel(c)}</span>'
        f'<span style="flex:1;min-width:0;overflow:hidden;">'
        f'{emg_html}'
        f'<span style="font-size:15px;font-weight:600;color:#0f172a;">{_pt_name(c)}</span>'
        f'<span style="font-size:12px;color:#94a3b8;"> {_pt_meta(c)}</span><br>'
        f'<span style="font-size:13px;color:#64748b;white-space:nowrap;">'
        f'{_esc(c["procedure"])} · {_esc(c.get("surgeon", "-"))}</span></span>'
        f'<span style="min-width:80px;"><span style="background:#fdf3dd;color:#9a6700;'
        f'border-radius:10px;padding:2px 10px;font-size:12.5px;font-weight:500;white-space:nowrap;">รอผ่าตัด</span></span>'
        f'<span style="min-width:110px;"><span id="t" style="color:#fff;padding:2px 9px;'
        f'border-radius:8px;font-size:13px;font-weight:600;display:inline-block;'
        f'white-space:nowrap;"></span>{ov_badge}</span>'
        f'</div>'
        f'<script>var el0={el0:.0f},t0=Date.now(),t=document.getElementById("t");'
        'function u(){var el=el0+(Date.now()-t0)/1000,d=Math.floor(el/60),'
        'sec=Math.floor(el%60),c=d<30?"#22a565":d<60?"#e3920b":"#e24b4a";'
        'if(d>=1440){t.textContent="⏱ รอนานมาก";t.style.background="#e24b4a";return}'
        't.style.background=c;'
        't.textContent="⏱ รอแล้ว "+d+":"+String(sec).padStart(2,"0")}'
        'u();setInterval(u,1000)</script></body></html>'
    )


def _inroom_row_iframe(c, loc, tlabel, eff, emg_html, border_css, ov_badge, now, callnext_html=''):
    """แถวกำลังผ่าแบบสด (ลูกผสม — บอร์ดสงบ เคสมีปัญหาเด่นเอง):
    - ปกติ: โชว์นาทีล้วน '41 / 60 น.' สีเขียว เดินเองทุกนาที
    - ใกล้ครบ (เหลือ ≤5 นาที): สลับเป็น mm:ss สีส้ม
    - เกินเวลา: mm:ss สีแดง + 'เกิน m:ss' + ชิป/พื้นแถวเปลี่ยนแดงสด ไม่ต้อง refresh
    ⏱ TZ-proof: ส่ง 'ผ่าไปแล้วกี่วินาที' จาก Python (BKK) ให้ JS เดินต่อด้วย
    Date.now() ของเครื่อง — ไม่พึ่ง .timestamp() ที่เพี้ยนข้าม timezone"""
    ent = c.get('time_entered_or')
    el0 = max((now - ent).total_seconds(), 0) if (ent is not None and hasattr(ent, 'hour')) else 0
    return (
        '<html><head><style>'
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:'IBM Plex Sans Thai','Sarabun','Segoe UI',sans-serif;background:transparent}"
        f"{_EMG_CSS}"
        '</style></head><body>'
        f'<div id="rw" style="display:flex;align-items:center;gap:10px;{border_css}'
        f'background:#f4fbf7;border-radius:10px;padding:9px 12px;">'
        f'<span style="min-width:78px;font-size:14px;font-weight:600;color:#1565c0;">{loc(c)}</span>'
        f'<span style="min-width:46px;font-size:13px;color:#64748b;">{tlabel(c)}</span>'
        f'<span style="flex:1;min-width:0;overflow:hidden;">'
        f'{emg_html}'
        f'<span style="font-size:15px;font-weight:600;color:#0f172a;">{_pt_name(c)}</span>'
        f'<span style="font-size:12px;color:#94a3b8;"> {_pt_meta(c)}</span><br>'
        f'<span style="font-size:13px;color:#64748b;white-space:nowrap;">'
        f'{_esc(c["procedure"])} · {_esc(c.get("surgeon", "-"))}</span></span>'
        f'<span style="min-width:80px;"><span id="ch" style="background:#e6f6ec;color:#1b7f4b;'
        f'border-radius:10px;padding:2px 10px;font-size:12.5px;font-weight:500;white-space:nowrap;">กำลังผ่า</span></span>'
        f'<span style="min-width:150px;font-size:13px;">'
        f'<span id="t" style="color:#1b7f4b;font-weight:600;"></span>{ov_badge}'
        f'<span style="display:block;height:4px;background:#eef2f6;border-radius:2px;'
        f'overflow:hidden;margin-top:3px;"><span id="b" style="display:block;height:100%;'
        f'width:0%;background:#22a565;"></span></span>{callnext_html}</span>'
        f'</div>'
        f'<script>var el0={el0:.0f},t0=Date.now(),eff={int(eff)};'
        'var t=document.getElementById("t"),b=document.getElementById("b"),'
        'ch=document.getElementById("ch"),rw=document.getElementById("rw");'
        'function z(x){return String(x).padStart(2,"0")}'
        'function u(){var el=Math.floor(el0+(Date.now()-t0)/1000),'
        'm=Math.floor(el/60),ss=el%60,rem=eff*60-el;'
        'b.style.width=Math.min(el/(eff*60)*100,100)+"%";'
        'if(rem>300){t.textContent=m+" / "+eff+" น.";'
        't.style.color="#1b7f4b";b.style.background="#22a565";}'
        'else if(rem>0){t.textContent=m+":"+z(ss)+" / "+eff+" น.";'
        't.style.color="#e3920b";b.style.background="#e3920b";}'
        'else{var ov=-rem;'
        't.textContent=m+":"+z(ss)+" / "+eff+" น. · เกิน "+Math.floor(ov/60)+":"+z(ov%60);'
        't.style.color="#c0392b";b.style.width="100%";b.style.background="#e24b4a";'
        'ch.textContent="เกินเวลา";ch.style.background="#fbe9e8";ch.style.color="#c0392b";'
        'rw.style.background="#fdf3f3";}}'
        'u();setInterval(u,1000)</script></body></html>'
    )


def _render_row(idx, c, disp, eff, elapsed, now, R, busy_rooms,
                do_arrive, do_enter, do_finish, do_undo, loc, tlabel,
                room_opts=None, mark_dirty=None, tov_map=None):
    room_opts = room_opts or []
    # .get + ค่า default — กัน KeyError ถ้าเจอสถานะแปลก (เช่น snapshot จากเวอร์ชันเก่า)
    label, fg, chipbg, rowbg = _STATUS_META.get(
        disp, (str(disp or 'ไม่ทราบสถานะ'), '#64748b', '#f1f5f9', ''))
    bg = rowbg if rowbg else '#ffffff'
    ov = c.get('user_override_min')
    ov_badge = ('<span style="background:#e3f0fb;color:#1565c0;border-radius:8px;'
                'padding:1px 7px;font-size:11.5px;margin-left:4px;">ปรับแล้ว</span>'
                if ov else '')
    # จำหน่ายแล้ว → แถบเทาจาง ทุกอย่างหรี่ลง (ไฟฉุกเฉินดับด้วย — เคสจบแล้ว ไม่รกตา)
    muted = (disp == 'discharged')
    emer = _is_emer(c) and not muted
    emg_html = _EMG_BADGE if emer else ''
    border_css = ('border:1px solid #f5c6c5;border-left:3px solid #e0312e;'
                  if emer else 'border:1px solid #eef2f6;')
    room_fg = '#b6c2cf' if muted else '#1565c0'
    name_fg = '#94a3b8' if muted else '#0f172a'
    sub_fg = '#b6c2cf' if muted else '#64748b'
    time_fg = '#b6c2cf' if muted else '#475569'

    # ---------- layout ต่อแถว: [แถว] [✏️] [ปุ่มหลัก] [↩] ----------
    c0, c1, c2, c3 = st.columns([8, 0.8, 1.5, 0.8])

    with c0:
        if disp == 'holding_pre':
            components.html(_holding_row_iframe(c, loc, tlabel, now), height=60)
        elif (disp in ('in_or', 'overrun')
              and c.get('time_entered_or') is not None
              and hasattr(c.get('time_entered_or'), 'timestamp')):
            # แถวกำลังผ่าแบบสด — นาฬิกาเดินหน้า + สลับเกินเวลาอัตโนมัติ
            components.html(
                _inroom_row_iframe(c, loc, tlabel, max(int(eff), 5),
                                   emg_html, border_css, ov_badge, now,
                                   _callnext_html(c, eff, tov_map)),
                height=78)
        else:
            time_html = _time_cell(c, disp, eff, elapsed, now)
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;'
                f'{border_css}background:{bg};'
                f'border-radius:10px;padding:9px 12px;margin:2px 0;">'
                f'<span style="min-width:78px;font-size:14px;font-weight:600;color:{room_fg};">{loc(c)}</span>'
                f'<span style="min-width:46px;font-size:13px;color:{sub_fg};">{tlabel(c)}</span>'
                f'<span style="flex:1;min-width:0;overflow:hidden;">'
                f'{emg_html}'
                f'<span style="font-size:15px;font-weight:600;color:{name_fg};">{_pt_name(c)}</span>'
                f'<span style="font-size:12px;color:#94a3b8;"> {_pt_meta(c)}</span><br>'
                f'<span style="font-size:13px;color:{sub_fg};white-space:nowrap;overflow:hidden;'
                f'text-overflow:ellipsis;display:inline-block;max-width:100%;">'
                f'{_esc(c["procedure"])} · {_esc(c.get("surgeon", "-"))}</span></span>'
                f'<span style="min-width:80px;"><span style="background:{chipbg};color:{fg};'
                f'border-radius:10px;padding:2px 10px;font-size:12.5px;font-weight:500;white-space:nowrap;">{label}</span></span>'
                f'<span style="min-width:110px;font-size:13px;color:{time_fg};">{time_html}{ov_badge}</span>'
                f'</div>',
                unsafe_allow_html=True)

    with c1:
        if disp in ('not_arrived', 'holding_pre', 'in_or', 'overrun'):
            try:
                pop = st.popover("✏️", help=_EDIT_HELP)
            except TypeError:
                pop = st.popover("✏️")
            with pop:
                st.caption("เวลาคาดการณ์ใช้ห้องผ่าตัด (นาที) — แก้แทนค่า AI ได้ "
                           "(เวลาใช้ห้องตั้งแต่ room in ถึง room out)")
                # 🤖 ที่มาของคำทำนาย — หลักฐานช่วยตัดสินใจว่าควรเชื่อ AI แค่ไหน
                _ai0 = c.get('ai_predicted_min') or c.get('predicted_min')
                if _ai0:
                    _bits = [f"🤖 AI {int(_ai0)} นาที"]
                    if c.get('proc_n') is not None:
                        _nev = int(c.get('proc_n') or 0)
                        _bits.append(f"based on {_nev} เคส" if _nev
                                     else "ไม่มีเคสใกล้เคียง")
                    if c.get('confidence'):
                        _bits.append(f"มั่นใจ: {c['confidence']}")
                    st.caption(" · ".join(_bits))
                # 📏 ช่วงทำนาย 90% (split conformal — คาลิเบรตจากข้อมูลจริงปี 2567)
                _rng = c.get('predicted_range')
                if c.get('range_method') == 'conformal' and _rng:
                    st.caption(f"📏 โอกาส 9 ใน 10 เคสจะใช้เวลา "
                               f"{int(_rng[0])}–{int(_rng[1])} นาที")
                new_t = st.number_input("นาที", min_value=5, max_value=600,
                                        value=eff, key=f"tb_ov_{idx}",
                                        label_visibility="collapsed")
                if disp in ('in_or', 'overrun'):
                    st.selectbox("ส่งต่อหลังผ่า", ["ห้องรับ-ส่ง", "ห้องพักฟื้น"],
                                 key=f"dest_{idx}")

                # 🔀 ย้ายห้อง — เลือกได้ทุกห้องที่เปิดใช้ (ชื่อล้วน ไม่มีรหัส)
                _new_room = None
                if room_opts:
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
                    st.rerun()

    with c2:
        if disp == 'not_arrived':
            if st.button("รับเข้า", key=f"tb_a_{idx}", width='stretch'):
                do_arrive(idx)
        elif disp == 'holding_pre':
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
        elif disp in ('in_or', 'overrun'):
            if st.button("ผ่าเสร็จ", key=f"tb_f_{idx}", type="primary", width='stretch'):
                do_finish(idx, R, st.session_state.get(f"dest_{idx}", "ห้องรับ-ส่ง"))
        elif disp in ('holding_post', 'recovery'):
            if st.button("จำหน่าย", key=f"tb_d_{idx}", width='stretch'):
                if c.get('status') != 'discharged':  # กันกดรัว
                    c['status'] = 'discharged'
                    c['time_discharged'] = _now()
                    if mark_dirty:
                        mark_dirty(c)   # CR-2: จำหน่าย ต้องเซฟขึ้นบอร์ดกลาง
                st.rerun()

    with c3:
        if disp in _UNDO_TARGET:
            if st.button("↩️", key=f"tb_un_{idx}", width='stretch',
                         help=f"ย้อนกลับเป็น '{_UNDO_TARGET[disp]}' (กันกดพลาด)"):
                do_undo(idx)
