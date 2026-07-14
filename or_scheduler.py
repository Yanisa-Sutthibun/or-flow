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
  - UI v3 (14 ก.ค. 2026 — มุคกี้สั่งลดความซับซ้อน): ปุ่มเดียว + 2 ตาราง
    ① ใช้จริง (ห้องเดิม·คิวล็อก) · ② AI จัดอิสระ (ย้ายคิว/ห้องได้ — ดูเปรียบเทียบ)
    ไม่มีปุ่มส่งเข้าบอร์ด = หน้านี้เป็นคำแนะนำอ่านอย่างเดียว · ไม่โชว์เวลานาฬิกา
    (first case on time ยังทำไม่ได้) — โชว์เฉพาะลำดับคิว + เวลาคาดใช้ต่อเคส

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


# ═════════════════════ UI (v3 — 14 ก.ค. 2026) ═════════════════════
# มุคกี้สั่งลดความซับซ้อน: ปุ่มเดียว + 2 ตาราง — Gantt / ตารางเทียบ 4 กลยุทธ์ /
# radio เผื่อเวลา / sensitivity / ปุ่มส่งเข้าบอร์ด ถอดออกแล้ว (โค้ดเดิมดู git history)
# กันเสี่ยงล็อกที่ P80 (ค่าแนะนำเดิม) · start_sensitivity คงไว้เผื่อกลับมาใช้

_RISK_DEFAULT = 'p80'

_TD = 'padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:middle;'


def _dur_txt(mins):
    m = int(round(float(mins)))
    h, mm = divmod(m, 60)
    if h and mm:
        return f"~{h} ชม. {mm} น."
    return f"~{h} ชม." if h else f"~{mm} น."


def _sect_html(no, title, tag, n_handover):
    chip = ('<span style="color:#2e7d32;font-weight:700;">✅ คาดรับเวร 0 เคส</span>'
            if n_handover == 0 else
            f'<span style="color:#c0392b;font-weight:700;">⚠️ คาดรับเวร '
            f'{n_handover} เคส</span>')
    return (f'<div style="display:flex;justify-content:space-between;'
            f'align-items:baseline;margin:18px 0 2px;">'
            f'<span style="font-size:16px;font-weight:700;color:#0d47a1;">'
            f'{no} {title} <span style="font-size:11.5px;color:#64748b;'
            f'font-weight:400;">— {tag}</span></span>'
            f'<span style="font-size:13.5px;">{chip}</span></div>')


def _queue_table_html(rooms_entries, room_label_fn, locked_ids,
                      notes=None, default_note='AI จัด'):
    """ตารางคิว group ตามห้อง: คิวที่ | หัตถการ·แพทย์ | เวลาคาดใช้ | หมายเหตุ"""
    notes = notes or {}
    th = ('<th style="background:#eef4fb;color:#0d47a1;font-size:12.5px;'
          'text-align:left;padding:7px 10px;border-bottom:2px solid #d7e3f4;'
          '{w}">{t}</th>')
    rows = ['<table style="width:100%;border-collapse:collapse;'
            'font-size:13.5px;margin:4px 0 10px;">',
            '<tr>' + th.format(w='width:52px;', t='คิวที่')
            + th.format(w='', t='หัตถการ · แพทย์')
            + th.format(w='width:110px;', t='เวลาคาดใช้')
            + th.format(w='width:150px;', t='หมายเหตุ') + '</tr>']
    for rm in sorted(rooms_entries):
        es = rooms_entries[rm]
        if not es:
            continue
        rows.append(f'<tr><td colspan="4" style="{_TD}background:#f6f9fc;'
                    f'font-weight:700;color:#334155;font-size:13px;">'
                    f'🏥 {room_label_fn(rm)} ({len(es)} เคส)</td></tr>')
        for seq, e in enumerate(es, start=1):
            c = e['case']
            cid = str(c.get('id'))
            locked = cid in locked_ids
            q = ('<span style="display:inline-block;min-width:22px;height:22px;'
                 'border-radius:50%;background:{bg};color:#fff;text-align:center;'
                 'line-height:22px;font-size:12px;font-weight:700;">{s}</span>'
                 ).format(bg='#607d8b' if locked else '#1565c0',
                          s='🔒' if locked else seq)
            if e['handover']:
                note = ('<span style="color:#c0392b;font-weight:700;'
                        'font-size:12.5px;">⚠️ เสี่ยงรับเวร</span>')
            elif locked:
                note = '<span style="color:#94a3b8;font-size:12.5px;">คิวเดิม</span>'
            elif cid in notes:
                note = ('<span style="background:#ede7f6;color:#5e35b1;'
                        'border-radius:999px;padding:1px 9px;font-size:11.5px;'
                        f'font-weight:600;">{notes[cid]}</span>')
            else:
                note = (f'<span style="color:#94a3b8;font-size:12.5px;">'
                        f'{default_note}</span>')
            bg = 'background:#fff5f5;' if e['handover'] else ''
            proc = str(c.get('procedure') or '-')[:40]
            surg = str(c.get('surgeon') or '')[:30]
            rows.append(
                f'<tr><td style="{_TD}{bg}">{q}</td>'
                f'<td style="{_TD}{bg}">{proc}<br>'
                f'<span style="color:#64748b;font-size:12px;">{surg}</span></td>'
                f'<td style="{_TD}{bg}">{_dur_txt(_p50(c))}</td>'
                f'<td style="{_TD}{bg}">{note}</td></tr>')
    rows.append('</table>')
    return ''.join(rows)


def page_scheduler():
    from main_or_pages import _enabled_room_options
    from room_config import room_label
    from tracking_board import _turnover_map

    st.caption("🗓️ เรียงลำดับเคสวันนี้ให้มีเคสค้างส่งเวรน้อยที่สุด — "
               "คิวเดิม (ororder) ล็อก 🔒 ไม่ขยับ · หน้านี้เป็นคำแนะนำ "
               "ไม่เขียนอะไรกลับเข้าบอร์ด")

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

    st.markdown(f"วันนี้มีเคสรอจัดคิว **{len(schedulable)} เคส** "
                f"ใน {len(cases_by_room)} ห้อง "
                f"(มีคิวเดิมแล้ว 🔒 {n_locked} เคส — AI จะจัดให้ {n_free} เคส)")
    if in_flow:
        st.caption(f"ℹ️ อีก {in_flow} เคสเข้ากระบวนการแล้ว (รอผ่า/กำลังผ่า/เสร็จ) — ไม่ถูกจัด")
    if no_room:
        st.warning(f"⚠️ {len(no_room)} เคสไม่มีห้อง/ห้องถูกปิด — จัดไม่ได้ "
                   f"(ไปกำหนดห้องผ่าน ✏️ บนบอร์ดก่อน): "
                   + ' · '.join(str(c.get('procedure', ''))[:20] for c in no_room[:5]))

    if st.button("🪄 จัดคิว", type="primary", use_container_width=True,
                 key='schd_run'):
        st.session_state['schd_ran'] = True
    if not st.session_state.get('schd_ran'):
        st.caption("กดปุ่มเพื่อให้ AI เรียงคิว — กดซ้ำได้ ไม่กระทบบอร์ด")
        return

    tov_map = _turnover_map()
    results, best = build_primary(cases_by_room, tov_map, _RISK_DEFAULT)
    best_plan = results[best]
    locked_ids = {str(c.get('id'))
                  for rcs in cases_by_room.values()
                  for c in split_locked(rcs)[0]}

    # ── ① ตารางใช้จริง — ห้องเดิม · คิวเดิมล็อก ──
    st.markdown(_sect_html('①', 'ตารางใช้จริง', 'ห้องเดิม · คิวเดิมล็อก 🔒',
                           best_plan['metrics']['handover']),
                unsafe_allow_html=True)
    st.markdown(_queue_table_html(best_plan['rooms'], room_label, locked_ids),
                unsafe_allow_html=True)
    if best_plan['metrics']['handover']:
        st.caption("แถวแดง = เผื่อเวลาแล้วยังคาดออกห้องหลัง 15:30 "
                   "แม้จัดแบบดีที่สุด — การพิจารณาเลื่อนเป็นการตัดสินใจของหัวหน้าเวร")

    # ── ② แบบ AI จัดอิสระ — ย้ายคิว/ย้ายห้องได้ (ดูอย่างเดียว) ──
    ideal = build_ideal(cases_by_room, enabled_rooms, tov_map, _RISK_DEFAULT)
    st.markdown(_sect_html('②', 'แบบ AI จัดอิสระ',
                           'ย้ายคิว/ย้ายห้องได้ · ไว้ดูเปรียบเทียบ',
                           ideal['metrics']['handover']),
                unsafe_allow_html=True)
    st.markdown('<div style="background:#f3e5f5;border:1px solid #ce93d8;'
                'color:#6a1b9a;border-radius:8px;padding:8px 13px;'
                'font-size:12.5px;margin:4px 0;">🔭 ดูอย่างเดียว — '
                'หน้างานจริงไม่ย้ายเคสข้ามห้อง (ทีมห้องอื่นไม่พร้อมรับเคสต่างสาขา) '
                'ตารางนี้ตอบคำถามเดียว: ถ้าย้ายได้อิสระ จะลดเคสรับเวรได้ไหม</div>',
                unsafe_allow_html=True)

    # ป้ายหมายเหตุตาราง ②: ย้ายห้อง / สลับคิวขึ้นก่อน (เทียบกับตาราง ①)
    prim_pos = {str(e['case'].get('id')): (rm, i)
                for rm, es in best_plan['rooms'].items()
                for i, e in enumerate(es)}
    notes = {}
    for rm, es in ideal['rooms'].items():
        for i, e in enumerate(es):
            cid = str(e['case'].get('id'))
            if cid in locked_ids or cid not in prim_pos:
                continue
            rm0, i0 = prim_pos[cid]
            if rm != rm0:
                notes[cid] = f'ย้ายจาก {room_label(rm0)}'
            elif i < i0:
                notes[cid] = 'สลับคิวขึ้นก่อน'
    st.markdown(_queue_table_html(ideal['rooms'], room_label, locked_ids,
                                  notes=notes, default_note=''),
                unsafe_allow_html=True)

    # ── 💡 วิธีคิด (expander เดียวที่เหลือ) ──
    with st.expander("💡 AI คิดยังไง", expanded=False):
        st.markdown(
            f"1. **เวลาทำนายการใช้ห้อง (room duration) ต่อเคส** = ค่าทำนายบนบอร์ด (AI หรือค่าที่พยาบาลแก้ไข ✏️ )\n"
            f"2. **คิวเดิม (or order) {n_locked} เคส 🔒** อยู่ลำดับเดิมตามที่ set ผ่าตัด\n"
            f"3. **เคสที่ไม่ระบุคิวตอน set ผ่าตัด {n_free} เคส** AI ลองเรียงหลายแบบภายในห้องเดิม "
            f"แล้วเลือกแบบที่เคสรับเวรน้อยที่สุด (รอบนี้: แบบ {best})\n"
            f"4. **'เสี่ยงรับเวร'** = "
            f"เคสที่จำหน่ายหลัง 15:30 — คิดจากเวลาสะสมของคิวก่อนหน้า + turnover รายห้อง\n"
            f"5. **ตาราง ②** ให้ AI ย้ายคิว/ย้ายห้องได้อิสระ เพื่อหาวิธีเพิ่ม room utility"
        )
