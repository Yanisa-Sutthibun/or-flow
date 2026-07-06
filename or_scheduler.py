# -*- coding: utf-8 -*-
"""
or_scheduler.py — 🗓️ ผู้ช่วยจัดคิวผ่าตัด (AI) · ต่อยอด Wu et al. 2025 (Fig 3/4)
════════════════════════════════════════════════════════════════════════════
ปัญหา: เคสจาก HIS ไม่มีลำดับคิวมาตั้งแต่ลงนัด → AI ลองเรียงหลายกลยุทธ์
แล้วเลือกตามกติกา พร้อม "โชว์วิธีคิด" (explainability — จุดที่ Wu ไม่มี)

🔒 กฎเหล็ก (มุคกี้กำหนด 5 ก.ค. 2026):
  1. แผนหลัก (primary) ห้ามย้ายเคสข้ามห้อง — ทีมห้องอื่นไม่พร้อมรับเคสต่างสาขา
  2. ห้อง EM รับได้ทั้ง elective + emergency — ไม่กันห้องว่างไว้
  3. ห้องที่ปิดใช้งาน (หน้า ⚙️) ห้ามจัดเคสเข้าเด็ดขาด (OR1 = ห้องเก็บของแล้ว)

กติกาเลือกแผน: ① เคสรับเวร (คาดออกห้องหลังเส้นตาย 15:30 — นับจากขอบบนช่วง
กันเสี่ยง) ต้องน้อยสุด (เป้า 0) → ② ใช้ห้องคุ้มสุด → ③ เลิกเร็วสุด
ถ้าดีสุดแล้วยังรับเวร > 0 → โชว์แผน + เตือน + ชี้เคสที่ควรพิจารณาเลื่อน (คนตัดสิน)

การเชื่อมกับบอร์ด (ตารางผ่าตัดวันนี้):
  - อ่านเคสสดจาก st.session_state.patient_cases ทุกครั้ง → บอร์ดเปลี่ยน = คิวคำนวณใหม่
  - จัดเฉพาะเคส "ยังไม่มา" · เคสที่เข้า flow แล้ว/มีคิวแท้จริง (ororder ไม่ซ้ำ) = ล็อก 🔒
  - "ส่งแผนเข้าบอร์ด" เขียน ororder + เวลาเริ่มตามแผนกลับเข้าบอร์ด (เก็บเวลานัดเดิมไว้ใน
    orig_sched) → หน้างานแก้ manual ต่อได้ตามปกติ (✏️/ปุ่ม) — แผนเป็นคำแนะนำ ไม่ใช่คำสั่ง

ช่วงกันเสี่ยง: เคสบนบอร์ดมีช่วง 90% (conformal) — ประมาณขอบบน P80 ด้วย
hi80 ≈ p50 + 0.60×(hi90 − p50) (สัดส่วน q80/q90 ของ thesis_ML = 62.1/103.2)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

_BKK = timezone(timedelta(hours=7))
WORK_START_MIN = 8 * 60          # 08:00
DEADLINE_MIN = 15 * 60 + 30      # 15:30 — เส้นตายออกห้อง (เคสรับเวร)
DAY_END_MIN = 16 * 60            # 16:00 — ขอบขวาของ Gantt
_P80_FRAC = 0.60                 # hi80 ≈ p50 + 0.6*(hi90-p50)

STRATEGIES = [
    ('A', 'ตามเวลานัดเดิม'),
    ('B', 'เคสสั้นขึ้นก่อน (SPT)'),
    ('C', 'เคสยาวขึ้นก่อน (LPT)'),
    ('D', 'ช่วงไม่แน่นอนกว้างขึ้นก่อน (กันเสี่ยง)'),
]
RISK_LEVELS = [('p80', '🛡️ เผื่อเวลาพอดี (แนะนำ)'),
               ('p90', '🛡️🛡️ เผื่อเวลามาก — ปลอดภัยไว้ก่อน'),
               ('p50', 'ไม่เผื่อ — เชื่อค่าคาดการณ์ตรง ๆ')]


def _mins(h, m):
    return f"{int(h):02d}:{int(m):02d}"


def _fmt(minutes):
    minutes = int(round(minutes))
    return _mins(minutes // 60, minutes % 60)


def _p50(c) -> float:
    return float(c.get('effective_min') or c.get('ai_predicted_min')
                 or c.get('predicted_min') or 30)


def _hi(c, risk: str) -> float:
    """ขอบบนของเวลาเคสตามระดับกันเสี่ยง (ใช้ตัดสิน 'เคสรับเวร')"""
    p50 = _p50(c)
    rng = c.get('predicted_range')
    hi90 = None
    try:
        if rng and len(rng) == 2 and float(rng[1]) > p50:
            hi90 = float(rng[1])
    except (TypeError, ValueError):
        hi90 = None
    if hi90 is None:
        hi90 = p50 * 1.5     # fallback heuristic เดิมของระบบ
    if risk == 'p50':
        return p50
    if risk == 'p90':
        return hi90
    return p50 + _P80_FRAC * (hi90 - p50)


def _sched_min_of(c):
    h = c.get('sched_hour')
    if h is None:
        return None
    return int(h) * 60 + int(c.get('sched_min') or 0)


def split_locked(room_cases):
    """แยกเคส 'มีคิวแท้จริง' (ororder ใช้ได้และไม่ซ้ำในห้อง) = ล็อก 🔒
    ที่เหลือ = อิสระ ให้ AI จัด · คิวล็อกเรียงตาม ororder และอยู่หัวแถวเสมอ"""
    orders = [c.get('ororder') for c in room_cases]
    counts = {}
    for o in orders:
        counts[o] = counts.get(o, 0) + 1
    locked, free = [], []
    for c in room_cases:
        o = c.get('ororder')
        try:
            o_ok = o is not None and int(o) > 0 and counts.get(o, 0) == 1
        except (TypeError, ValueError):
            o_ok = False
        (locked if o_ok else free).append(c)
    locked.sort(key=lambda c: int(c.get('ororder') or 999))
    return locked, free


def order_free(free, strat: str, risk: str):
    if strat == 'A':
        return sorted(free, key=lambda c: (_sched_min_of(c) is None,
                                           _sched_min_of(c) or 9999))
    if strat == 'B':
        return sorted(free, key=_p50)
    if strat == 'C':
        return sorted(free, key=_p50, reverse=True)
    return sorted(free, key=lambda c: _hi(c, risk) - _p50(c), reverse=True)  # D


def simulate_room(ordered, turnover: float, risk: str,
                  start_min: float = WORK_START_MIN):
    """เดินตารางห้องเดียว: cursor เดินด้วย P50 + turnover ·
    'รับเวร' ตัดสินจากขอบบน (start + hi) เกินเส้นตาย · คืน list ของ entry"""
    cursor = float(start_min)
    entries = []
    for c in ordered:
        start = cursor
        end50 = start + _p50(c)
        end_hi = start + _hi(c, risk)
        entries.append({'case': c, 'start': start, 'end50': end50,
                        'end_hi': end_hi,
                        'handover': end_hi > DEADLINE_MIN})
        cursor = end50 + turnover
    return entries


def plan_metrics(rooms_entries):
    n_handover = sum(1 for es in rooms_entries.values()
                     for e in es if e['handover'])
    latest = max((e['end50'] for es in rooms_entries.values() for e in es),
                 default=WORK_START_MIN)
    busy = sum(_p50(e['case']) for es in rooms_entries.values() for e in es)
    n_rooms = sum(1 for es in rooms_entries.values() if es)
    capacity = max(n_rooms, 1) * (DEADLINE_MIN - WORK_START_MIN)
    return {'handover': n_handover, 'latest_end': latest,
            'util': busy / capacity * 100 if capacity else 0}


def build_primary(cases_by_room, tov_map, risk: str):
    """ลองทุกกลยุทธ์ (เรียงเฉพาะเคสอิสระ ภายในห้องเดิม) → เลือกตามกติกา"""
    results = {}
    for sid, _label in STRATEGIES:
        rooms_entries = {}
        for rm, rcs in cases_by_room.items():
            locked, free = split_locked(rcs)
            ordered = locked + order_free(free, sid, risk)
            tov = float((tov_map or {}).get(rm)
                        or (tov_map or {}).get('_global') or 15)
            rooms_entries[rm] = simulate_room(ordered, tov, risk)
        results[sid] = {'rooms': rooms_entries,
                        'metrics': plan_metrics(rooms_entries)}
    best = min(results, key=lambda s: (results[s]['metrics']['handover'],
                                       -results[s]['metrics']['util'],
                                       results[s]['metrics']['latest_end']))
    return results, best


def start_sensitivity(entries, turnover: float, risk: str):
    """⏰ ต่อห้อง: เริ่มช้าสุดเท่าไรยังรับเวร 0, ช้ากว่านั้นรับเวรกี่เคส
    (คำนวณย้อนจากเส้นตาย — ordered ตามแผนแล้ว)"""
    if not entries:
        return []
    ordered = [e['case'] for e in entries]
    steps = []
    # ถ้าเริ่มที่เวลา t เคส k (นับจากท้าย) จะรับเวรเมื่อ t > threshold_k
    # threshold ของ "รับเวร ≤ n เคส" = เส้นตาย − (เวลาถึงขอบบนของเคสตัวที่ len-n จากหัว)
    for n_over in range(0, len(ordered) + 1):
        keep = ordered[:len(ordered) - n_over] if n_over else ordered
        if not keep:
            steps.append((n_over, None))
            break
        cursor = 0.0
        last_hi = 0.0
        for c in keep:
            last_hi = cursor + _hi(c, risk)
            cursor += _p50(c) + turnover
        latest_start = DEADLINE_MIN - last_hi
        steps.append((n_over, latest_start))
        if latest_start >= WORK_START_MIN and n_over == 0:
            pass
    return steps


def build_ideal(cases_by_room, rooms_enabled, tov_map, risk: str):
    """🔭 แผนอุดมคติ (ย้ายข้ามห้องได้ — ดูอย่างเดียว ไม่มีปุ่มใช้จริง):
    เคสล็อกอยู่ห้องเดิม · เคสอิสระรวม pool แล้ว LPT ลงห้องที่ว่างเร็วสุด"""
    cursors, rooms_entries, tovs = {}, {}, {}
    pool = []
    for rm in rooms_enabled:
        tovs[rm] = float((tov_map or {}).get(rm)
                         or (tov_map or {}).get('_global') or 15)
        cursors[rm] = float(WORK_START_MIN)
        rooms_entries[rm] = []
    for rm, rcs in cases_by_room.items():
        locked, free = split_locked(rcs)
        pool.extend(free)
        if rm not in cursors:      # ห้องไม่ได้เปิด — คิวล็อกยังต้องอยู่ห้องเดิม
            cursors[rm] = float(WORK_START_MIN)
            tovs[rm] = float((tov_map or {}).get('_global') or 15)
            rooms_entries[rm] = []
        for c in locked:
            start = cursors[rm]
            rooms_entries[rm].append({'case': c, 'start': start,
                                      'end50': start + _p50(c),
                                      'end_hi': start + _hi(c, risk),
                                      'handover': start + _hi(c, risk) > DEADLINE_MIN})
            cursors[rm] = start + _p50(c) + tovs[rm]
    for c in sorted(pool, key=_p50, reverse=True):       # LPT ข้ามห้อง
        rm = min(cursors, key=lambda r: cursors[r])
        start = cursors[rm]
        rooms_entries[rm].append({'case': c, 'start': start,
                                  'end50': start + _p50(c),
                                  'end_hi': start + _hi(c, risk),
                                  'handover': start + _hi(c, risk) > DEADLINE_MIN})
        cursors[rm] = start + _p50(c) + tovs[rm]
    return {'rooms': rooms_entries, 'metrics': plan_metrics(rooms_entries)}


# ════════════════════════════════ UI ════════════════════════════════

def _gantt_html(rooms_entries, room_label_fn, locked_ids):
    """Gantt HTML ต่อห้อง (สเกล 08:00→16:00) — แบบ wireframe ที่ approve แล้ว"""
    span = DAY_END_MIN - WORK_START_MIN

    def pct(m):
        return max(0.0, min(100.0, (m - WORK_START_MIN) / span * 100))

    dl = pct(DEADLINE_MIN)
    rows = []
    for rm in sorted(rooms_entries):
        es = rooms_entries[rm]
        if not es:
            continue
        bars = []
        for e in es:
            c = e['case']
            left, w = pct(e['start']), max(pct(e['end50']) - pct(e['start']), 1.5)
            whk_w = max(pct(e['end_hi']) - pct(e['end50']), 0)
            lock = '🔒 ' if str(c.get('id')) in locked_ids else ''
            bg, bd, fg = ('#F7C1C1', '#E24B4A', '#501313') if e['handover'] \
                else ('#B5D4F4', '#85B7EB', '#042C53')
            label = f"{lock}{str(c.get('procedure') or '')[:18]} · {int(_p50(c))}น."
            tip = (f"{c.get('name','')} | เริ่ม {_fmt(e['start'])} | "
                   f"คาดเสร็จ {_fmt(e['end50'])} (ขอบบน {_fmt(e['end_hi'])})"
                   + (' | ⚠️ คาดรับเวร' if e['handover'] else ''))
            bars.append(
                f'<div title="{tip}" style="position:absolute;left:{left:.2f}%;'
                f'width:{w:.2f}%;top:3px;height:24px;background:{bg};'
                f'border:1px solid {bd};color:{fg};border-radius:4px;'
                f'font-size:10.5px;display:flex;align-items:center;'
                f'justify-content:center;white-space:nowrap;overflow:hidden;">'
                f'{label}</div>')
            if whk_w > 0.3:
                bars.append(
                    f'<div style="position:absolute;left:{pct(e["end50"]):.2f}%;'
                    f'width:{whk_w:.2f}%;top:14px;height:2px;'
                    f'border-top:2px dashed #BA7517;"></div>')
        rows.append(
            f'<div style="display:flex;align-items:center;gap:8px;margin:5px 0;">'
            f'<span style="min-width:88px;font-size:12.5px;font-weight:600;'
            f'color:#1565c0;">{room_label_fn(rm)}</span>'
            f'<div style="position:relative;flex:1;height:30px;background:#fff;'
            f'border:1px solid #eef2f6;border-radius:6px;">'
            f'<div style="position:absolute;left:{dl:.2f}%;top:0;bottom:0;'
            f'width:2px;background:#E24B4A;"></div>{"".join(bars)}</div></div>')
    axis = ('<div style="position:relative;margin:0 0 2px 96px;height:14px;'
            'font-size:10.5px;color:#94a3b8;">'
            + ''.join(f'<span style="position:absolute;left:{pct(h*60):.2f}%">'
                      f'{h:02d}:00</span>' for h in (8, 10, 12, 14))
            + f'<span style="position:absolute;left:{dl:.2f}%;color:#A32D2D;'
              f'font-weight:600">15:30</span></div>')
    return axis + ''.join(rows)


def page_scheduler():
    from main_or_pages import (_enabled_room_options, _mark_board_dirty,
                               _save_board_snapshot)
    from room_config import room_label
    from tracking_board import _turnover_map

    st.caption("🗓️ จัดคิวเคสที่ยังไม่มีลำดับ — AI ลอง 4 กลยุทธ์แล้วเลือกตามกติกา "
               "(อ่านจากบอร์ดสด: บอร์ดเปลี่ยน → คิวคำนวณใหม่อัตโนมัติ)")

    cases = st.session_state.get('patient_cases') or []
    room_opts = _enabled_room_options()          # 🔒 กฎ 3: เฉพาะห้องที่เปิดใช้
    enabled_rooms = [rn for rn, _ in room_opts]

    schedulable = [c for c in cases if c.get('status') == 'not_arrived']
    in_flow = len(cases) - len(schedulable)
    no_room = [c for c in schedulable if not c.get('room')
               or c.get('room') not in enabled_rooms]
    schedulable = [c for c in schedulable if c.get('room') in enabled_rooms]

    if not schedulable:
        st.info("ยังไม่มีเคส 'ยังไม่มา' ให้จัดคิว — อัปโหลดตารางที่ ⚙️ ตั้งค่า "
                "หรือเปิด 🎬 สาธิต ที่หน้าตารางผ่าตัดก่อน")
        return

    cases_by_room = {}
    for c in schedulable:
        cases_by_room.setdefault(int(c['room']), []).append(c)

    n_locked = sum(len(split_locked(rcs)[0]) for rcs in cases_by_room.values())
    n_free = len(schedulable) - n_locked

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("เคสจัดคิวได้", len(schedulable))
    m2.metric("มีคิวเดิม 🔒", n_locked)
    m3.metric("AI จัดให้", n_free)
    m4.metric("เส้นตายออกห้อง", "15:30")
    if in_flow:
        st.caption(f"ℹ️ อีก {in_flow} เคสเข้ากระบวนการแล้ว (รอผ่า/กำลังผ่า/เสร็จ) — ไม่ถูกจัด")
    if no_room:
        st.warning(f"⚠️ {len(no_room)} เคสไม่มีห้อง/ห้องถูกปิด — จัดไม่ได้ "
                   f"(ไปกำหนดห้องผ่าน ✏️ บนบอร์ดก่อน): "
                   + ' · '.join(str(c.get('procedure', ''))[:20] for c in no_room[:5]))

    risk = st.radio(
        "เผื่อเวลาแค่ไหนดี? (เคสจริงมักใช้เวลางอกกว่าที่คาด — ยิ่งเผื่อมาก "
        "ระบบยิ่งระวังไม่ให้มีเคสออกห้องหลัง 15:30)",
        [r[1] for r in RISK_LEVELS], horizontal=True,
        key='schd_risk', label_visibility='visible',
        help="สำหรับอ้างอิงเชิงวิชาการ: เผื่อพอดี = ขอบบน ~P80 · "
             "เผื่อมาก = ขอบบนช่วงความมั่นใจ 90% (conformal) · "
             "ไม่เผื่อ = ค่ากลาง P50 — ระดับที่เลือกใช้เฉพาะการตัดสิน "
             "'เคสเสี่ยงรับเวร' ไม่ได้ทำให้ตารางหลวมขึ้น")
    risk_key = next(k for k, lbl in RISK_LEVELS if lbl == risk)

    tov_map = _turnover_map()
    results, best = build_primary(cases_by_room, tov_map, risk_key)

    # ---- ตารางเทียบกลยุทธ์ ----
    st.markdown('<div style="font-size:14px;font-weight:700;color:#334155;'
                'margin:10px 0 4px;">AI ลองจัด 4 แบบ — กติกา: ① รับเวรน้อยสุด '
                '→ ② ใช้ห้องคุ้มสุด → ③ เลิกเร็วสุด</div>', unsafe_allow_html=True)
    _rows_html = []
    for sid, slabel in STRATEGIES:
        m = results[sid]['metrics']
        is_best = (sid == best)
        chip = ('<span style="background:#3B6D11;color:#fff;border-radius:999px;'
                'padding:1px 10px;font-size:11.5px;">✓ เลือกแผนนี้</span>' if is_best
                else ('<span style="color:#94a3b8;font-size:11.5px;">ผ่าน</span>'
                      if m['handover'] == 0 else
                      '<span style="color:#c0392b;font-size:11.5px;">ตกกติกา ①</span>'))
        bg = 'background:#EAF3DE;' if is_best else ''
        hv = (f'<span style="color:#c0392b;">{m["handover"]} เคส</span>'
              if m['handover'] else '0 เคส')
        _rows_html.append(
            f'<tr style="{bg}"><td style="padding:5px 8px;">{sid} · {slabel}</td>'
            f'<td style="padding:5px 8px;">{hv}</td>'
            f'<td style="padding:5px 8px;">{_fmt(m["latest_end"])}</td>'
            f'<td style="padding:5px 8px;">{m["util"]:.0f}%</td>'
            f'<td style="padding:5px 8px;">{chip}</td></tr>')
    st.markdown(
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<tr style="color:#64748b;font-size:12px;border-bottom:1px solid #eef2f6;">'
        '<th style="text-align:left;padding:5px 8px;">กลยุทธ์เรียงเคสอิสระ</th>'
        '<th style="text-align:left;padding:5px 8px;">เคสรับเวร</th>'
        '<th style="text-align:left;padding:5px 8px;">เลิกช้าสุด</th>'
        '<th style="text-align:left;padding:5px 8px;">ใช้ห้อง</th>'
        '<th style="text-align:left;padding:5px 8px;">ผล</th></tr>'
        + ''.join(_rows_html) + '</table>', unsafe_allow_html=True)

    best_plan = results[best]
    if best_plan['metrics']['handover'] > 0:
        _over = [e for es in best_plan['rooms'].values() for e in es
                 if e['handover']]
        st.error(f"⚠️ เคสล้นวัน: แผนที่ดีที่สุดยังคาดรับเวร "
                 f"{best_plan['metrics']['handover']} เคส — เคสที่ควรพิจารณาเลื่อน: "
                 + ' · '.join(f"{str(e['case'].get('procedure',''))[:25]} "
                              f"(คาดออก {_fmt(e['end_hi'])})" for e in _over)
                 + " — การเลื่อนเป็นการตัดสินใจของหัวหน้าเวร")

    # ---- Gantt แผนหลัก ----
    st.markdown(f'<div style="font-size:14px;font-weight:700;color:#334155;'
                f'margin:14px 0 4px;">แผนที่แนะนำ (แบบ {best}) — '
                f'🔒 คิวเดิม · เส้นประส้ม = ขอบบนช่วงกันเสี่ยง · '
                f'เส้นแดง = เส้นตาย 15:30</div>', unsafe_allow_html=True)
    locked_ids = {str(c.get('id'))
                  for rcs in cases_by_room.values()
                  for c in split_locked(rcs)[0]}
    st.markdown(_gantt_html(best_plan['rooms'], room_label, locked_ids),
                unsafe_allow_html=True)

    # ---- ⏰ ความไวต่อเวลาเริ่ม ----
    with st.expander("⏰ ถ้าห้องเริ่มช้า จะรับเวรกี่เคส? (ความไวต่อเวลาเริ่มจริง)",
                     expanded=True):
        st.caption("ตารางผ่าตัดคำนวณจากสมมติเริ่ม 08:00 — แต่หน้างานอาจเริ่มช้า "
                   "ตารางนี้บอกว่าแต่ละห้อง 'ทนได้ถึงกี่โมง'")
        for rm in sorted(best_plan['rooms']):
            es = best_plan['rooms'][rm]
            if not es:
                continue
            tov = float((tov_map or {}).get(rm)
                        or (tov_map or {}).get('_global') or 15)
            steps = start_sensitivity(es, tov, risk_key)
            parts = []
            for n_over, latest in steps[:3]:
                if latest is None:
                    break
                if latest < WORK_START_MIN:
                    parts.append(f"เริ่ม 08:00 ก็คาดรับเวร ≥{n_over} เคส")
                    break
                parts.append(f"เริ่มก่อน {_fmt(latest)} → รับเวร ≤{n_over} เคส")
            st.markdown(f"**{room_label(rm)}** — " + ' · '.join(parts),
                        unsafe_allow_html=True)

    # ---- 🔭 แผนอุดมคติ ----
    with st.expander("🔭 แผนอุดมคติ (ideal — ย้ายข้ามห้องได้) · ดูเปรียบเทียบเท่านั้น",
                     expanded=False):
        ideal = build_ideal(cases_by_room, enabled_rooms, tov_map, risk_key)
        im, pm = ideal['metrics'], best_plan['metrics']
        st.caption("⚠️ ไม่ใช่แผนปฏิบัติ — หน้างานไม่ย้ายเคสข้ามห้อง (ทีมไม่พร้อมรับ"
                   "เคสต่างสาขา) แสดงเพื่อวัดว่าข้อจำกัดนี้มีต้นทุนเท่าไร")
        st.markdown(f"ถ้าย้ายข้ามห้องได้อิสระ: รับเวร {im['handover']} เคส "
                    f"(แผนจริง {pm['handover']}) · เลิกช้าสุด {_fmt(im['latest_end'])} "
                    f"(แผนจริง {_fmt(pm['latest_end'])}) · ใช้ห้อง {im['util']:.0f}% "
                    f"(แผนจริง {pm['util']:.0f}%)")
        st.markdown(_gantt_html(ideal['rooms'], room_label, locked_ids),
                    unsafe_allow_html=True)

    # ---- 💡 วิธีคิด ----
    with st.expander("💡 วิธีคิดของ AI", expanded=False):
        risk_note = {'p80': "ขอบบน ~P80 (p50 + 0.60×(hi90−p50) — สัดส่วน q80/q90 "
                            "ของ thesis_ML = 62.1/103.2)",
                     'p90': "ขอบบนช่วง 90% (conformal)",
                     'p50': "ค่ากลาง P50 (ไม่เผื่อความไม่แน่นอน)"}[risk_key]
        st.markdown(
            f"1. **ทำนายเวลา + ช่วงต่อเคส** — ใช้ค่าบนบอร์ด (thesis_ML หรือค่าที่พยาบาล ✏️ ทับ)\n"
            f"2. **ล็อกเคสมีคิวเดิม {n_locked} เคส 🔒** — คิวที่ตกลงกันแล้วไม่ขยับ (อยู่หัวแถวตาม ororder)\n"
            f"3. **เคสอิสระ {n_free} เคส ลองเรียง 4 กลยุทธ์** ภายในห้องเดิมเท่านั้น "
            f"(กฎเหล็ก: ไม่ย้ายข้ามห้อง · ห้องปิดไม่จัด · ห้อง EM จัด elective ได้ปกติ)\n"
            f"4. **ตัดสิน 'เคสรับเวร' จาก{risk_note}** — เคสที่ขอบบนเกิน 15:30 นับเป็นรับเวร\n"
            f"5. **เลือกแผน {best}** — รับเวรน้อยสุด → ใช้ห้องคุ้มสุด → เลิกเร็วสุด · "
            f"เคสช่วงกว้างถูกดันขึ้นเช้า เหลือกันชนท้ายวัน\n\n"
            f"หมายเหตุ: ตาราง (Gantt) เดินด้วยค่ากลาง P50 + turnover รายห้องจากข้อมูลจริง — "
            f"ช่วงกันเสี่ยงใช้เฉพาะการตัดสินรับเวร ไม่ได้ถ่างตารางให้หลวม")

    # ---- 📤 ส่งแผนเข้าบอร์ด ----
    st.markdown("---")
    c_ok, c_btn = st.columns([3, 2])
    _confirm = c_ok.checkbox(
        f"ยืนยันส่งแผน {best} เข้า OR Board — อัปเดตลำดับ (ororder) + เวลาเริ่มตามแผน "
        f"ของเคสอิสระ {n_free} เคส (คิวล็อก 🔒 ไม่ถูกแตะ · หน้างานแก้ต่อได้ตามปกติ)",
        key='schd_confirm')
    if c_btn.button("📤 ส่งแผนเข้า OR Board", type="primary",
                    use_container_width=True, disabled=not _confirm,
                    key='schd_apply'):
        n_upd = 0
        for rm, es in best_plan['rooms'].items():
            for seq, e in enumerate(es, start=1):
                c = e['case']
                if str(c.get('id')) in locked_ids:
                    continue
                if 'orig_sched' not in c:      # เก็บเวลานัดเดิมจาก HIS ไว้อ้างอิง
                    c['orig_sched'] = (c.get('sched_hour'), c.get('sched_min'))
                c['ororder'] = seq
                c['sched_hour'] = int(e['start'] // 60)
                c['sched_min'] = int(e['start'] % 60)
                c['is_tf'] = False
                _mark_board_dirty(c)
                n_upd += 1
            for seq, e in enumerate(es, start=1):   # ororder ของคิวล็อกให้ต่อเนื่อง
                if str(e['case'].get('id')) in locked_ids:
                    e['case']['ororder'] = seq
        if n_upd:
            _save_board_snapshot(cases)
            st.session_state['_board_dirty'] = False
        st.success(f"✅ ส่งแผนแล้ว — อัปเดต {n_upd} เคส · ไปดูที่ 📋 ตารางผ่าตัด "
                   f"(เวลาบนบอร์ด = เวลาเริ่มตามแผน · เวลานัดเดิมเก็บไว้ใน orig_sched)")
