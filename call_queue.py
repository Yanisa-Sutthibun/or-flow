# -*- coding: utf-8 -*-
"""
call_queue.py — 🔔 ระบบเรียกคิวถัดไป (มุคกี้เคาะ wireframe rev.2 · 13 ส.ค. 2026)
════════════════════════════════════════════════════════════════════════════
จุดขายของ OR Flow: ใช้เวลาทำนายของ AI หา "เวลาเรียกผู้ป่วยคิวถัดไปขึ้นมารอ
ไม่เกิน 1 ชั่วโมง" — โมดูลนี้เป็น logic ล้วนของฟีเจอร์นั้น:
  · หาว่าเคสไหนคือ "คิวถัดไปที่ต้องเรียก" ของแต่ละห้อง (next_call_map)
  · คำนวณเวลาเรียกที่ AI แนะนำ (suggested_call_dt) — สูตรเดียวกับบรรทัด
    "เรียกคิวถัดไป ~HH:MM" ท้ายแถวเคสกำลังผ่าบน tracking_board ไม่ใช่สูตรใหม่
  · ค่าที่คนแก้ (call_override_hhmm) ชนะ AI — กติกาเดียวกับ effective_min
  · กดเรียก/ยกเลิกเรียก (apply_call / apply_undo_call)

field ใหม่ในเคส (ติดไปกับ snapshot บอร์ดกลาง → ทุกจอเห็นเหมือนกัน):
  call_override_hhmm  'HH:MM' ที่คนแก้ (None = ใช้ค่า AI)
  call_override_reason เหตุผลที่แก้
  call_time           datetime ตอนกดเรียกจริง (📣/🔔)
  call_from           จอที่กด: 'board' หรือ 'room:<เลขห้อง>'
  call_planned_hhmm   เวลาแผน (AI หรือที่แก้) แช่แข็ง ณ ตอนกดเรียก — ไว้เทียบใน log
  call_undone         True = เพิ่งกด ↩️ ยกเลิกการเรียกโดยตั้งใจ (กัน merge ดึงเวลา
                      เรียกจากเครื่องอื่นกลับมา — ดู _merge_case_no_regress)

⛔ โมดูลนี้ห้าม import streamlit — ต้องรันได้ใน tests/test_board_state.py ตรง ๆ
"""
from __future__ import annotations

from datetime import datetime, timedelta

# ⏰ เผื่อเวลาโทรตาม ward + เคลื่อนย้าย + เปลี่ยนชุด ก่อนห้องพร้อม (นาที)
#    เรียกก่อนห้องพร้อม 30 นาที → ผู้ป่วยมารอหน้าห้องราว 15-30 นาที ไม่เกิน 1 ชม.
#    (ตัวเดียวกับที่ tracking_board ใช้แสดงท้ายแถวเคสกำลังผ่า — แก้ที่นี่ที่เดียว)
CALL_LEAD_MIN = 30

# 🔔 กดกระดิ่งเร็วกว่าเวลาแนะนำเกินกี่นาที ให้เตือนว่าผู้ป่วยอาจรอเกิน 1 ชม.
CALL_EARLY_WARN_MIN = 45

_DEF_TURNOVER = 15   # เตรียมห้อง (นาที) เมื่อไม่มีข้อมูล turnover จริงของห้อง

# เหตุผลการแก้เวลาเรียก (ให้เลือกใน ✏️ — เก็บลง call_log)
CALL_EDIT_REASONS = ('ward อยู่ไกล', 'ผู้ป่วยเตรียมตัวนาน (ICU / เตียงเคลื่อนย้าย)',
                     'แพทย์สั่ง', 'อื่น ๆ')


# ─────────────────────────── helpers ───────────────────────────

def _rid(c):
    """เลขห้องจริง หรือ None (1 = placeholder ไม่ใช่ห้องจริง — กติกาเดียวกับบอร์ด)"""
    try:
        r = int(float((c or {}).get('room')))
    except (TypeError, ValueError):
        return None
    return r if r and r != 1 else None


def _ord(c):
    """ลำดับคิวจากตารางผ่าตัด — None ถ้าไม่มี/เป็น 99 (เพิ่ม Manual = ไม่ได้จัดคิว)"""
    try:
        o = int((c or {}).get('ororder'))
    except (TypeError, ValueError):
        return None
    return o if o and o != 99 else None


def _eff(c):
    """เวลาคาดใช้ห้อง (นาที) — ลำดับเดียวกับบอร์ด: คนแก้ชนะ AI"""
    try:
        return int(c.get('effective_min') or c.get('ai_predicted_min')
                   or c.get('predicted_min') or 30)
    except (TypeError, ValueError):
        return 30


def _is_emer(c):
    """สำเนา logic เคสฉุกเฉินของ tracking_board (ทำซ้ำที่นี่ กัน import streamlit)"""
    if c.get('is_emergency'):
        return True
    t = str(c.get('case_type') or c.get('op_type') or c.get('optype') or '').lower()
    return ('emer' in t) or ('urg' in t) or ('ฉุกเฉิน' in t) or ('เร่งด่วน' in t)


def _turnover(room, tov_map):
    tov = (tov_map or {}).get(room) or (tov_map or {}).get('_global') or _DEF_TURNOVER
    try:
        return float(tov)
    except (TypeError, ValueError):
        return float(_DEF_TURNOVER)


def fmt_hhmm(dt) -> str | None:
    """datetime → 'HH:MM' (None ถ้าไม่ใช่เวลา)"""
    try:
        return dt.strftime('%H:%M') if (dt is not None and hasattr(dt, 'hour')) else None
    except Exception:
        return None


def parse_hhmm(s, on_date) -> datetime | None:
    """'HH:MM' → datetime บนวันที่ที่กำหนด (คืน None ถ้า parse ไม่ได้)"""
    try:
        h, m = str(s).strip().split(':')
        return datetime(on_date.year, on_date.month, on_date.day, int(h), int(m))
    except (ValueError, AttributeError, TypeError):
        return None


def call_from_label(src) -> str:
    """'room:97' → 'จอห้อง 97' · 'board' → 'จอรับ-ส่ง' (ไว้โชว์บนบอร์ด/log)"""
    s = str(src or '')
    if s.startswith('room:'):
        return f'จอห้อง {s[5:]}'
    return 'จอรับ-ส่ง' if s == 'board' else (s or '?')


# ─────────────────────── เลือกเคส "คิวถัดไป" ───────────────────────

def is_queued(c) -> bool:
    """เคส "จัดคิวแล้ว" = มีลำดับคิวจริงจากตารางผ่าตัด · TF/Manual(99)/ฉุกเฉิน
    ไม่นับ (ตาม wireframe: เคสไม่ได้จัดคิว แถวเรียกคิวว่าง)"""
    return (_ord(c) is not None) and not c.get('is_tf') and not _is_emer(c)


def _room_queue_trusted(cases, room) -> bool:
    """เลขคิวในห้อง "ไม่ซ้ำกัน" ถึงถือว่าเชื่อได้ — กติกาเดียวกับป้าย 🔒 ล็อคคิว
    (_sched_order_html): HIS ส่งมา 1 ทั้งห้อง = ยังไม่จัดคิวจริง จะจัดหน้างาน"""
    orders = []
    for x in cases:
        if _rid(x) != room or x.get('is_tf'):
            continue
        o = _ord(x)
        if o is not None:
            orders.append(o)
    return bool(orders) and len(orders) == len(set(orders))


def next_call_case(cases, room):
    """เคสคิวถัดไปที่ต้องเรียกของห้องนี้ (ยังไม่มา + จัดคิวแล้ว + คิวเล็กสุด)
    คืน None ถ้าไม่มี/คิวห้องนี้เชื่อไม่ได้"""
    if room is None or not _room_queue_trusted(cases, room):
        return None
    cands = [x for x in cases
             if _rid(x) == room and x.get('status') == 'not_arrived'
             and is_queued(x)]
    if not cands:
        return None
    return min(cands, key=lambda x: _ord(x))


# ─────────────────────── คำนวณเวลาเรียก ───────────────────────

def suggested_call_dt(cases, case, now, tov_map=None):
    """เวลาเรียกที่ AI แนะนำ = ห้องพร้อมรับเคสนี้ - CALL_LEAD_MIN
    ห้องพร้อม = คาดออกห้องของเคสสุดท้ายก่อนหน้า + เตรียมห้อง (turnover)
    ไล่โซ่: เคสกำลังผ่า → เคสรอผ่าตัดในห้อง → เคสยังไม่มาที่คิวเล็กกว่า
    ยังไม่กดเรียก/ไม่ได้แก้มือ = ค่านี้ขยับตามสถานการณ์จริงเอง (คำนวณสดทุกรอบ)"""
    room = _rid(case)
    if room is None:
        return None
    tov = _turnover(room, tov_map)

    # จุดตั้งต้น: คาดออกห้องของเคสที่กำลังผ่าอยู่ (ent + effective_min —
    # เลขเดียวกับบรรทัด "ออกห้อง ~" บนบอร์ด · เคสเกินเวลา = ค่าอยู่ในอดีต
    # → เวลาเรียกกลายเป็น "เลยเวลา" ให้หน้างานเห็นว่าต้องตัดสินใจเอง)
    t = None
    cur = next((x for x in cases
                if x.get('status') == 'in_or' and _rid(x) == room), None)
    if cur is not None:
        ent = cur.get('time_entered_or')
        if ent is not None and hasattr(ent, 'hour'):
            t = ent + timedelta(minutes=_eff(cur))

    # เคสคั่นกลางก่อนถึงคิวเคสนี้: รอผ่าตัดในห้อง (มาแล้ว รอเข้า) +
    # ยังไม่มาที่คิวเล็กกว่า (ต้องเรียก/ผ่าก่อนเคสนี้)
    my_ord = _ord(case)
    ahead = [x for x in cases
             if x is not case and _rid(x) == room and (
                 x.get('status') == 'holding_pre'
                 or (x.get('status') == 'not_arrived' and is_queued(x)
                     and my_ord is not None and (_ord(x) or 0) < my_ord))]
    if t is None:
        if not ahead:
            return now          # ห้องว่าง ไม่มีใครคั่น : เรียกได้เลย
        t = now
    for x in sorted(ahead, key=lambda x: (_ord(x) or 999)):
        t = t + timedelta(minutes=tov + _eff(x))
    return t + timedelta(minutes=tov - CALL_LEAD_MIN)


def effective_call_dt(cases, case, now, tov_map=None):
    """เวลาเรียกที่ใช้จริง — (datetime, 'override'|'ai') · คนแก้ชนะ AI และ
    ค่าที่แก้ "ล็อก" ไม่ขยับตามสถานการณ์ (ตามกติกาที่เคาะใน wireframe ④)"""
    ov = parse_hhmm(case.get('call_override_hhmm'), now.date())
    if ov is not None:
        return ov, 'override'
    return suggested_call_dt(cases, case, now, tov_map), 'ai'


def next_call_map(cases, now, tov_map=None):
    """{room: (case, เวลาเรียกที่ใช้จริง, 'override'|'ai', เวลาที่ AI แนะนำ)}
    ของทุกห้องที่มีคิวถัดไปให้เรียก — ช่องสุดท้ายไว้โชว์ค่า AI คู่กับค่าที่คนแก้"""
    out = {}
    for room in {_rid(c) for c in cases} - {None}:
        nxt = next_call_case(cases, room)
        if nxt is None:
            continue
        ai_dt = suggested_call_dt(cases, nxt, now, tov_map)
        ov = parse_hhmm(nxt.get('call_override_hhmm'), now.date())
        dt, src = (ov, 'override') if ov is not None else (ai_dt, 'ai')
        if dt is not None:
            out[room] = (nxt, dt, src, ai_dt)
    return out


# ─────────────────────── การกดเรียก / ยกเลิก ───────────────────────

def apply_call(case, now, source, planned_hhmm=None) -> bool:
    """บันทึกว่า "เรียกแล้ว" (📣 จอรับ-ส่ง / 🔔 จอห้อง) — คืน False ถ้ากดซ้ำ
    planned_hhmm = เวลาแผน (AI/ที่แก้) ณ ตอนกด — แช่แข็งไว้เทียบใน log วิจัย"""
    if case.get('call_time') is not None:
        return False            # กันกดรัว/สองจอกดพร้อมกัน
    case['call_time'] = now
    case['call_from'] = source
    if planned_hhmm:
        case['call_planned_hhmm'] = planned_hhmm
    case['call_undone'] = False
    return True


def apply_undo_call(case) -> bool:
    """↩️ ยกเลิกการเรียก (กดผิด) — ตั้ง call_undone กัน merge ดึงเวลาเรียกคืน"""
    if case.get('call_time') is None:
        return False
    case['call_time'] = None
    case['call_from'] = None
    case['call_planned_hhmm'] = None
    case['call_undone'] = True
    return True


def merge_call_forward(out, theirs):
    """🔁 ใช้ตอน merge หลายเครื่อง (เรียกจาก _merge_case_no_regress):
    เครื่องที่ยังไม่เห็นการเรียก (out ไม่มี call_time) ห้ามลบเวลาเรียกที่เครื่องอื่น
    บันทึกไปแล้ว — ยกเว้นเครื่องนี้เพิ่งกด ↩️ ยกเลิกเอง (call_undone)
    ทำงานกับทั้ง dict ปกติและ dict ที่ serialize แล้ว ({'__dt__': ...})"""
    try:
        if (theirs and theirs.get('call_time')
                and not out.get('call_time') and not out.get('call_undone')):
            for k in ('call_time', 'call_from', 'call_planned_hhmm'):
                out[k] = theirs.get(k)
    except Exception:
        pass
    return out
