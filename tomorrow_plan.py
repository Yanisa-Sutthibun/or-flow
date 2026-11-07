# -*- coding: utf-8 -*-
"""
tomorrow_plan.py : 🗓️ จัดคิวพรุ่งนี้ + จัดเวรพยาบาล (แอป DEMO · มุกกี้สั่ง 7 พ.ย. 2026)
════════════════════════════════════════════════════════════════════════════
แยก "คนจัด" ออกจาก "คนดู" ตามแบบที่มุกกี้ร่าง:
  ⚙️ ตั้งค่า > จัดเวรพรุ่งนี้  (render_staff_editor) : หัวหน้าอัปโหลดตาราง + จัดเวร + บันทึก
  🗓️ แท็บจัดคิวพรุ่งนี้          (page_tomorrow)       : ทุกคนดูอย่างเดียว + คัดลอกไป LINE
     ยังไม่บันทึก = "กำลังดำเนินการ"
ตารางเวร: แถวรับ-ส่ง (จำนวนเคสทั้งหมด) + OR1-OR9 (operation ตามคิว, เวลาโดยประมาณ)
  คอลัมน์มอบหมายงาน = หัวหน้าห้อง + สมาชิก 3 ช่อง
  ใต้ตาราง: HN · ทั่วไป · OT · เวรเสริม · ลาพักผ่อน · ลาชั่วโมง (พิมพ์เอง) · อบรมนอกหน่วยงาน

ที่เก็บ: app_settings คีย์ day_plan_YYYY-MM-DD
  { date, uploaded_at, cases:[...], staff:{slot: ชื่อ}, absences:{vac:[],train:[]},
    leave_hours: str, staff_saved_at: 'HH:MM', promoted: bool }
  · ชื่อ/HN ผู้ป่วย mask ก่อนเขียน (กติกาเดียวกับ _save_board_snapshot) · procnote ไม่ขึ้นคลาวด์
  · ชื่อพยาบาล mask ด้วย _mask_nurse_name (ชื่อต้น + อักษรแรกนามสกุล)
  · ข้อมูลเวรไม่เข้าตารางวิจัยใด ๆ · ลบแผนที่เก่ากว่า 7 วันทุกครั้งที่บันทึก
ถึงวันนั้น บอร์ดว่างเครื่องแรกที่เปิด → promote_plan_if_needed() ย้ายเคสเข้าบอร์ด (ครั้งเดียว)
"""
from __future__ import annotations

import json
import html as _html
from datetime import timedelta, date as _date

import streamlit as st

TURNOVER_DEFAULT = 20          # นาที (ใช้ median รายห้องจาก command_center ถ้ามี)
DAY_START_MIN = 8 * 60 + 30    # เคสแรกเริ่ม 08:30 ถ้าไฟล์ไม่มีเวลานัด
CUT_1530 = 15 * 60 + 30
SLOT_LABELS = ['หัวหน้าห้อง', 'สมาชิก', 'สมาชิก', 'สมาชิก']
POSTS = [('p-hn', 'HN'), ('p-gen', 'ทั่วไป'), ('p-ot', 'OT'), ('p-extra', 'เวรเสริม')]
ABSENCES = [('vac', 'ลาพักผ่อน'), ('train', 'อบรมนอกหน่วยงาน')]
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


def _dur(m) -> str:
    m = int(round(m))
    return f"{m // 60} ชม. {m % 60} นาที" if m >= 60 else f"{m} นาที"


def _is_demo_instance() -> bool:
    try:
        return str(st.secrets.get('instance_mode', '')).lower() == 'demo'
    except Exception:
        return False


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


def save_day_plan(d: str, plan: dict) -> bool:
    """บันทึกแผน (mask ชื่อพยาบาลแล้ว) + ลบแผนเก่ากว่า 7 วัน · คืน True ถ้าสำเร็จ"""
    try:
        from main_or_db import _set_app_setting, get_conn
        from main_or_pages import _mask_nurse_name
        p = dict(plan)
        p['date'] = d
        p['staff'] = {k: _mask_nurse_name(v) for k, v in (p.get('staff') or {}).items() if v}
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
    """🗓️ เปิดบอร์ดวันใหม่แล้วยังว่าง → ย้ายเคสจากแผนเข้าบอร์ด (ครั้งเดียวต่อวัน)
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
    """เวรของวัน d (ใช้ที่ภาพรวมวันนี้) : rooms {room_no: [ชื่อ]}, posts {label: ชื่อ}, absences {label: [..]}
    ยังไม่บันทึกเวร = คืนค่าว่าง"""
    plan = load_day_plan(d) or {}
    if not plan.get('staff_saved_at'):
        return {'rooms': {}, 'posts': {}, 'absences': {}}
    staff = plan.get('staff') or {}
    rooms = {}
    for k, v in sorted(staff.items()):
        if k.startswith('r') and not k.startswith('rs') and '-' in k:
            try:
                rooms.setdefault(int(k[1:].split('-')[0]), []).append(v)
            except ValueError:
                continue
    rs = ', '.join(staff.get(f'rs-{i}', '') for i in range(1, 5) if staff.get(f'rs-{i}'))
    posts = {'รับ-ส่ง': rs}
    posts.update({lbl: staff.get(pid, '') for pid, lbl in POSTS})
    absn = {lbl: (plan.get('absences') or {}).get(k, []) for k, lbl in ABSENCES}
    if plan.get('leave_hours'):
        absn['ลาชั่วโมง'] = [plan['leave_hours']]
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
    kw = dict(index=idx, key=key, label_visibility='collapsed' if hide_label else 'visible',
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
                              accept_new_options=True, placeholder='เลือกหรือพิมพ์ชื่อ')
    except TypeError:
        return st.multiselect(label, opts, default=values, key=key)


# ─────────────────────────── สรุปรายห้อง ───────────────────────────
def _room_rows(cases):
    """คืน 9 แถว (OR1-OR9 จาก room_config) : room_no, code, spec, n, ops[], mins (เวลาทำนายรวม), finish"""
    import room_config
    try:
        from command_center import _turnover_for, _turnover_map
        tmap = _turnover_map()
    except Exception:
        _turnover_for, tmap = None, {}
    by_room = {}
    for c in cases or []:
        try:
            r = int(float(c.get('room')))
        except (TypeError, ValueError):
            continue
        by_room.setdefault(r, []).append(c)
    rooms = list(room_config.ROOM_INFO.keys())
    rooms += [r for r in sorted(by_room) if r not in rooms]
    out = []
    for r in rooms:
        lst = sorted(by_room.get(r, []), key=lambda c: (
            int(c.get('ororder') or 99),
            int(c.get('sched_hour') or 23) * 60 + int(c.get('sched_min') or 0)))
        mins = [int(c.get('effective_min') or c.get('ai_predicted_min') or c.get('predicted_min') or 60)
                for c in lst]
        starts = [int(c.get('sched_hour')) * 60 + int(c.get('sched_min') or 0)
                  for c in lst if c.get('sched_hour') is not None and int(c.get('sched_hour')) < 23]
        turn = _turnover_for({'room_no': r}, tmap) if (_turnover_for and lst) else TURNOVER_DEFAULT
        total = sum(mins) + turn * max(len(mins) - 1, 0)
        start = min(starts) if starts else DAY_START_MIN
        name, spec = room_config.ROOM_INFO.get(r, (f'ห้อง {r}', ''))
        out.append({'room_no': r, 'code': name, 'spec': spec, 'n': len(lst),
                    'ops': [str(c.get('procedure') or '-') for c in lst],
                    'mins': sum(mins), 'finish': start + total if lst else None})
    return out


# ─────────────────────────── ตารางตัวอย่าง (DEMO) ───────────────────────────
_SAMPLE_ROSTER = ['แก้ว', 'น้ำฝน', 'ปลา', 'มิ้นท์', 'ฝ้าย', 'จอย', 'แพร', 'ต้น', 'บีม', 'ออม',
                  'เมย์', 'นุ่น', 'ฟ้า', 'ขวัญ', 'ปุ้ย', 'หนิง', 'ตาล', 'แนน', 'เบียร์', 'กิ๊ฟ',
                  'โบว์', 'อ้อม', 'ปู', 'ไหม', 'ใบเตย', 'พลอย', 'ส้ม', 'แอน', 'จูน', 'ก้อย',
                  'ป่าน', 'เอิร์ธ', 'ข้าวหอม', 'มายด์']
_SAMPLE_STAFF = {
    'rs-1': 'น้ำฝน', 'rs-2': 'ขวัญ',
    'r91-1': 'ฝ้าย', 'r91-2': 'ปุ้ย', 'r91-3': 'หนิง',
    'r92-1': 'แพร', 'r92-2': 'ตาล', 'r92-3': 'แนน',
    'r93-1': 'มิ้นท์', 'r93-2': 'เบียร์', 'r93-3': 'กิ๊ฟ',
    'r94-1': 'จอย', 'r94-2': 'โบว์', 'r94-3': 'อ้อม',
    'r95-1': 'ต้น', 'r95-2': 'ปู', 'r95-3': 'ไหม', 'r95-4': 'ใบเตย',
    'r96-1': 'ออม', 'r96-2': 'พลอย', 'r96-3': 'ส้ม',
    'r97-1': 'บีม', 'r97-2': 'แอน', 'r97-3': 'จูน',
    'p-hn': 'แก้ว', 'p-gen': 'ฟ้า', 'p-ot': 'ปลา', 'p-extra': 'เมย์',
}
_SAMPLE_ABSENCES = {'vac': ['นุ่น'], 'train': ['ป่าน']}
_SAMPLE_LEAVE_HOURS = 'ก้อย 13:00-16:00'


def _sample_cases():
    """🎬 ตารางตัวอย่าง (DEMO): ชุดสาธิตเดียวกับบอร์ด (ผู้ป่วยทดสอบ NN / แพทย์ A-K)
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


# ─────────────────────────── CSS ร่วม ───────────────────────────
_CSS = (
    "<style>"
    ".tmr-h{font-size:26px;font-weight:700;margin:4px 0 0;}"
    ".tmr-sub{font-size:15px;color:#64748B;margin:2px 0 14px;}"
    ".tmr-hd{font-size:14px;color:#64748B;font-weight:600;border-bottom:1px solid #E2E8F0;padding-bottom:6px;}"
    ".tmr-code{font-size:17px;font-weight:700;line-height:1.2;}"
    ".tmr-muted{font-size:13px;color:#94A3B8;}"
    ".tmr-ops{font-size:14px;color:#475569;line-height:1.45;}"
    ".tmr-late{color:#8A5A00;font-weight:700;}"
    ".tmr-tbl{width:100%;border-collapse:collapse;font-size:15px;}"
    ".tmr-tbl th{font-size:14px;color:#64748B;font-weight:600;text-align:left;padding:8px 10px;"
    "border-bottom:1px solid #E2E8F0;background:#F8FAFC;}"
    ".tmr-tbl td{padding:8px 10px;border-bottom:1px solid #F1F5F9;vertical-align:top;}"
    "</style>"
)


def _pick_date(key):
    today = _now().date()
    c_date, _sp = st.columns([1, 3])
    with c_date:
        target = st.date_input('วันที่ผ่าตัด', value=_next_workday(today), min_value=today, key=key)
    return target


# ─────────────────────────── ⚙️ ตั้งค่า > จัดเวรพรุ่งนี้ (หัวหน้า) ───────────────────────────
def render_staff_editor():
    """หัวหน้าเวร: อัปโหลดตารางวันถัดไป + จัดเวรตามแบบท้ายใบตาราง + บันทึก"""
    st.markdown(_CSS, unsafe_allow_html=True)
    target = _pick_date('tmr_edit_date')
    d = target.isoformat()
    plan = load_day_plan(d) or {}
    cases = plan.get('cases') or []

    st.markdown(f'<div class="tmr-h">จัดเวร {_html.escape(_th_date(target))}</div>', unsafe_allow_html=True)
    saved_at = plan.get('staff_saved_at')
    st.markdown('<div class="tmr-sub">' + (
        f'บันทึกเวรล่าสุด {_html.escape(saved_at)} น. แก้แล้วกดบันทึกอีกครั้งได้' if saved_at else
        'ยังไม่ได้บันทึกเวร : แท็บจัดคิวพรุ่งนี้จะขึ้นว่า "กำลังดำเนินการ"') + '</div>',
        unsafe_allow_html=True)

    # ── ตาราง : อัปโหลด หรือ ตัวอย่าง (DEMO) ──
    c_up, c_demo = st.columns([3, 1], vertical_alignment='bottom')
    with c_up:
        with st.expander('อัปโหลดตารางผ่าตัด' + (f' (มีแล้ว {len(cases)} เคส)' if cases else ''),
                         expanded=not cases):
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
                        st.rerun()
                    st.error('บันทึกไม่สำเร็จ : ลองใหม่อีกครั้ง')
                else:
                    st.warning('ไม่พบเคสในไฟล์ : ตรวจหัวคอลัมน์ (hn/ชื่อ/หัตถการ/เวลา/ห้อง)')
    with c_demo:
        if _is_demo_instance() and st.button(
                'โหลดตัวอย่าง (สาธิต)', key='tmr_sample', use_container_width=True,
                help='ตารางผ่าตัดและเวรตัวอย่างครบชุด ชื่อสมมติทั้งหมด ไม่บันทึกลงฐานข้อมูลวิจัย'):
            with st.spinner('กำลังสร้างตัวอย่างและทำนายเวลา...'):
                try:
                    sample = _sample_cases()
                except Exception as ex:
                    sample = []
                    st.error(f'สร้างตัวอย่างไม่สำเร็จ: {ex}')
            if sample:
                plan.update(cases=_mask_cases(sample), uploaded_at=_now().strftime('%H:%M'),
                            promoted=False, staff=dict(_SAMPLE_STAFF),
                            absences={k: list(v) for k, v in _SAMPLE_ABSENCES.items()},
                            leave_hours=_SAMPLE_LEAVE_HOURS, staff_saved_at=_now().strftime('%H:%M'))
                _save_roster(_load_roster() + _SAMPLE_ROSTER)
                for _k in [k for k in st.session_state.keys() if str(k).startswith(f'tmr_{d}_')]:
                    del st.session_state[_k]      # ล้างช่องเลือกค้าง ไม่งั้นโชว์ค่าเก่าแทนตัวอย่าง
                if save_day_plan(d, plan):
                    st.rerun()

    rows = _room_rows(cases)
    staff = dict(plan.get('staff') or {})
    absences = plan.get('absences') or {}
    roster = _load_roster()
    W = [0.9, 2.6, 1.3, 1.25, 1.25, 1.25, 1.25]

    with st.form('tmr_staff_form', border=False):
        h = st.columns(W)
        for col, t in zip(h, ['ห้อง', 'operation', 'ใช้เวลาโดยประมาณ'] + SLOT_LABELS):
            col.markdown(f'<div class="tmr-hd">{t}</div>', unsafe_allow_html=True)
        new_staff = {}

        def _slots(prefix, label_prefix, cols):
            for k, col in enumerate(cols, 1):
                sid = f'{prefix}-{k}'
                with col:
                    new_staff[sid] = _select(f'{label_prefix} {SLOT_LABELS[k - 1]}', roster,
                                             staff.get(sid, ''), key=f'tmr_{d}_{sid}', hide_label=True)

        # แถวรับ-ส่ง : operation = จำนวนเคสทั้งหมด
        cs = st.columns(W, vertical_alignment='center')
        cs[0].markdown('<div class="tmr-code">รับ-ส่ง</div>', unsafe_allow_html=True)
        cs[1].markdown(f'<div class="tmr-ops">ทั้งหมด {len(cases)} เคส</div>', unsafe_allow_html=True)
        cs[2].markdown('<div class="tmr-muted">-</div>', unsafe_allow_html=True)
        _slots('rs', 'รับ-ส่ง', cs[3:])

        for rm in rows:
            cs = st.columns(W, vertical_alignment='center')
            cs[0].markdown(f'<div class="tmr-code">{_html.escape(rm["code"])}</div>'
                           f'<div class="tmr-muted">{_html.escape(rm["spec"])}</div>', unsafe_allow_html=True)
            cs[1].markdown('<div class="tmr-ops">' + ('<br>'.join(
                f'{i}. {_html.escape(op)}' for i, op in enumerate(rm['ops'], 1)) or
                '<span class="tmr-muted">ไม่มีเคส</span>') + '</div>', unsafe_allow_html=True)
            if rm['n']:
                late = ' tmr-late' if rm['finish'] >= CUT_1530 - 15 else ''
                cs[2].markdown(f'<div style="font-size:15px;">{_dur(rm["mins"])}</div>'
                               f'<div class="tmr-muted{late}">เสร็จประมาณ {_hhmm(rm["finish"])}</div>',
                               unsafe_allow_html=True)
            else:
                cs[2].markdown('<div class="tmr-muted">-</div>', unsafe_allow_html=True)
            _slots(f"r{rm['room_no']}", rm['code'], cs[3:])

        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
        pc = st.columns(len(POSTS))
        for (pid, lbl), col in zip(POSTS, pc):
            with col:
                new_staff[pid] = _select(lbl, roster, staff.get(pid, ''), key=f'tmr_{d}_{pid}')
        a1, a2, a3 = st.columns(3)
        with a1:
            vac = _multi('ลาพักผ่อน', roster, list(absences.get('vac', [])), key=f'tmr_{d}_abs_vac')
        with a2:
            leave_h = st.text_input('ลาชั่วโมง', value=plan.get('leave_hours', ''),
                                    placeholder='เช่น แก้ว 13:00-16:00', key=f'tmr_{d}_leave_h')
        with a3:
            train = _multi('อบรมนอกหน่วยงาน', roster, list(absences.get('train', [])), key=f'tmr_{d}_abs_train')
        saved = st.form_submit_button('บันทึก', type='primary')

    if saved:
        used = {}
        for sid, v in new_staff.items():
            if v:
                used.setdefault(v, []).append(sid)
        away = {n: 'ลาพักผ่อน' for n in vac}
        away.update({n: 'อบรมนอกหน่วยงาน' for n in train})
        problems = [f'{n} ถูกจัดซ้ำ {len(s)} จุด' for n, s in used.items() if len(s) > 1]
        problems += [f'{n} อยู่ในรายชื่อ{away[n]}' for n in used if n in away]
        if problems:
            st.error('ต้องแก้ก่อนบันทึก : ' + ' | '.join(problems))
        else:
            plan.update(staff={k: v for k, v in new_staff.items() if v},
                        absences={'vac': vac, 'train': train},
                        leave_hours=(leave_h or '').strip(), staff_saved_at=_now().strftime('%H:%M'))
            if save_day_plan(d, plan):
                _save_roster(roster + list(used) + list(away))
                st.success('บันทึกเวรแล้ว : ไปแสดงที่แท็บจัดคิวพรุ่งนี้')
            else:
                st.error('บันทึกไม่สำเร็จ : ลองใหม่อีกครั้ง')

    with st.expander('รายชื่อพยาบาล', expanded=False):
        txt = st.text_area('ชื่อเล่นหรือชื่อต้น บรรทัดละ 1 คน', value='\n'.join(_load_roster()),
                           height=160, key='tmr_roster_txt')
        if st.button('บันทึกรายชื่อ', key='tmr_roster_save'):
            _save_roster([x for x in (txt or '').splitlines() if x.strip()])
            st.success('บันทึกรายชื่อแล้ว')


# ─────────────────────────── 🗓️ แท็บจัดคิวพรุ่งนี้ (ดูอย่างเดียว) ───────────────────────────
def page_tomorrow():
    """ทุกคนดูอย่างเดียว · ยังไม่บันทึกเวร = กำลังดำเนินการ · คัดลอกไป LINE"""
    st.markdown(_CSS, unsafe_allow_html=True)
    target = _pick_date('tmr_view_date')
    d = target.isoformat()
    plan = load_day_plan(d) or {}
    st.markdown(f'<div class="tmr-h">{_html.escape(_th_date(target))}</div>', unsafe_allow_html=True)

    if not plan.get('staff_saved_at'):
        n = len(plan.get('cases') or [])
        st.markdown(
            '<div style="margin-top:14px;padding:22px;border:1px dashed #CBD5E1;border-radius:12px;'
            'text-align:center;"><div style="font-size:22px;font-weight:700;color:#334155;">กำลังดำเนินการ</div>'
            '<div style="font-size:15px;color:#64748B;margin-top:4px;">หัวหน้ากำลังจัดตารางเวร'
            + (f' : ได้รับตารางผ่าตัดแล้ว {n} เคส' if n else '') + '</div></div>',
            unsafe_allow_html=True)
        return

    cases = plan.get('cases') or []
    st.markdown(f'<div class="tmr-sub">ผ่าตัด {len(cases)} เคส จัดเวรเมื่อ '
                f'{_html.escape(plan["staff_saved_at"])} น.</div>', unsafe_allow_html=True)
    rows = _room_rows(cases)
    staff = plan.get('staff') or {}
    e = _html.escape
    dash = '<span style="color:#CBD5E1">-</span>'

    def _cells(prefix):
        return ''.join(f'<td>{e(staff.get(f"{prefix}-{k}", "")) or dash}</td>' for k in range(1, 5))

    body = f'<tr><td><b>รับ-ส่ง</b></td><td>ทั้งหมด {len(cases)} เคส</td><td>-</td>{_cells("rs")}</tr>'
    for rm in rows:
        if not rm['n'] and not any(staff.get(f"r{rm['room_no']}-{k}") for k in range(1, 5)):
            continue                      # ห้องไม่มีเคสและไม่มีเวร ไม่ต้องโชว์
        ops = ('<br>'.join(f'{i}. {e(op)}' for i, op in enumerate(rm['ops'], 1))
               or '<span style="color:#94A3B8">ไม่มีเคส</span>')
        if rm['n']:
            late = 'color:#8A5A00;font-weight:700;' if rm['finish'] >= CUT_1530 - 15 else 'color:#94A3B8;'
            tm = f'{_dur(rm["mins"])}<div style="font-size:13px;{late}">เสร็จประมาณ {_hhmm(rm["finish"])}</div>'
        else:
            tm = '-'
        body += (f'<tr><td><b>{e(rm["code"])}</b><div style="font-size:12px;color:#94A3B8">{e(rm["spec"])}</div></td>'
                 f'<td style="font-size:14px;color:#475569">{ops}</td><td>{tm}</td>'
                 f'{_cells("r" + str(rm["room_no"]))}</tr>')
    head = ''.join(f'<th>{t}</th>' for t in ['ห้อง', 'operation', 'ใช้เวลาโดยประมาณ'] + SLOT_LABELS)
    st.markdown(f'<div style="overflow-x:auto"><table class="tmr-tbl"><thead><tr>{head}</tr></thead>'
                f'<tbody>{body}</tbody></table></div>', unsafe_allow_html=True)

    info = staff_for(d)
    lines = [f'<div><b>{e(k)}</b> : {e(v) or "-"}</div>' for k, v in info['posts'].items() if k != 'รับ-ส่ง']
    lines += [f'<div style="color:#475569"><b>{e(k)}</b> : {e(", ".join(v)) or "-"}</div>'
              for k, v in info['absences'].items()]
    st.markdown('<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 24px;'
                'font-size:15px;margin:16px 0 8px;">' + ''.join(lines) + '</div>', unsafe_allow_html=True)
    _render_copy_card(target, rows, plan, info)


def _render_copy_card(target: _date, rows, plan, info):
    """📋 ปุ่มคัดลอกใบสรุปเวรเป็นภาพ (วางใน LINE) · html2canvas ฝั่งเบราว์เซอร์
    คัดลอกไม่ได้ (เบราว์เซอร์ไม่อนุญาต) → ดาวน์โหลดเป็นไฟล์ PNG แทน · ไม่มีชื่อผู้ป่วย"""
    import streamlit.components.v1 as components
    e = _html.escape
    staff = plan.get('staff') or {}

    def _names(prefix):
        lst = [staff.get(f'{prefix}-{k}', '') for k in range(1, 5)]
        return ', '.join(v for v in lst if v) or '-'
    room_rows = f'<div><b>รับ-ส่ง</b> : {e(_names("rs"))}</div>' + ''.join(
        f'<div><b>{e(rm["code"])}</b> <span style="color:#64748B;font-size:12px">{e(rm["spec"])}</span> : '
        f'{e(_names("r" + str(rm["room_no"])))}</div>' for rm in rows if rm['n'])
    post_rows = ''.join(f'<div><b>{e(k)}</b> : {e(v) or "-"}</div>'
                        for k, v in info['posts'].items() if k != 'รับ-ส่ง')
    abs_rows = ''.join(f'<div><b>{e(k)}</b> : {e(", ".join(v)) or "-"}</div>'
                       for k, v in info['absences'].items())
    n_cases = len(plan.get('cases') or [])
    fname = f"เวร_{target.isoformat()}.png"
    card = f"""
<div id="card" style="width:500px;background:#fff;border:1px solid #CBD5E1;border-radius:10px;padding:14px 16px;
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
    }} catch(err) {{
      const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download={json.dumps(fname)};
      document.body.appendChild(a); a.click(); a.remove();
      msg.textContent='เบราว์เซอร์ไม่อนุญาตให้คัดลอก : ดาวน์โหลดเป็นไฟล์ภาพแทนแล้ว';
    }}
  }} catch(err) {{ msg.textContent='สร้างภาพไม่สำเร็จ : '+err; }}
}};
</script>""", height=60)
