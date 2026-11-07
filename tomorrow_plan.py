# -*- coding: utf-8 -*-
"""
tomorrow_plan.py : 🗓️ จัดคิวพรุ่งนี้ (มุกกี้สั่ง 7 พ.ย. 2026 · ทำตาม mockup แบบ minimal)
════════════════════════════════════════════════════════════════════════════
เลียนแบบหน้างานจริง: ช่วงบ่าย (ราว 14:30) หัวหน้าเวรได้ตารางผ่าตัดของวันถัดไป
แล้วจัดเวรพยาบาลท้ายใบตาราง (ห้องละ 3-4 คน · HN · ทั่วไป · รับ-ส่ง · OT · เวรเสริม
· ลาพักผ่อน · ลาป่วย · ไปอบรม)

ที่เก็บ: app_settings คีย์ day_plan_YYYY-MM-DD (JSON ก้อนเดียวต่อวัน)
  { date, uploaded_at, cases:[...], staff:{slot_id: ชื่อ}, absences:{vac,sick,train},
    promoted: bool }
  · ชื่อ/HN ผู้ป่วย mask ก่อนเขียนเสมอ (กติกาเดียวกับ _save_board_snapshot)
  · ชื่อพยาบาล mask ด้วย _mask_nurse_name (ชื่อต้น + อักษรแรกนามสกุล) ก่อนเขียน
  · ข้อมูลจัดเวรไม่เข้าตารางวิจัยใด ๆ · ลบแผนที่เก่ากว่า 7 วันทุกครั้งที่บันทึก
เมื่อถึงวันนั้น บอร์ดว่างเครื่องแรกที่เปิด → promote_plan_if_needed() ย้ายเคสเข้าบอร์ด
"""
from __future__ import annotations

import json
import html as _html
from datetime import datetime, timedelta, date as _date

import streamlit as st

TURNOVER_DEFAULT = 20          # นาที (ใช้ median รายห้องจาก command_center ถ้ามี)
DAY_START_MIN = 8 * 60 + 30    # เคสแรกเริ่ม 08:30 ถ้าไฟล์ไม่มีเวลานัด
CUT_1530 = 15 * 60 + 30
ROOM_SLOTS = 4                 # ห้องละ 3-4 คน (คนที่ 4 ไม่บังคับ)
POSTS = [('p-hn', 'HN'), ('p-gen', 'ทั่วไป'), ('p-rs', 'รับ-ส่ง'),
         ('p-ot', 'OT'), ('p-extra', 'เวรเสริม')]
ABSENCES = [('vac', 'ลาพักผ่อน'), ('sick', 'ลาป่วย'), ('train', 'ไปอบรม')]
_TH_DAY = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
_TH_MON = ['', 'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
           'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']


# ─────────────────────────── เวลา / วันที่ ───────────────────────────
def _now():
    from main_or_pages import _now as _pn
    return _pn()


def _th_date(d: _date) -> str:
    return f"{_TH_DAY[d.weekday()]} {d.day} {_TH_MON[d.month]} {d.year + 543}"


def _next_workday(d: _date) -> _date:
    n = d + timedelta(days=1)
    while n.weekday() >= 5:      # ข้ามเสาร์-อาทิตย์
        n += timedelta(days=1)
    return n


def _hhmm(m) -> str:
    m = int(round(m))
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


# ─────────────────────────── ที่เก็บแผน ───────────────────────────
def _key(d: str) -> str:
    return f"day_plan_{d}"


def load_day_plan(d: str) -> dict | None:
    """อ่านแผนของวันที่ d (YYYY-MM-DD) · None ถ้าไม่มี/อ่านไม่ได้"""
    try:
        from main_or_db import _get_app_setting
        s = _get_app_setting(_key(d), '')
        return json.loads(s) if s else None
    except Exception as e:
        print(f"[day_plan] อ่านแผน {d} ไม่สำเร็จ: {e}")
        return None


def _mask_cases(cases):
    """mask ผู้ป่วยก่อนขึ้นคลาวด์ (กติกาเดียวกับ _save_board_snapshot)"""
    from main_or_pages import _ser
    from main_or_db import mask_patient_name, mask_hn
    out = []
    for c in cases:
        d = {k: _ser(v) for k, v in c.items()}
        if d.get('name'):
            d['name'] = mask_patient_name(d['name'])
        if d.get('hn'):
            d['hn'] = mask_hn(d['hn'])
        d.pop('procnote', None)          # free text จาก HIS ไม่ขึ้นคลาวด์
        out.append(d)
    return out


def _mask_staff(names: dict) -> dict:
    from main_or_pages import _mask_nurse_name
    return {k: _mask_nurse_name(v) for k, v in names.items() if v}


def save_day_plan(d: str, plan: dict) -> bool:
    """บันทึกแผน (mask แล้ว) + ลบแผนเก่ากว่า 7 วัน · คืน True ถ้าสำเร็จ"""
    try:
        from main_or_db import _set_app_setting, get_conn
        from main_or_pages import _mask_nurse_name
        p = dict(plan)
        p['date'] = d
        p['staff'] = _mask_staff(p.get('staff') or {})
        p['absences'] = {k: [_mask_nurse_name(x) for x in (p.get('absences') or {}).get(k, []) if x]
                         for k, _ in ABSENCES}
        _set_app_setting(_key(d), json.dumps(p, ensure_ascii=False, default=str))
        try:
            cut = _key((_now().date() - timedelta(days=7)).isoformat())
            conn = get_conn()
            try:
                conn.execute("DELETE FROM app_settings WHERE key LIKE 'day_plan_%' AND key < ?", (cut,))
                conn.commit()
            finally:
                conn.close()
        except Exception as ce:
            print(f"[day_plan] ลบแผนเก่าไม่สำเร็จ (ข้าม): {ce}")
        return True
    except Exception as e:
        print(f"[day_plan] บันทึกแผน {d} ไม่สำเร็จ: {e}")
        return False


def promote_plan_if_needed(today: str):
    """🗓️ เปิดบอร์ดวันใหม่แล้วยังว่าง → ย้ายเคสจากแผนที่เตรียมไว้เข้าบอร์ด (ครั้งเดียวต่อวัน)
    คืน list เคส (deserialize แล้ว) หรือ None · ธง promoted กันย้ายซ้ำ
    (เช่น ผู้วิจัยล้างกระดานตั้งใจ ระบบจะไม่ดึงแผนกลับมาอีก)"""
    plan = load_day_plan(today)
    if not plan or plan.get('promoted') or not plan.get('cases'):
        return None
    from main_or_pages import _deser
    cases = [{k: _deser(v) for k, v in c.items()} for c in plan['cases']]
    for c in cases:
        c['status'] = 'not_arrived'
    plan['promoted'] = True
    try:
        from main_or_db import _set_app_setting
        _set_app_setting(_key(today), json.dumps(plan, ensure_ascii=False, default=str))
    except Exception as e:
        print(f"[day_plan] ตั้งธง promoted ไม่สำเร็จ: {e}")
    return cases


def staff_for(d: str) -> dict:
    """ชื่อพยาบาลของวัน d : {'rooms': {room_no: [ชื่อ,...]}, 'posts': {label: ชื่อ}, 'absences': {...}}"""
    plan = load_day_plan(d) or {}
    staff = plan.get('staff') or {}
    rooms = {}
    for k, v in staff.items():
        if k.startswith('r') and '-' in k:
            try:
                rno = int(k[1:].split('-')[0])
            except ValueError:
                continue
            rooms.setdefault(rno, []).append((k, v))
    rooms = {r: [v for _, v in sorted(lst)] for r, lst in rooms.items()}
    posts = {lbl: staff.get(pid, '') for pid, lbl in POSTS}
    absn = {lbl: (plan.get('absences') or {}).get(k, []) for k, lbl in ABSENCES}
    return {'rooms': rooms, 'posts': posts, 'absences': absn}


# ─────────────────────────── รายชื่อพยาบาล ───────────────────────────
def _load_roster() -> list:
    try:
        from main_or_db import _get_app_setting
        s = _get_app_setting('nurse_roster', '')
        return [x for x in (json.loads(s) if s else []) if x]
    except Exception:
        return []


def _save_roster(names) -> None:
    try:
        from main_or_db import _set_app_setting
        from main_or_pages import _mask_nurse_name
        uniq = []
        for n in names:
            n = _mask_nurse_name(str(n).strip())
            if n and n not in uniq:
                uniq.append(n)
        _set_app_setting('nurse_roster', json.dumps(uniq, ensure_ascii=False))
    except Exception as e:
        print(f"[day_plan] บันทึกรายชื่อพยาบาลไม่สำเร็จ: {e}")


def _select(label, options, value, key, hide_label=False):
    """selectbox พิมพ์ชื่อใหม่ได้ (Streamlit ≥1.45) · ถอยเป็นแบบเลือกอย่างเดียวถ้าไม่รองรับ"""
    opts = [''] + [o for o in options if o]
    if value and value not in opts:
        opts.append(value)
    idx = opts.index(value) if value in opts else 0
    kw = dict(index=idx, key=key, placeholder='เพิ่ม',
              label_visibility='collapsed' if hide_label else 'visible',
              format_func=lambda x: x if x else '-')
    try:
        return st.selectbox(label, opts, accept_new_options=True, **kw)
    except TypeError:
        return st.selectbox(label, opts, **kw)


def _multi(label, options, values, key):
    opts = [o for o in options if o]
    for v in values:
        if v not in opts:
            opts.append(v)
    try:
        return st.multiselect(label, opts, default=values, key=key,
                              accept_new_options=True, placeholder='+ เพิ่ม')
    except TypeError:
        return st.multiselect(label, opts, default=values, key=key)


# ─────────────────────────── สรุปรายห้อง ───────────────────────────
def _room_summary(cases):
    """คืน list ห้องที่มีเคส: code, spec, room_no, n, finish(นาที), ops[] · เรียงตามห้อง"""
    import room_config
    try:
        from command_center import _turnover_for, _turnover_map
        tmap = _turnover_map()
    except Exception:
        _turnover_for, tmap = None, {}
    by_room = {}
    for c in cases:
        try:
            r = int(float(c.get('room')))
        except (TypeError, ValueError):
            continue
        by_room.setdefault(r, []).append(c)
    out = []
    for r in sorted(by_room):
        lst = sorted(by_room[r], key=lambda c: (int(c.get('ororder') or 99),
                                               int(c.get('sched_hour') or 23) * 60 + int(c.get('sched_min') or 0)))
        starts = [int(c.get('sched_hour')) * 60 + int(c.get('sched_min') or 0)
                  for c in lst if c.get('sched_hour') is not None and int(c.get('sched_hour')) < 23]
        start = min(starts) if starts else DAY_START_MIN
        turn = _turnover_for({'room_no': r}, tmap) if _turnover_for else TURNOVER_DEFAULT
        mins = [int(c.get('effective_min') or c.get('ai_predicted_min') or c.get('predicted_min') or 60)
                for c in lst]
        finish = start + sum(mins) + turn * (len(mins) - 1)
        name, spec = room_config.ROOM_INFO.get(r, (f'ห้อง {r}', ''))
        out.append({'room_no': r, 'code': name, 'spec': spec, 'n': len(lst), 'finish': finish,
                    'ops': [str(c.get('procedure') or '-') for c in lst]})
    return out


# ─────────────────────────── ตารางตัวอย่าง (DEMO) ───────────────────────────
_SAMPLE_ROSTER = ['แก้ว', 'น้ำฝน', 'ปลา', 'มิ้นท์', 'ฝ้าย', 'จอย', 'แพร', 'ต้น', 'บีม', 'ออม',
                  'เมย์', 'นุ่น', 'ฟ้า', 'ขวัญ', 'ปุ้ย', 'หนิง', 'ตาล', 'แนน', 'เบียร์', 'กิ๊ฟ',
                  'โบว์', 'อ้อม', 'ปู', 'ไหม', 'ใบเตย', 'พลอย', 'ส้ม', 'แอน', 'จูน', 'ก้อย',
                  'ป่าน', 'เอิร์ธ']


# เวรตัวอย่าง (ชื่อเล่นสมมติ) : ห้องละ 3 คน ห้อง NEURO 4 คน + งานประจำจุด + ลา/อบรม
_SAMPLE_STAFF = {
    'r91-1': 'ฝ้าย', 'r91-2': 'ปุ้ย', 'r91-3': 'หนิง',
    'r92-1': 'แพร', 'r92-2': 'ตาล', 'r92-3': 'แนน',
    'r93-1': 'มิ้นท์', 'r93-2': 'เบียร์', 'r93-3': 'กิ๊ฟ',
    'r94-1': 'จอย', 'r94-2': 'โบว์', 'r94-3': 'อ้อม',
    'r95-1': 'ต้น', 'r95-2': 'ปู', 'r95-3': 'ไหม', 'r95-4': 'ใบเตย',
    'r96-1': 'ออม', 'r96-2': 'พลอย', 'r96-3': 'ส้ม',
    'r97-1': 'บีม', 'r97-2': 'แอน', 'r97-3': 'จูน',
    'p-hn': 'แก้ว', 'p-gen': 'ฟ้า', 'p-rs': 'น้ำฝน', 'p-ot': 'ปลา', 'p-extra': 'เมย์',
}
_SAMPLE_ABSENCES = {'vac': ['นุ่น'], 'sick': ['ก้อย'], 'train': ['ป่าน']}


def _is_demo_instance() -> bool:
    try:
        return str(st.secrets.get('instance_mode', '')).lower() == 'demo'
    except Exception:
        return False


def _sample_cases():
    """🎬 7 พ.ย. 2026 (มุกกี้สั่ง): ตารางตัวอย่างสำหรับแอป DEMO
    ใช้ชุดสาธิตเดียวกับบอร์ด (demo_cases_data.DEMO_POOL · ผู้ป่วยทดสอบ NN / แพทย์ A-K)
    ทำนายด้วยแบบจำลองจริงผ่าน _or_board_demo() แล้วรีเซ็ตทุกเคสเป็น "ยังไม่มา"
    ทุกเคสติดธง _demo → ไม่ถูกเขียนลงฐานข้อมูลวิจัย"""
    from main_or_pages import _or_board_demo
    out = []
    for c in _or_board_demo() or []:
        c = dict(c)
        for k in list(c):
            if k.startswith('time_') or k in ('actual_duration_min', 'done_before_board'):
                c.pop(k, None)
        c['status'] = 'not_arrived'
        c['_demo'] = True
        out.append(c)
    return out


# ─────────────────────────── หน้าเพจ ───────────────────────────
_CSS = (
    "<style>"
    ".tmr-h{font-size:26px;font-weight:700;margin:4px 0 0;}"
    ".tmr-sub{font-size:15px;color:#64748B;margin:2px 0 14px;}"
    ".tmr-hd{font-size:14px;color:#94A3B8;border-bottom:1px solid #EEF2F6;padding-bottom:6px;}"
    ".tmr-code{font-size:18px;font-weight:700;line-height:1.2;}"
    ".tmr-muted{font-size:13px;color:#94A3B8;}"
    ".tmr-ops{font-size:14px;color:#475569;line-height:1.45;}"
    ".tmr-late{color:#8A5A00;font-weight:700;}"
    "</style>"
)


def page_tomorrow():
    """🗓️ แท็บจัดคิวพรุ่งนี้ : อัปโหลดตารางวันถัดไป + จัดเวรพยาบาล + คัดลอกไป LINE"""
    st.markdown(_CSS, unsafe_allow_html=True)
    today = _now().date()
    c_date, _sp = st.columns([1, 3])
    with c_date:
        target = st.date_input('วันที่ผ่าตัด', value=_next_workday(today),
                               min_value=today, key='tmr_date')
    d = target.isoformat()
    plan = load_day_plan(d) or {}
    cases = plan.get('cases') or []

    st.markdown(f'<div class="tmr-h">{_html.escape(_th_date(target))}</div>', unsafe_allow_html=True)
    if cases:
        st.markdown(f'<div class="tmr-sub">{len(cases)} เคส อัปโหลดเมื่อ '
                    f'{_html.escape(str(plan.get("uploaded_at") or "-"))} น. '
                    f'เข้าบอร์ดเองเมื่อเปิดระบบวันนั้น</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="tmr-sub">ยังไม่มีตารางของวันนี้ : อัปโหลดไฟล์จาก HIS ได้ตั้งแต่ 14:30 น.</div>',
                    unsafe_allow_html=True)

    # ── อัปโหลดตาราง ──
    with st.expander('อัปโหลดตารางใหม่' if cases else 'อัปโหลดตาราง', expanded=not cases):
        up = st.file_uploader('ไฟล์ตารางผ่าตัดจาก HIS (.xls/.xlsx/.csv)',
                              type=['xls', 'xlsx', 'csv'], key='tmr_file')
        if up is not None and st.button('อัปโหลดและทำนายเวลา', type='primary', key='tmr_load'):
            with st.spinner('กำลังอ่านไฟล์และทำนายเวลา...'):
                try:
                    from main_or_app import parse_schedule_csv_to_cases
                    new_cases = parse_schedule_csv_to_cases(up)
                except Exception as ex:
                    new_cases = []
                    st.error(f'อ่านไฟล์ไม่สำเร็จ: {ex}')
            if new_cases:
                plan['cases'] = _mask_cases(new_cases)
                plan['uploaded_at'] = _now().strftime('%H:%M')
                plan['promoted'] = False
                if save_day_plan(d, plan):
                    st.success(f'บันทึกตาราง {len(new_cases)} เคสแล้ว')
                    st.rerun()
                else:
                    st.error('บันทึกไม่สำเร็จ : ลองใหม่อีกครั้ง')
            elif up is not None:
                st.warning('ไม่พบเคสในไฟล์ : ตรวจหัวคอลัมน์ (hn/ชื่อ/หัตถการ/เวลา/ห้อง)')

    # 🎬 DEMO: ปุ่มโหลดตารางตัวอย่าง (ผู้ทดลองใช้ไม่มีไฟล์ HIS)
    if _is_demo_instance():
        if st.button('โหลดตารางตัวอย่าง (สาธิต)', key='tmr_sample',
                     help='ใช้ชุดสาธิตเดียวกับบอร์ด : ผู้ป่วยทดสอบ และแพทย์ A-K '
                          'เวลาทำนายจากแบบจำลองจริง ไม่บันทึกลงฐานข้อมูลวิจัย'):
            with st.spinner('กำลังสร้างตารางตัวอย่างและทำนายเวลา...'):
                try:
                    sample = _sample_cases()
                except Exception as ex:
                    sample = []
                    st.error(f'สร้างตารางตัวอย่างไม่สำเร็จ: {ex}')
            if sample:
                plan['cases'] = _mask_cases(sample)
                plan['uploaded_at'] = _now().strftime('%H:%M')
                plan['promoted'] = False
                # 🎬 มุกกี้สั่ง 7 พ.ย. 2026: กดแล้วต้องเห็นตารางที่จัดเวรครบเลย ไม่ต้องกรอกเอง
                plan['staff'] = dict(_SAMPLE_STAFF)
                plan['absences'] = {k: list(v) for k, v in _SAMPLE_ABSENCES.items()}
                _save_roster(_load_roster() + _SAMPLE_ROSTER)
                # ล้างค่าช่องเลือกที่ค้างใน session ไม่งั้นช่องจะโชว์ค่าเก่าแทนเวรตัวอย่าง
                for _k in [k for k in st.session_state.keys() if str(k).startswith(f'tmr_{d}_')]:
                    del st.session_state[_k]
                if save_day_plan(d, plan):
                    st.success(f'โหลดตารางตัวอย่าง {len(sample)} เคสแล้ว')
                    st.rerun()

    if not cases:
        return

    rooms = _room_summary(cases)
    staff = dict(plan.get('staff') or {})
    absences = plan.get('absences') or {}
    roster = _load_roster()

    # ── ฟอร์มจัดเวร (กดบันทึกครั้งเดียว ไม่ rerun ทุกช่อง) ──
    with st.form('tmr_staff_form', border=False):
        h = st.columns([1, 1.3, 2.6, 4.4])
        for col, t in zip(h, ['ห้อง', 'เคส', 'Operation', 'พยาบาล']):
            col.markdown(f'<div class="tmr-hd">{t}</div>', unsafe_allow_html=True)
        new_staff = {}
        for rm in rooms:
            c1, c2, c3, c4 = st.columns([1, 1.3, 2.6, 4.4], vertical_alignment='center')
            c1.markdown(f'<div class="tmr-code">{rm["code"]}</div>'
                        f'<div class="tmr-muted">{_html.escape(rm["spec"])}</div>', unsafe_allow_html=True)
            late = ' tmr-late' if rm['finish'] >= CUT_1530 - 15 else ''
            c2.markdown(f'<div style="font-size:17px;">{rm["n"]} เคส</div>'
                        f'<div class="tmr-muted{late}">เสร็จประมาณ {_hhmm(rm["finish"])}</div>',
                        unsafe_allow_html=True)
            c3.markdown('<div class="tmr-ops">' + '<br>'.join(
                f'{i}. {_html.escape(op)}' for i, op in enumerate(rm['ops'], 1)) + '</div>',
                unsafe_allow_html=True)
            with c4:
                sc = st.columns(ROOM_SLOTS)
                for k in range(1, ROOM_SLOTS + 1):
                    sid = f"r{rm['room_no']}-{k}"
                    with sc[k - 1]:
                        new_staff[sid] = _select(f"{rm['code']} คนที่ {k}", roster, staff.get(sid, ''),
                                                 key=f'tmr_{d}_{sid}', hide_label=True)
        st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
        pc = st.columns(len(POSTS))
        for (pid, lbl), col in zip(POSTS, pc):
            with col:
                new_staff[pid] = _select(lbl, roster, staff.get(pid, ''), key=f'tmr_{d}_{pid}')
        new_abs = {}
        ac = st.columns(len(ABSENCES))
        for (ak, lbl), col in zip(ABSENCES, ac):
            with col:
                new_abs[ak] = _multi(lbl, roster, list(absences.get(ak, [])), key=f'tmr_{d}_abs_{ak}')
        saved = st.form_submit_button('บันทึก', type='primary')

    if saved:
        used = {}
        for sid, v in new_staff.items():
            if v:
                used.setdefault(v, []).append(sid)
        away = {n: lbl for ak, lbl in ABSENCES for n in new_abs.get(ak, [])}
        problems = [f'{n} ถูกจัดซ้ำ {len(s)} จุด' for n, s in used.items() if len(s) > 1]
        problems += [f'{n} อยู่ในรายชื่อ{away[n]}' for n in used if n in away]
        if problems:
            st.error('ต้องแก้ก่อนบันทึก : ' + ' | '.join(problems))
        else:
            plan['staff'] = {k: v for k, v in new_staff.items() if v}
            plan['absences'] = new_abs
            if save_day_plan(d, plan):
                _save_roster(roster + list(used) + list(away))
                st.success('บันทึกเวรแล้ว')
                plan = load_day_plan(d) or plan
            else:
                st.error('บันทึกไม่สำเร็จ : ลองใหม่อีกครั้ง')

    # ── ท้ายหน้า : คนที่ยังว่าง + คัดลอกไป LINE ──
    st_saved = plan.get('staff') or {}
    away_saved = {n for ak, _ in ABSENCES for n in (plan.get('absences') or {}).get(ak, [])}
    free = [n for n in _load_roster() if n not in st_saved.values() and n not in away_saved]
    st.caption(('ยังว่าง ' + str(len(free)) + ' คน : ' + ', '.join(free)) if free else 'จัดครบทุกคนแล้ว')
    _render_copy_card(target, rooms, plan)

    with st.expander('รายชื่อพยาบาล', expanded=False):
        txt = st.text_area('ชื่อเล่นหรือชื่อต้น บรรทัดละ 1 คน', value='\n'.join(_load_roster()),
                           height=160, key='tmr_roster_txt')
        if st.button('บันทึกรายชื่อ', key='tmr_roster_save'):
            _save_roster([x for x in txt.splitlines() if x.strip()])
            st.success('บันทึกรายชื่อแล้ว')


def _render_copy_card(target: _date, rooms, plan):
    """📋 ปุ่มคัดลอกใบสรุปเวรเป็นภาพ (วางใน LINE) · html2canvas ฝั่งเบราว์เซอร์
    คัดลอกไม่ได้ (เบราว์เซอร์ไม่อนุญาต) → ดาวน์โหลดเป็นไฟล์ PNG แทน · ไม่มีชื่อผู้ป่วย"""
    import streamlit.components.v1 as components
    e = _html.escape
    staff = plan.get('staff') or {}
    room_rows = ''.join(
        f'<div><b>{e(rm["code"])}</b> <span style="color:#64748B;font-size:12px">{e(rm["spec"])}</span> : '
        + e(', '.join(v for v in (staff.get(f"r{rm['room_no']}-{k}", '') for k in range(1, ROOM_SLOTS + 1)) if v) or '-')
        + '</div>' for rm in rooms)
    post_rows = ''.join(f'<div><b>{e(lbl)}</b> : {e(staff.get(pid, "") or "-")}</div>' for pid, lbl in POSTS)
    abs_rows = ''.join(f'<div><b>{e(lbl)}</b> : {e(", ".join((plan.get("absences") or {}).get(ak, [])) or "-")}</div>'
                       for ak, lbl in ABSENCES)
    n_cases = sum(rm['n'] for rm in rooms)
    fname = f"เวร_{target.isoformat()}.png"
    card = f"""
<div id="card" style="width:480px;background:#fff;border:1px solid #CBD5E1;border-radius:10px;padding:14px 16px;
 font-family:Sarabun,'Noto Sans Thai',Tahoma,sans-serif;color:#0F172A;box-sizing:border-box">
 <div style="font-size:16px;font-weight:700">เวรห้องผ่าตัดศัลยกรรมทั่วไป</div>
 <div style="font-size:13px;color:#64748B;border-bottom:1px solid #E2E8F0;padding-bottom:8px;margin-bottom:8px">
  {e(_th_date(target))} : ผ่าตัด {n_cases} เคส</div>
 <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 12px;font-size:14px">{room_rows}</div>
 <div style="font-size:14px;border-top:1px solid #E2E8F0;margin-top:8px;padding-top:8px">{post_rows}</div>
 <div style="font-size:14px;color:#475569;border-top:1px solid #E2E8F0;margin-top:8px;padding-top:8px">{abs_rows}</div>
</div>"""
    components.html(f"""
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;700&display=swap" rel="stylesheet">
<div style="position:absolute;left:-9999px;top:0">{card}</div>
<button id="cp" style="font-family:Sarabun,sans-serif;font-size:16px;padding:10px 18px;min-height:44px;
 border:1px solid #CBD5E1;border-radius:8px;background:#fff;cursor:pointer">คัดลอกไปวางใน LINE</button>
<span id="msg" style="font-family:Sarabun,sans-serif;font-size:14px;color:#64748B;margin-left:10px"></span>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script>
const btn=document.getElementById('cp'), msg=document.getElementById('msg');
btn.onclick=async()=>{{
  msg.textContent='กำลังสร้างภาพ...';
  try {{
    const cv=await html2canvas(document.getElementById('card'),{{scale:2,backgroundColor:'#ffffff'}});
    const blob=await new Promise(r=>cv.toBlob(r,'image/png'));
    try {{
      await navigator.clipboard.write([new ClipboardItem({{'image/png':blob}})]);
      msg.textContent='คัดลอกแล้ว : เปิด LINE แล้วกด Ctrl+V';
    }} catch(e) {{
      const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download={json.dumps(fname)};
      document.body.appendChild(a); a.click(); a.remove();
      msg.textContent='เบราว์เซอร์ไม่อนุญาตให้คัดลอก : ดาวน์โหลดเป็นไฟล์ภาพแทนแล้ว';
    }}
  }} catch(e) {{ msg.textContent='สร้างภาพไม่สำเร็จ : '+e; }}
}};
</script>""", height=60)
