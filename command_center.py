"""
command_center.py — พยากรณ์เวลาเสร็จรายห้อง + ไทม์ไลน์ (หน้าบริหารวันนี้)

ใช้ข้อมูลรายห้องจาก get_room_status() (มี rm['cases'] = DataFrame ทุกเคสของห้อง
พร้อม ai_predicted_min / in_or_at / op_end_at / status)

room_forecast(rm)        → dict สถานะ + เวลาเสร็จคาดการณ์ (ใช้ร่วมทั้ง 2 section)
forecast_caption_html()  → บรรทัด "คาดเสร็จ" สำหรับการ์ด (Section 1)
render_room_timeline()   → ไทม์ไลน์รายห้อง (Section 2)
ทั้งสอง section เรียก room_forecast ตัวเดียวกัน → ตัวเลขตรงกันเสมอ (เชื่อมกัน)

🔄 turnover: ใช้ median รายห้องจากข้อมูลจริง (main_or_db.get_room_turnover_map)
   แทนค่าคงที่ 20 นาที — ห้องข้อมูลน้อยถอยไปค่ากลางรวม · ไม่มีข้อมูลถึง fallback 20
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ค่าสำรองเมื่อ "ไม่มีข้อมูล turnover จริง" — ปกติจะใช้ median รายห้องจากข้อมูล (ดู _turnover_map)
TURNOVER_FALLBACK = 20
TURNOVER_MIN = TURNOVER_FALLBACK   # backward-compat alias


@st.cache_data(ttl=3600, show_spinner=False)
def _turnover_map():
    """median turnover ต่อห้องจากข้อมูลจริง (cache 1 ชม.) — {room_no: นาที, '_global': นาที}
    DB ใช้ไม่ได้/ไม่มีข้อมูล → {} แล้ว caller ถอยไปใช้ TURNOVER_FALLBACK"""
    try:
        from main_or_db import get_room_turnover_map
        return get_room_turnover_map() or {}
    except Exception:
        return {}


def _turnover_for(rm, tmap=None) -> float:
    """turnover (นาที) ของห้องนี้: median ห้องตัวเอง → ค่ากลางรวม → fallback 20"""
    tmap = _turnover_map() if tmap is None else tmap
    if not tmap:
        return TURNOVER_FALLBACK
    try:
        _rno = int(float(rm.get('room_no')))
    except (TypeError, ValueError):
        _rno = None
    v = tmap.get(_rno)
    if v is None:
        v = tmap.get('_global')
    return float(v) if v is not None else TURNOVER_FALLBACK


def _parse_dt(s):
    if isinstance(s, str) and s:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass
    return None


def _mins(dt):
    return dt.hour * 60 + dt.minute


def room_forecast(rm, now=None, turnover_map=None):
    """คำนวณพยากรณ์เวลาเสร็จของห้องเดียว.
    turnover_map: {room_no: median นาที, '_global': ...} — ถ้า None ดึง cache เอง"""
    now = now or datetime.now()
    turn_min = _turnover_for(rm, turnover_map)   # median รายห้องจากข้อมูลจริง (แทน 20 คงที่)
    cases = rm.get('cases')
    active = rm.get('active_case')
    waiting_n = int(rm.get('waiting', 0) or 0)
    done_n = int(rm.get('done', 0) or 0)
    has_cases = int(rm.get('total', 0) or 0) > 0

    waiting_min = 0
    earliest = None
    latest_end = None
    if cases is not None and len(cases):
        for _, c in cases.iterrows():
            sdt = _parse_dt(c.get('in_or_at'))
            if sdt and (earliest is None or sdt < earliest):
                earliest = sdt
            edt = _parse_dt(c.get('op_end_at'))
            if edt and (latest_end is None or edt > latest_end):
                latest_end = edt
        try:
            wdf = cases[cases['status'].isin(['scheduled', 'arrived'])]
        except Exception:
            wdf = cases.iloc[0:0]
        for _, c in wdf.iterrows():
            p = c.get('ai_predicted_min')
            try:
                waiting_min += int(p) if (p is not None and not pd.isna(p)) else 60
            except (ValueError, TypeError):
                waiting_min += 60

    elapsed = 0
    ai_active = 0
    active_rem = 0
    over_min = 0
    if active:
        try:
            ai_active = int(active.get('ai_predicted_min') or 0)
        except (ValueError, TypeError):
            ai_active = 0
        sdt = _parse_dt(active.get('in_or_at'))
        if sdt:
            elapsed = max(int((now - sdt).total_seconds() / 60), 0)
        if ai_active:
            active_rem = max(ai_active - elapsed, 0)
            over_min = max(elapsed - ai_active, 0)
        else:
            active_rem = 30

    total_remaining = active_rem + waiting_min + turn_min * waiting_n
    has_future = bool(active) or waiting_n > 0
    finish = (now + timedelta(minutes=total_remaining)) if has_future else (latest_end or now)

    if active and over_min > 0:
        status = 'เกินเวลา'
    elif active:
        status = 'กำลังผ่า'
    elif waiting_n > 0 and done_n > 0:
        status = 'เตรียมห้อง'
    elif waiting_n > 0:
        status = 'รอเข้าห้อง'
    elif done_n > 0:
        status = 'เสร็จแล้ว'
    else:
        status = 'ว่าง'

    return {
        'status': status, 'elapsed': elapsed, 'ai_active': ai_active,
        'active_rem': active_rem, 'over_min': over_min, 'waiting_n': waiting_n,
        'done_n': done_n, 'total_remaining': total_remaining, 'finish': finish,
        'earliest': earliest, 'latest_end': latest_end,
        'has_future': has_future, 'has_cases': has_cases,
        'turnover_min': round(turn_min, 1),   # turnover รายห้องที่ใช้ (จากข้อมูลจริง)
    }


_STATUS_C = {
    'กำลังผ่า': ('#22a565', '#1b7f4b'),
    'เกินเวลา': ('#e24b4a', '#c0392b'),
    'รอเข้าห้อง': ('#e3920b', '#9a6700'),
    'เตรียมห้อง': ('#e3920b', '#9a6700'),
    'เสร็จแล้ว': ('#22a565', '#1b7f4b'),
    'ว่าง': ('#94a3b8', '#64748b'),
}


def forecast_caption_html(fc):
    """บรรทัด 'คาดเสร็จ' สำหรับใส่ท้ายการ์ดห้อง (Section 1)."""
    if not fc['has_future']:
        return ''
    fin = fc['finish'].strftime('%H:%M') if fc['finish'] else '—'
    over = fc['status'] == 'เกินเวลา'
    col = '#c0392b' if over else '#1565c0'
    bg = '#fbe9e8' if over else '#e3f0fb'
    return (f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'background:{bg};color:{col};border-radius:8px;padding:5px 9px;'
            f'font-size:11px;margin-top:8px;">'
            f'<span>เหลือ {fc["waiting_n"]} เคส</span>'
            f'<span>🤖 คาดเสร็จ <b>{fin}</b></span></div>')


def render_room_timeline(rooms, now=None):
    """Section 2 — ไทม์ไลน์ AI ทำนายเวลาเสร็จรายห้อง (ใช้ room_forecast เดียวกับการ์ด)."""
    now = now or datetime.now()
    _tmap = _turnover_map()   # ดึง median รายห้องครั้งเดียว ส่งต่อทุกห้อง (เร็ว)
    fcs = [(rm, room_forecast(rm, now, _tmap)) for rm in rooms]
    fcs = [(rm, fc) for rm, fc in fcs if fc['has_cases']]
    if not fcs:
        st.caption('ยังไม่มีเคสวันนี้ — ไทม์ไลน์จะขึ้นเมื่อมีเคสเข้า')
        return

    now_min = _mins(now)
    starts = [_mins(fc['earliest']) for _, fc in fcs if fc['earliest']]
    finishes = [_mins(fc['finish']) for _, fc in fcs if fc['finish']]
    day_start = (min([8 * 60] + starts) // 30) * 30
    day_end = max([18 * 60, now_min] + finishes)
    day_end = -(-day_end // 30) * 30
    span = max(day_end - day_start, 60)

    def pos(m):
        return max(0.0, min(100.0, (m - day_start) / span * 100))

    ticks = list(range(((day_start + 59) // 60) * 60, day_end + 1, 120))
    axis = ''.join(
        f'<span style="position:absolute;left:{pos(t):.1f}%;font-size:11px;'
        f'color:#94a3b8;transform:translateX(-50%);">{t // 60:02d}:00</span>'
        for t in ticks)

    order = {'เกินเวลา': 0, 'กำลังผ่า': 1, 'เตรียมห้อง': 2, 'รอเข้าห้อง': 3,
             'เสร็จแล้ว': 4, 'ว่าง': 5}
    fcs.sort(key=lambda x: order.get(x[1]['status'], 9))

    rows = ''
    for rm, fc in fcs:
        label = rm.get('room_label') or f"ห้อง {rm.get('room_no')}"
        dot, lblc = _STATUS_C.get(fc['status'], _STATUS_C['ว่าง'])
        s_min = _mins(fc['earliest']) if fc['earliest'] else now_min
        f_min = _mins(fc['finish']) if fc['finish'] else now_min
        used_l, used_r = pos(s_min), pos(min(now_min, f_min))
        used_w = max(used_r - used_l, 0)
        dash_l, dash_r = pos(min(now_min, f_min)), pos(f_min)
        dash_w = max(dash_r - dash_l, 0)
        bar = ''
        if used_w > 0.3:
            bar += (f'<div style="position:absolute;left:{used_l:.1f}%;width:{used_w:.1f}%;'
                    f'height:100%;background:{dot};border-radius:4px 0 0 4px;"></div>')
        if dash_w > 0.3 and fc['has_future']:
            bar += (f'<div style="position:absolute;left:{dash_l:.1f}%;width:{dash_w:.1f}%;'
                    f'height:100%;border:1.5px dashed {dot};border-radius:0 4px 4px 0;'
                    f'box-sizing:border-box;"></div>')
        bar += (f'<div style="position:absolute;left:{pos(now_min):.1f}%;top:-2px;'
                f'width:2px;height:24px;background:#0f172a;"></div>')
        if fc['has_future']:
            bar += (f'<div style="position:absolute;left:{pos(f_min):.1f}%;top:0;'
                    f'font-size:11px;color:{lblc};transform:translateX(2px);">◆</div>')
        fin_txt = fc['finish'].strftime('%H:%M') if (fc['has_future'] and fc['finish']) else '—'
        right = (f'เหลือ {fc["waiting_n"]} · เสร็จ <b style="color:{lblc};">{fin_txt}</b>'
                 if fc['has_future'] else 'เสร็จงานแล้ว')
        rows += (
            f'<div style="margin-bottom:11px;">'
            f'<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">'
            f'<span style="font-weight:500;color:#1565c0;">{label}</span>'
            f'<span style="color:#64748b;">{right}</span></div>'
            f'<div style="position:relative;height:20px;background:#f1f5f9;border-radius:4px;">{bar}</div>'
            f'</div>')

    legend = (
        '<div style="display:flex;flex-wrap:wrap;gap:13px;margin-top:6px;font-size:11px;color:#64748b;">'
        '<span><span style="display:inline-block;width:15px;height:8px;background:#22a565;'
        'border-radius:2px;vertical-align:middle;"></span> กำลังผ่า</span>'
        '<span><span style="display:inline-block;width:15px;height:8px;background:#e24b4a;'
        'border-radius:2px;vertical-align:middle;"></span> เกินเวลา</span>'
        '<span><span style="display:inline-block;width:15px;height:8px;border:1.5px dashed #94a3b8;'
        'border-radius:2px;vertical-align:middle;box-sizing:border-box;"></span> AI ประมาณการ</span>'
        '<span><b style="color:#0f172a;">|</b> ตอนนี้ &middot; ◆ คาดเสร็จ</span></div>')

    st.markdown(
        f'<div style="position:relative;height:16px;margin-bottom:4px;">{axis}</div>'
        f'{rows}{legend}',
        unsafe_allow_html=True,
    )
