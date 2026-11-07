"""
command_center.py — พยากรณ์เวลาเสร็จรายห้อง + ไทม์ไลน์ (หน้าบริหารวันนี้)

ใช้ข้อมูลรายห้องจาก get_room_status() (มี rm['cases'] = DataFrame ทุกเคสของห้อง
พร้อม ai_predicted_min / in_or_at / op_end_at / status)

room_forecast(rm)        → dict สถานะ + เวลาเสร็จทำนาย (ใช้ร่วมทั้ง 2 section)
forecast_caption_html()  → บรรทัด "เคสสุดท้ายของวัน" สำหรับการ์ด (Section 1)
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
    """บรรทัด 'เคสสุดท้ายของวัน' สำหรับใส่ท้ายการ์ดห้อง (Section 1)
    (เดิมใช้คำว่า 'คาดเสร็จ' — เปลี่ยน 1 ส.ค. 2026 เพราะกำกวม ผู้ใช้เข้าใจว่าเคสปัจจุบัน)"""
    if not fc['has_future']:
        return ''
    fin = fc['finish'].strftime('%H:%M') if fc['finish'] else '—'
    over = fc['status'] == 'เกินเวลา'
    col = '#c0392b' if over else '#1565c0'
    bg = '#fbe9e8' if over else '#e3f0fb'
    return (f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'background:{bg};color:{col};border-radius:8px;padding:7px 12px;'
            f'font-size:var(--fs-meta);margin-top:8px;">'
            f'<span>เหลือ {fc["waiting_n"]} เคส</span>'
            f'<span>🤖 เคสสุดท้ายของวัน <b>{fin}</b></span></div>')


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
        f'<span style="position:absolute;left:{pos(t):.1f}%;font-size:var(--fs-meta);'
        f'color:#94a3b8;transform:translateX(-50%);">{t // 60:02d}:00</span>'
        for t in ticks)

    order = {'เกินเวลา': 0, 'กำลังผ่า': 1, 'เตรียมห้อง': 2, 'รอเข้าห้อง': 3,
             'เสร็จแล้ว': 4, 'ว่าง': 5}
    fcs.sort(key=lambda x: order.get(x[1]['status'], 9))

    # 🗓️ รายเคส (28 ก.ค. 2026 — ย้าย Gantt จากหน้าจัดคิวมาที่นี่ตามคำสั่งมุคกี้):
    #    แต่ละแถวแสดง "แท่งเคส" ซ้าย→ขวาเหมือนอ่านตารางผ่าตัดจริง — เสร็จ ✓ จาง /
    #    กำลังผ่าเขียว(เกิน=แดง) ต่อด้วยเส้นประ AI ที่เหลือ / คิวถัดไปกรอบเทา
    #    ต่อหลังเวลาปัจจุบัน + turnover · ◆ เคสสุดท้ายของวัน = จุดเดียวกับการ์ดห้องเสมอ
    def _blk(l, w, sty, txt, tip):
        _t = txt if w > 6 else ''
        return (f'<div title="{tip}" style="position:absolute;left:{l:.1f}%;'
                f'width:{max(w, 0.8):.1f}%;height:32px;border-radius:4px;{sty}'
                f'font-size:var(--fs-meta);line-height:32px;padding:0 6px;overflow:hidden;'
                f'white-space:nowrap;box-sizing:border-box;">{_t}</div>')

    rows = ''
    for rm, fc in fcs:
        label = rm.get('room_label') or f"ห้อง {rm.get('room_no')}"
        dot, lblc = _STATUS_C.get(fc['status'], _STATUS_C['ว่าง'])
        bar = ''
        cases = rm.get('cases')
        df = cases if (cases is not None and len(cases)) else None
        if df is not None:
            for _, c in df.iterrows():
                stt = str(c.get('status') or '')
                proc = str(c.get('procedure_name') or '-')[:36]
                sdt = _parse_dt(c.get('in_or_at'))
                if stt == 'cancelled' or sdt is None:
                    continue
                s = _mins(sdt)
                edt = _parse_dt(c.get('op_end_at'))
                if stt in ('post_op', 'discharged') and edt is not None:
                    bar += _blk(pos(s), pos(_mins(edt)) - pos(s),
                                'background:#f8faf8;border:1px solid #cfd8d1;'
                                'color:#94a3b8;', f'✓ {proc}',
                                f'{proc} · เสร็จแล้ว')
                elif stt == 'in_or':
                    # ส่วนที่ผ่าไปแล้ว (ทึบ) + ที่ AI คาดว่าเหลือ (เส้นประ)
                    bar += _blk(pos(s), pos(now_min) - pos(s),
                                f'background:{dot};color:#fff;font-weight:600;',
                                proc, f'{proc} · กำลังผ่า')
                    _rem = fc['active_rem'] or 0
                    if _rem > 0:
                        bar += _blk(pos(now_min), pos(now_min + _rem) - pos(now_min),
                                    f'border:1.5px dashed {dot};color:{lblc};',
                                    '', f'{proc} · AI คาดเหลือ ~{int(_rem)} น.')
        # คิวถัดไป: ต่อจาก ตอนนี้ + เวลาที่เหลือของเคสในห้อง + turnover
        if df is not None:
            cur = now_min + (fc['active_rem'] or 0) + (fc['turnover_min']
                                                       if fc['active_rem'] else 0)
            try:
                wdf = df[df['status'].isin(['scheduled', 'arrived'])]
            except Exception:
                wdf = df.iloc[0:0]
            for _, c in wdf.iterrows():
                proc = str(c.get('procedure_name') or '-')[:36]
                try:
                    ai = int(c.get('ai_predicted_min') or 60)
                except (ValueError, TypeError):
                    ai = 60
                bar += _blk(pos(cur), pos(cur + ai) - pos(cur),
                            'background:#ffffff;border:1px solid #90a4ae;'
                            'color:#334155;', proc,
                            f'{proc} · คิวถัดไป · AI ~{ai} น.')
                cur += ai + fc['turnover_min']
        bar += (f'<div style="position:absolute;left:{pos(now_min):.1f}%;top:-2px;'
                f'width:2px;height:36px;background:#0f172a;"></div>')
        f_min = _mins(fc['finish']) if fc['finish'] else now_min
        if fc['has_future']:
            bar += (f'<div style="position:absolute;left:{pos(f_min):.1f}%;top:0;'
                    f'font-size:11px;color:{lblc};transform:translateX(2px);">◆</div>')
        fin_txt = fc['finish'].strftime('%H:%M') if (fc['has_future'] and fc['finish']) else '—'
        right = (f'เหลือ {fc["waiting_n"]} · เสร็จ <b style="color:{lblc};">{fin_txt}</b>'
                 if fc['has_future'] else 'เสร็จงานแล้ว')
        rows += (
            f'<div style="margin-bottom:13px;">'
            f'<div style="display:flex;justify-content:space-between;font-size:var(--fs-meta);margin-bottom:4px;">'
            f'<span style="font-size:var(--fs-card);font-weight:600;color:#1565c0;">{label}</span>'
            f'<span style="color:#64748b;">{right}</span></div>'
            f'<div style="position:relative;height:32px;background:#f1f5f9;border-radius:4px;">{bar}</div>'
            f'</div>')

    legend = (
        '<div style="display:flex;flex-wrap:wrap;gap:16px;margin-top:8px;font-size:var(--fs-meta);color:#64748b;">'
        '<span><span style="display:inline-block;width:15px;height:8px;background:#f8faf8;'
        'border:1px solid #cfd8d1;border-radius:2px;vertical-align:middle;'
        'box-sizing:border-box;"></span> ✓ เสร็จแล้ว</span>'
        '<span><span style="display:inline-block;width:15px;height:8px;background:#22a565;'
        'border-radius:2px;vertical-align:middle;"></span> กำลังผ่า</span>'
        '<span><span style="display:inline-block;width:15px;height:8px;background:#e24b4a;'
        'border-radius:2px;vertical-align:middle;"></span> เกินเวลา</span>'
        '<span><span style="display:inline-block;width:15px;height:8px;border:1.5px dashed #94a3b8;'
        'border-radius:2px;vertical-align:middle;box-sizing:border-box;"></span> AI ประมาณการ</span>'
        '<span><span style="display:inline-block;width:15px;height:8px;background:#fff;'
        'border:1px solid #90a4ae;border-radius:2px;vertical-align:middle;'
        'box-sizing:border-box;"></span> คิวถัดไป</span>'
        '<span><b style="color:#0f172a;">|</b> ตอนนี้ &middot; ◆ เคสสุดท้ายของวัน</span></div>')

    st.markdown(
        f'<div style="position:relative;height:24px;margin-bottom:6px;">{axis}</div>'
        f'{rows}{legend}',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# 🗓️ ไทม์ไลน์รุ่น 2 (มุกกี้สั่ง 7 พ.ย. 2026 : ทำตาม mockup "มุมมองไทม์ไลน์ห้องผ่าตัด"
#    เปิดเฉพาะแอป DEMO ก่อน · ระบบจริงยังใช้ render_room_timeline เดิม)
#    ที่มา: ผู้ทรงคุณวุฒิ (อ.ณัฐวิทย์) ติว่าจอรก + ศึกษางานมืออาชีพ (LiveData/Apella)
#    ต่างจากรุ่นเดิม: ป้ายห้องคอลัมน์ซ้าย (แถวเตี้ยลง เห็นครบ 9 ห้อง) · เรียงตามห้อง
#    OR1-OR9 เหมือนกระดานไวท์บอร์ด · เส้นตอนนี้ลากยาวทุกแถว · แรเงาหลัง 15:30 ·
#    แถบกำลังผ่า = สีเข้มส่วนที่ผ่านไป/อ่อนส่วนที่เหลือ · เกินเวลาเป็นแดงเฉพาะส่วนที่เกิน ·
#    แจ้งเตือนสรุปบนหัว (เกินเวลาที่ทำนาย / คาดเลิกหลัง 15:30)
#    ตัวเลขทุกตัวยังมาจาก room_forecast ชุดเดียวกับการ์ดห้อง → ตรงกันเสมอ
# ════════════════════════════════════════════════════════════════════
_CUT_1530 = 15 * 60 + 30


def _hhmm(m):
    m = int(round(m))
    return f'{(m // 60) % 24:02d}:{m % 60:02d}'


def render_room_timeline_v2(rooms, now=None):
    """ไทม์ไลน์ห้องผ่าตัดรุ่น 2 (DEMO) : แถวละ 1 ห้อง แกนเวลาแนวนอน."""
    import html as _html
    now = now or datetime.now()
    _tmap = _turnover_map()
    try:
        from room_config import ROOM_INFO as _RI
    except Exception:
        _RI = {}
    rows_in = [rm for rm in rooms if not rm.get('closed')]
    fcs = [(rm, room_forecast(rm, now, _tmap)) for rm in rows_in]
    if not any(fc['has_cases'] for _, fc in fcs):
        st.caption('ยังไม่มีเคสวันนี้ : ไทม์ไลน์จะขึ้นเมื่อมีเคสเข้า')
        return

    now_min = _mins(now)
    starts = [_mins(fc['earliest']) for _, fc in fcs if fc['earliest']]
    finishes = [_mins(fc['finish']) for _, fc in fcs if fc['finish'] and fc['has_future']]
    day_start = (min([8 * 60] + starts) // 60) * 60
    day_end = max([18 * 60 + 30, now_min + 15] + finishes)
    day_end = -(-day_end // 30) * 30
    span = max(day_end - day_start, 60)

    def pos(m):
        return max(0.0, min(100.0, (m - day_start) / span * 100))

    hour_w = 60 / span * 100
    LBL = 150   # ความกว้างคอลัมน์ป้ายห้อง (px)

    def _blk(a, b, sty, label, sub, tip):
        w = pos(b) - pos(a)
        _l = (f'<span style="display:block;font-weight:600;">{label}</span>' if w > 6 else '')
        _s = (f'<span style="display:block;font-size:12px;">{sub}</span>' if w > 9 else '')
        return (f'<div title="{tip}" style="position:absolute;top:9px;bottom:9px;'
                f'left:{pos(a):.2f}%;width:{max(w, 0.6):.2f}%;box-sizing:border-box;'
                f'border-radius:6px;padding:3px 7px;overflow:hidden;white-space:nowrap;'
                f'font-size:13px;line-height:1.3;{sty}">{_l}{_s}</div>')

    alerts = []
    rows = ''
    for rm, fc in fcs:
        try:
            _rno = int(float(rm.get('room_no')))
        except (TypeError, ValueError):
            _rno = None
        if _rno in _RI:
            code, spec = _RI[_rno]
        else:
            code, spec = (rm.get('room_label') or f"ห้อง {rm.get('room_no')}"), ''
        bar = ''
        cases = rm.get('cases')
        df = cases if (cases is not None and len(cases)) else None
        if df is not None:
            for _, c in df.iterrows():
                stt = str(c.get('status') or '')
                proc = _html.escape(str(c.get('procedure_name') or '-')[:36])
                sdt = _parse_dt(c.get('in_or_at'))
                if stt == 'cancelled' or sdt is None:
                    continue
                s = _mins(sdt)
                edt = _parse_dt(c.get('op_end_at'))
                if stt in ('post_op', 'discharged') and edt is not None:
                    e = _mins(edt)
                    bar += _blk(s, e, 'background:#E9EDF2;border:1px solid #CBD5E1;color:#475569;',
                                proc, f'จริง {e - s} น.', f'{proc} : เสร็จแล้ว ใช้เวลา {e - s} นาที')
                elif stt == 'in_or':
                    try:
                        ai = int(c.get('ai_predicted_min') or 0)
                    except (ValueError, TypeError):
                        ai = 0
                    pe = s + ai if ai else now_min + (fc['active_rem'] or 30)
                    b = max(pe, now_min)
                    tot = max(b - s, 1)
                    if now_min > pe:
                        y = (pe - s) / tot * 100
                        sty = (f'background:linear-gradient(90deg,#BFE6D6 0 {y:.1f}%,'
                               f'#F2D4D4 {y:.1f}% 100%);border:2px solid #A32D2D;color:#7A1F1F;')
                        sub = f'เกิน {now_min - pe} น.'
                    else:
                        x = (now_min - s) / tot * 100
                        sty = (f'background:linear-gradient(90deg,#BFE6D6 0 {x:.1f}%,'
                               f'#E1F5EE {x:.1f}% 100%);border:2px solid #1D9E75;color:#085041;')
                        sub = f'{now_min - s} / {ai} น.' if ai else f'{now_min - s} น.'
                    bar += _blk(s, b, sty, proc, sub,
                                f'{proc} : กำลังผ่า ทำนาย {ai} นาที' if ai else f'{proc} : กำลังผ่า')
            # คิวถัดไป: ต่อจาก ตอนนี้ + เวลาที่เหลือของเคสในห้อง + turnover (สูตรเดียวกับรุ่นเดิม)
            cur = now_min + (fc['active_rem'] or 0) + (fc['turnover_min'] if fc['active_rem'] else 0)
            if fc['over_min']:
                cur = now_min + fc['turnover_min']
            try:
                wdf = df[df['status'].isin(['scheduled', 'arrived'])]
            except Exception:
                wdf = df.iloc[0:0]
            for _, c in wdf.iterrows():
                proc = _html.escape(str(c.get('procedure_name') or '-')[:36])
                try:
                    ai = int(c.get('ai_predicted_min') or 60)
                except (ValueError, TypeError):
                    ai = 60
                bar += _blk(cur, cur + ai, 'background:#FFFFFF;border:1.5px dashed #94A3B8;color:#475569;',
                            proc, f'ทำนาย {ai} น.', f'{proc} : คิวถัดไป ทำนาย {ai} นาที')
                cur += ai + fc['turnover_min']

        # ป้ายสรุปใต้ชื่อห้อง
        sum_sty = 'color:#475569;'
        if not fc['has_cases']:
            summary, sum_sty = 'ไม่มีเคสวันนี้', 'color:#64748B;'
        elif not fc['has_future']:
            summary = (f'ว่างตั้งแต่ {fc["latest_end"].strftime("%H:%M")}'
                       if fc['latest_end'] else 'เสร็จงานแล้ว')
        else:
            fin_m = _mins(fc['finish']) if fc['finish'] else now_min
            summary = f'คาดเลิก {_hhmm(fin_m)}'
            if fin_m > _CUT_1530 and now_min < _CUT_1530:
                sum_sty = 'color:#8A5A00;font-weight:700;'
                alerts.append(('amber', f'{code} คาดเลิก {_hhmm(fin_m)} หลังเวลา 15:30'))
        if fc['over_min']:
            alerts.insert(0, ('red', f'{code} เกินเวลาที่ทำนาย {fc["over_min"]} นาที'))

        rows += (
            f'<div style="display:flex;height:60px;border-bottom:1px solid #EEF2F6;">'
            f'<div style="width:{LBL}px;flex:none;padding:6px 12px;box-sizing:border-box;'
            f'display:flex;flex-direction:column;justify-content:center;">'
            f'<div style="font-size:16px;font-weight:700;color:#0F172A;">{code} '
            f'<span style="font-size:12px;font-weight:500;color:#64748B;">{_html.escape(spec)}</span></div>'
            f'<div style="font-size:13px;{sum_sty}">{summary}</div></div>'
            f'<div style="position:relative;flex:1;margin-right:16px;background-image:'
            f'repeating-linear-gradient(90deg,#EEF2F6 0 1px,transparent 1px {hour_w:.4f}%);">'
            f'{bar}</div></div>')

    # แกนเวลา (รายชั่วโมง) + ป้าย 15:30 + ป้ายเวลาปัจจุบัน
    ticks = ''
    for t in range(day_start, day_end + 1, 60):
        _tx = 'transform:translateX(-50%);' if t > day_start else ''
        ticks += (f'<span style="position:absolute;top:8px;left:{pos(t):.2f}%;{_tx}'
                  f'font-size:12px;color:#64748B;">{_hhmm(t)}</span>')
    ticks += (f'<span style="position:absolute;top:6px;left:{pos(_CUT_1530):.2f}%;'
              f'transform:translateX(-50%);padding:1px 6px;border-radius:4px;background:#FDF3DD;'
              f'color:#7A5200;font-size:11px;font-weight:600;">15:30</span>')
    ticks += (f'<span style="position:absolute;top:5px;left:{pos(now_min):.2f}%;'
              f'transform:translateX(-50%);padding:1px 7px;border-radius:4px;background:#2563EB;'
              f'color:#FFFFFF;font-size:12px;font-weight:600;">{_hhmm(now_min)}</span>')
    axis = (f'<div style="display:flex;height:32px;border-bottom:1px solid #E2E8F0;">'
            f'<div style="width:{LBL}px;flex:none;padding:8px 12px;box-sizing:border-box;'
            f'font-size:12px;color:#64748B;">ห้อง</div>'
            f'<div style="position:relative;flex:1;margin-right:16px;">{ticks}</div></div>')

    zone = (f'<div style="position:absolute;top:0;bottom:0;left:{LBL}px;right:16px;pointer-events:none;">'
            f'<div style="position:absolute;top:0;bottom:0;left:{pos(_CUT_1530):.2f}%;right:0;'
            f'background:rgba(253,243,221,0.55);"></div></div>')
    nowline = (f'<div style="position:absolute;top:0;bottom:0;left:{LBL}px;right:16px;pointer-events:none;">'
               f'<div style="position:absolute;top:0;bottom:0;left:{pos(now_min):.2f}%;width:2px;'
               f'margin-left:-1px;background:#2563EB;"></div></div>')

    _ast = {'red': 'background:#FBEAEA;color:#7A1F1F;border:1px solid #E8BDBD;',
            'amber': 'background:#FDF3DD;color:#6B4600;border:1px solid #EBD39C;'}
    alert_html = ''
    if alerts:
        alert_html = ('<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">'
                      + ''.join(f'<div style="padding:6px 12px;border-radius:8px;font-size:14px;'
                                f'font-weight:600;{_ast[k]}">{_html.escape(t)}</div>'
                                for k, t in alerts)
                      + '</div>')

    def _sw(sty):
        return (f'<span style="display:inline-block;width:20px;height:11px;border-radius:3px;'
                f'box-sizing:border-box;vertical-align:middle;margin-right:6px;{sty}"></span>')
    legend = (
        '<div style="display:flex;flex-wrap:wrap;gap:16px;padding:10px 14px;font-size:13px;'
        'color:#475569;border-top:1px solid #E2E8F0;">'
        f'<span>{_sw("background:#E9EDF2;border:1px solid #CBD5E1;")}เสร็จแล้ว (ยาวตามเวลาจริง)</span>'
        f'<span>{_sw("background:linear-gradient(90deg,#BFE6D6 0 50%,#E1F5EE 50% 100%);border:2px solid #1D9E75;")}'
        'กำลังผ่า (สีเข้ม = เวลาที่ผ่านไป)</span>'
        f'<span>{_sw("background:#F2D4D4;border:2px solid #A32D2D;")}เกินเวลาที่ทำนาย</span>'
        f'<span>{_sw("background:#FFFFFF;border:1.5px dashed #94A3B8;")}คิวถัดไป (ยาวตามเวลาที่ทำนาย)</span>'
        f'<span>{_sw("width:2px;background:#2563EB;border-radius:0;")}เวลาปัจจุบัน</span>'
        f'<span>{_sw("background:rgba(253,243,221,0.9);")}หลังเวลา 15:30</span></div>')

    st.markdown(
        f'{alert_html}'
        f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;overflow-x:auto;">'
        f'<div style="min-width:880px;">{axis}'
        f'<div style="position:relative;">{zone}{rows}{nowline}</div>'
        f'{legend}</div></div>',
        unsafe_allow_html=True,
    )
