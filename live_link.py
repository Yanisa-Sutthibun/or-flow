"""
live_link.py — ตัวเชื่อมข้อมูลสด: หน้าตารางผ่าตัด (session) → หน้าบริหารจัดการ "วันนี้"

แปลง st.session_state.patient_cases ให้อยู่ในโครงเดียวกับ
get_room_status() / get_kpi() / get_workload() / get_delay_alerts()
เพื่อให้ การ์ดห้อง + ไทม์ไลน์ AI + KPI + ภาระงาน + แจ้งเตือน แสดงชุดเดียวกับกระดาน
(เวลาคาดการณ์ใช้ effective_min — ค่าที่คนแก้ชนะ AI — เชื่อม override ไปด้วย)
"""
import pandas as pd
from datetime import datetime

_SMAP = {'not_arrived': 'scheduled', 'holding_pre': 'arrived', 'in_or': 'in_or',
         'holding_post': 'post_op', 'recovery': 'post_op', 'discharged': 'discharged'}

_COLS = ['case_id', 'name', 'hn', 'diagnosis', 'procedure_name', 'surgeon_name',
         'status', 'in_or_at', 'op_end_at', 'ai_predicted_min', 'actual_duration_min']

_DONE_RAW = ('holding_post', 'recovery', 'discharged')


def _rid(c):
    try:
        r = int(float(c.get('room')))
    except (TypeError, ValueError):
        return None
    return r if r and r != 1 else None


def _ts(v):
    return v.strftime('%Y-%m-%d %H:%M:%S') if (v is not None and hasattr(v, 'hour')) else None


def _eff(c, default=None):
    eff = c.get('effective_min') or c.get('ai_predicted_min') or c.get('predicted_min')
    try:
        return int(eff) if eff else default
    except (ValueError, TypeError):
        return default


def _mask_nm(v):
    """mask ชื่อผู้ป่วยก่อนส่งให้หน้าบริหาร (มาตรา 3.6.4) — fail-safe คืน '-'"""
    try:
        from main_or_db import mask_patient_name
        return mask_patient_name(v or '-')
    except Exception:
        return '-'


def _rec(c):
    return {
        'case_id': c.get('id'), 'name': c.get('name'), 'hn': c.get('hn'),
        'diagnosis': c.get('diagnosis'), 'procedure_name': c.get('procedure'),
        'surgeon_name': c.get('surgeon'),
        'status': _SMAP.get(c.get('status'), 'scheduled'),
        'in_or_at': _ts(c.get('time_entered_or')),
        'op_end_at': _ts(c.get('time_exited_or')),
        'ai_predicted_min': _eff(c),
        'actual_duration_min': c.get('actual_duration_min'),
    }


def rooms_from_session(cases, now=None):
    """โครงเดียวกับ get_room_status() แต่ใช้เคสสดจากกระดาน (เชื่อมกัน realtime)."""
    now = now or datetime.now()
    try:
        from room_config import get_active_rooms, room_label
        room_ids = list(get_active_rooms(now.strftime('%Y-%m-%d')))
    except Exception:
        room_ids = []

        def room_label(r):
            return f'ห้อง {r}'

    by_room = {}
    for c in cases:
        r = _rid(c)
        if r is not None:
            by_room.setdefault(r, []).append(_rec(c))
    for r in by_room:
        if r not in room_ids:
            room_ids.append(r)

    out = []
    for r in sorted(room_ids):
        recs = by_room.get(r, [])
        df = pd.DataFrame(recs, columns=_COLS)
        active = next((x for x in recs if x['status'] == 'in_or'), None)
        out.append({
            'room_no': r,
            'room_label': room_label(r),
            'total': len(recs),
            'done': sum(1 for x in recs if x['status'] in ('post_op', 'discharged')),
            'waiting': sum(1 for x in recs if x['status'] in ('scheduled', 'arrived')),
            'active_case': dict(active) if active else None,
            'cases': df,
        })
    return out


def kpi_from_session(cases):
    """โครงเดียวกับ get_kpi() แต่คิดจากเคสสดบนกระดาน."""
    recs = [_rec(c) for c in cases]
    done = [x for x in recs if x['status'] in ('post_op', 'discharged')]
    # 📐 M-08: utilization = เวลาที่ตกในช่วง 8:00–16:00 (clip) ÷ (ห้อง×480) — นิยามเดียวกับทั้งระบบ
    from main_or_db import _inhours_min
    total_op_min = 0
    for c in cases:
        if c.get('status') in _DONE_RAW:
            te, tx = c.get('time_entered_or'), c.get('time_exited_or')
            if te is not None and tx is not None:
                total_op_min += int(round(_inhours_min(te, tx)))

    done_rooms = set()
    for c in cases:
        if c.get('status') in _DONE_RAW:
            r = _rid(c)
            if r:
                done_rooms.add(r)
    active_rooms = len(done_rooms) or 1
    available_min = 480 * active_rooms  # 8:00–16:00 (8 ชม.)
    utilization = round(min(total_op_min / available_min * 100, 100.0), 1) if available_min else 0.0

    # turnover: ช่องว่างระหว่างเคสที่จบแล้วในห้องเดียวกัน (0 < gap < 180 นาที)
    rb = {}
    for c in cases:
        if (c.get('status') in _DONE_RAW
                and c.get('time_entered_or') is not None
                and c.get('time_exited_or') is not None
                and hasattr(c.get('time_entered_or'), 'hour')
                and hasattr(c.get('time_exited_or'), 'hour')):
            r = _rid(c)
            if r:
                rb.setdefault(r, []).append((c['time_entered_or'], c['time_exited_or']))
    turnovers = []
    for r, lst in rb.items():
        lst.sort(key=lambda t: t[0])
        for i in range(1, len(lst)):
            gap = (lst[i][0] - lst[i - 1][1]).total_seconds() / 60
            if 1 <= gap <= 90:  # 📐 M-08: ช่วง turnover ที่นับ = 1–90 นาที (นิยามเดียวทั้งระบบ)
                turnovers.append(gap)

    return {
        'total': len(recs),
        'done': len(done),
        'in_or': sum(1 for x in recs if x['status'] == 'in_or'),
        'waiting': sum(1 for x in recs if x['status'] in ('scheduled', 'arrived')),
        'cancelled': 0,
        'total_op_min': total_op_min,
        'utilization': utilization,
        'avg_turnover': round(sum(turnovers) / len(turnovers), 1) if turnovers else 0.0,
        'n_turnovers': len(turnovers),
        'active_rooms': active_rooms,
    }


def workload_from_session(cases):
    """โครงเดียวกับ get_workload() แต่คิดจากเคสสดบนกระดาน.
    OPD/IPD ดูจาก ward (reqward ในไฟล์ HIS): ว่าง/มีคำว่า OPD = OPD ·
    มีชื่อ ward = IPD (SET = เคสจากไฟล์ตาราง · Walk-in = เพิ่มด้วยมือ)"""
    surg = {}
    for c in cases:
        s = (c.get('surgeon') or '').strip()
        if not s:
            continue
        d = surg.setdefault(s, [0, 0])
        d[0] += 1
        if c.get('status') in _DONE_RAW:
            d[1] += 1
    top = sorted(surg.items(), key=lambda kv: -kv[1][0])[:8]
    top_surgeons = pd.DataFrame(
        [{'surgeon_name': k, 'n': v[0], 'done': v[1]} for k, v in top],
        columns=['surgeon_name', 'n', 'done'])

    div = {}
    for c in cases:
        k = str(c.get('division') or '').strip() or '-'
        div[k] = div.get(k, 0) + 1
    div_stats = pd.DataFrame(
        sorted([{'division_code': k, 'n': n} for k, n in div.items()],
               key=lambda r: -r['n']),
        columns=['division_code', 'n'])

    def _after(c):
        if c.get('is_after_note'):
            return True
        h = c.get('sched_hour')
        m = c.get('sched_min') or 0
        return (h is not None and not c.get('is_tf')
                and (h * 60 + m) >= 15 * 60 + 30)

    n_opd = n_ipd = 0
    for c in cases:
        w = str(c.get('ward') or '').strip()
        if not w or 'opd' in w.lower():
            n_opd += 1
        else:
            n_ipd += 1

    return {
        'top_surgeons': top_surgeons,
        'div_stats': div_stats,
        'n_set': sum(1 for c in cases
                     if str(c.get('id') or '').startswith('CSV_') or c.get('_demo')),
        'n_walkin': sum(1 for c in cases
                        if str(c.get('id') or '').startswith('MANUAL_')),
        'n_opd': n_opd,
        'n_ipd': n_ipd,
        'n_after': sum(1 for c in cases if _after(c)),
    }


def alerts_from_session(cases, now=None):
    """โครงเดียวกับ get_delay_alerts() แต่คิดจากเคสสดบนกระดาน."""
    now = now or datetime.now()
    alerts = []
    for c in cases:
        s = c.get('status')
        if (s == 'in_or' and c.get('time_entered_or') is not None
                and hasattr(c.get('time_entered_or'), 'hour')):
            elapsed = (now - c['time_entered_or']).total_seconds() / 60
            pred = _eff(c, 60) or 60
            if elapsed > pred * 1.3:
                alerts.append({
                    'type': 'overrun',
                    'severity': 'high' if elapsed > pred * 1.5 else 'medium',
                    'room_no': _rid(c), 'case_id': c.get('id'),
                    # 🔒 mask ที่ต้นทาง — แผงแจ้งเตือนผู้บริหารห้ามเห็นชื่อเต็ม (มาตรา 3.6.4)
                    'name': _mask_nm(c.get('name')), 'procedure': c.get('procedure'),
                    'message': (f"เกินเวลาทำนาย — ผ่านมา {int(elapsed)} นาที "
                                f"(ทำนาย {pred} นาที)"),
                })
        elif (s == 'holding_pre' and c.get('time_arrived_holding') is not None
                and hasattr(c.get('time_arrived_holding'), 'hour')):
            wait = (now - c['time_arrived_holding']).total_seconds() / 60
            if wait > 60:
                alerts.append({
                    'type': 'long_wait',
                    'severity': 'high' if wait > 120 else 'medium',
                    'room_no': _rid(c), 'case_id': c.get('id'),
                    'name': _mask_nm(c.get('name')), 'procedure': c.get('procedure'),
                    'message': f"รอเข้าห้องนาน {int(wait)} นาที",
                })
    return sorted(alerts, key=lambda a: {'high': 0, 'medium': 1, 'info': 2}[a['severity']])
