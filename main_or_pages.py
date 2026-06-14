"""
Main OR — OR Board + Statistics Pages
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone
import json

# 🕐 เวลามาตรฐานกรุงเทพ — กันเพี้ยนเมื่อ deploy บน server/cloud ต่าง timezone
# (board เดิมใช้ datetime.now() = เวลา server → บน cloud UTC จะคลาด 7 ชม.)
_BKK = timezone(timedelta(hours=7))


def _now():
    """เวลาปัจจุบันโซนกรุงเทพ (naive) — ใช้แทน datetime.now() ทุกที่บนบอร์ด"""
    return datetime.now(_BKK).replace(tzinfo=None)


# ============================================================================
# 💾 Snapshot บอร์ดลงไฟล์ — กันข้อมูลหายเมื่อกด F5 / รีสตาร์ทแอพ
# (ก่อนต่อ Supabase: board อยู่ใน session_state ซึ่งหายเมื่อ reload จริง)
# เก็บเป็น JSON ในเครื่อง 1 ไฟล์/วัน · fail-safe: พังก็ไม่กระทบบอร์ด (try/except)
# ============================================================================
import os as _os
from datetime import date as _date

_SNAPSHOT_PATH = _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'data', '_board_snapshot.json')


def _ser(v):
    """แปลงค่าใน case ให้เป็น JSON ได้ (datetime/date → marker)
    + รองรับ numpy scalar (.item()) ที่อาจหลุดมาจาก pandas/โมเดล"""
    if isinstance(v, datetime):
        return {'__dt__': v.isoformat()}
    if isinstance(v, _date):
        return {'__d__': v.isoformat()}
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if hasattr(v, 'item'):  # numpy.int64/float64 → Python native
        try:
            return v.item()
        except Exception:
            return str(v)
    return v


def _deser(v):
    """แปลง marker กลับเป็น datetime/date"""
    if isinstance(v, dict) and '__dt__' in v:
        try:
            return datetime.fromisoformat(v['__dt__'])
        except (ValueError, TypeError):
            return None
    if isinstance(v, dict) and '__d__' in v:
        try:
            return _date.fromisoformat(v['__d__'])
        except (ValueError, TypeError):
            return None
    return v


def _board_case_key(d):
    """คีย์ระบุเคสข้ามเครื่อง/ข้าม payload (ใช้ตอน merge) — id ก่อน ไม่มีค่อย composite"""
    cid = d.get('id')
    if cid not in (None, ''):
        return f"id:{cid}"
    return (f"k:{d.get('hn','')}|{d.get('procedure','')}|"
            f"{d.get('sched_hour','')}:{d.get('sched_min','')}")


def _mark_board_dirty(case=None):
    """ทำเครื่องหมายว่า 'เครื่องนี้เพิ่งแก้บอร์ดจริง' → ค่อยเซฟ + กัน pull ทับ (CR-2)
    เก็บ id เคสที่แก้ไว้ใน _board_dirty_ids เพื่อ merge ราย-เคสตอนเซฟ"""
    try:
        st.session_state['_board_dirty'] = True
        ids = st.session_state.get('_board_dirty_ids')
        if not isinstance(ids, set):
            ids = set()
        if case is not None and case.get('id') not in (None, ''):
            ids.add(case.get('id'))
        st.session_state['_board_dirty_ids'] = ids
    except Exception:
        pass


def _mask_nurse_name(name):
    """🔒 mask ชื่อพยาบาลก่อนขึ้น cloud → 'ชื่อต้น + อักษรแรกนามสกุล.'
    เช่น 'กนกวรรณ มีแก้ว' -> 'กนกวรรณ ม.' (เผื่อข้อมูลเก่ามียศติดมา ตัดยศออกก่อน)"""
    import re as _re
    s = str(name or '').strip()
    if not s:
        return s
    s = _re.sub(r'^ว่าที่\s*', '', s)   # ตัด 'ว่าที่' นำหน้ายศ
    for t in ('นางสาว', 'นาง', 'นาย', 'ด.ช.', 'ด.ญ.', 'น.ส.'):
        if s.startswith(t):
            s = s[len(t):]
            break
    else:
        m = _re.match(r'^((?:[ก-ฮ]{1,2}\.)+)', s)   # ยศตำรวจ เช่น พ.ต.ท. จ.ส.ต.
        if m:
            s = s[m.end():]
    s = _re.sub(r'^(หญิง|ชาย)\s*', '', s).strip()
    parts = s.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    return parts[0] if parts else s


def _save_board_snapshot(cases):
    """บันทึกบอร์ดปัจจุบันลง DB กลาง + ไฟล์ local — ไม่ throw
    🔒 mask ชื่อ/HN **เสมอ ไม่มีข้อยกเว้น** (นโยบาย 11 มิ.ย. 2026 · มาตรา 3.6.4):
    ชื่อ = คำนำหน้า+ชื่อต้น+นามสกุลย่อ · HN = 4 ตัวท้าย — ทั้ง Supabase และไฟล์ local
    🔁 optimistic concurrency (CR-2): ใส่ version + merge ราย-เคส ก่อนเขียน —
    ถ้าเครื่องอื่นเขียนแซงหลังเราโหลด จะ merge เฉพาะเคสที่เครื่องนี้แก้ทับบนของล่าสุด
    ไม่ทับทั้งกระดาน (กันงานของเครื่องอื่นหายเงียบ)"""
    try:
        from main_or_db import mask_patient_name, mask_hn
        today = _now().date().isoformat()
        out = []
        for c in cases:
            d = {k: _ser(val) for k, val in c.items()}
            if d.get('name'):
                d['name'] = mask_patient_name(d['name'])
            if d.get('hn'):
                d['hn'] = mask_hn(d['hn'])
            # หมายเหตุ: ชื่อแพทย์ (surgeon) "โชว์จริง" บนบอร์ด — ทีม OR ต้องรู้ว่าใครผ่า
            #   Supabase อยู่หลัง credentials+รหัสแอป (ไม่ใช่สาธารณะ) จึงเก็บได้ตามการใช้งานจริง
            for _nk in ('scrub_nurse', 'circ_nurse'):   # 🔒 พยาบาล: ย่อตามที่ผู้ใช้เลือกไว้
                if d.get(_nk):
                    d[_nk] = _mask_nurse_name(d[_nk])
            d.pop('procnote', None)   # 🔒 free text จาก HIS ไม่ขึ้น cloud (data minimization)
            out.append(d)

        # ---- optimistic concurrency: อ่านสถานะ DB ล่าสุดก่อนเขียน ----
        base_ver = int(st.session_state.get('_board_base_version', 0) or 0)
        dirty_ids = {str(x) for x in st.session_state.get('_board_dirty_ids', set())}
        merged, new_ver = out, base_ver + 1
        try:
            from main_or_db import load_board_state
            _s = load_board_state(today)
            if _s:
                _dbp = json.loads(_s)
                db_ver = int(_dbp.get('version', 0) or 0)
                if _dbp.get('date') == today and db_ver > base_ver:
                    # มีเครื่องอื่นเขียนแซง → merge ราย-เคส (เริ่มจากของ DB ล่าสุด)
                    by_key = {_board_case_key(d): d for d in _dbp.get('cases', [])}
                    overlay_all = not dirty_ids   # งานเป็นชุด (upload) → ของเราชนะ
                    for d in out:
                        k = _board_case_key(d)
                        if overlay_all or str(d.get('id')) in dirty_ids or k not in by_key:
                            by_key[k] = d
                    merged, new_ver = list(by_key.values()), db_ver + 1
                elif db_ver >= base_ver:
                    new_ver = db_ver + 1
        except Exception as _mx:
            print(f"[snapshot] merge ข้าม (เขียนตรง): {_mx}")

        payload = {
            'date': today,
            'pii_kept': False,   # คงคีย์ไว้เข้ากันได้กับ payload เก่า — False เสมอ
            'version': new_ver,
            'saved_at': _now().isoformat(),
            'cases': merged,
        }
        payload_str = json.dumps(payload, ensure_ascii=False, default=str)  # default=str = ตาข่ายกันพัง
        # 🖥️ บอร์ดกลาง: เขียนลง DB (app_settings) → ทุกเครื่อง/ผู้บริหารเห็นชุดเดียวกัน
        _saved = False
        try:
            from main_or_db import save_board_state
            _ok = save_board_state(today, payload_str)
            if _ok:
                _saved = True
                st.session_state['_board_base_version'] = new_ver  # ซิงก์แล้ว = ฐานใหม่
                st.session_state['_board_dirty_ids'] = set()        # ล้างหลังเซฟสำเร็จ
                st.session_state['_board_db_fail'] = 0              # 🔌 M-09: เซฟสำเร็จ → รีเซ็ตตัวนับ
            else:
                # 🔌 M-09: เซฟล้มเหลว (return False) — นับไว้ ไม่เคลม "ซิงก์แล้ว"
                st.session_state['_board_db_fail'] = st.session_state.get('_board_db_fail', 0) + 1
        except Exception as _dx:
            st.session_state['_board_db_fail'] = st.session_state.get('_board_db_fail', 0) + 1
            print(f"[snapshot] DB save ล้มเหลว (ใช้ local แทน): {_dx}")
        # ไฟล์ local = backup + โหมด offline (db_mode=sqlite เครื่องเดียว)
        _os.makedirs(_os.path.dirname(_SNAPSHOT_PATH), exist_ok=True)
        with open(_SNAPSHOT_PATH, 'w', encoding='utf-8') as f:
            f.write(payload_str)
        if not _saved:
            try:
                from db_connection import IS_SQLITE as _is_sqlite
            except Exception:
                _is_sqlite = True
            if _is_sqlite:
                _saved = True   # โหมดเครื่องเดียว: ไฟล์ local = สำเร็จ (ไม่มีบอร์ดกลาง)
        return _saved
    except Exception as _ex:
        print(f"[snapshot] save ล้มเหลว: {_ex}")
        return False


def _load_board_snapshot():
    """โหลด snapshot บอร์ด 'วันนี้' — อ่าน DB (บอร์ดกลาง) ก่อน → fallback ไฟล์ local
    คืน None ถ้าไม่มี/เป็นของวันอื่น (กันกู้ของเมื่อวาน)"""
    _today = _now().date().isoformat()
    try:
        payload = None
        # 🖥️ บอร์ดกลาง: อ่านจาก DB ก่อน (เห็นสถานะที่เครื่องอื่นกดล่าสุด)
        try:
            from main_or_db import load_board_state
            _s = load_board_state(_today)
            if _s:
                payload = json.loads(_s)
        except Exception as _dx:
            print(f"[snapshot] DB load ล้มเหลว: {_dx}")
        # fallback: ไฟล์ local (offline / DB ใช้ไม่ได้)
        if payload is None:
            if not _os.path.exists(_SNAPSHOT_PATH):
                return None
            with open(_SNAPSHOT_PATH, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        if payload.get('date') != _today:
            return None  # ของวันอื่น — อย่ากู้
        try:
            st.session_state['_snap_pii_kept'] = bool(payload.get('pii_kept', False))
            # 🔁 CR-2: จำ version ที่เพิ่งโหลด = ฐานสำหรับ optimistic concurrency ตอนเซฟ
            st.session_state['_board_base_version'] = int(payload.get('version', 0) or 0)
        except Exception:
            pass
        return [{k: _deser(val) for k, val in c.items()}
                for c in payload.get('cases', [])]
    except Exception as _ex:
        print(f"[snapshot] load ล้มเหลว: {_ex}")
        return None


def _or_board_demo():
    """เคสตัวอย่างสำหรับลองใช้ OR Board (ไม่ใช่ข้อมูลจริง)
    🎓 เรียงเฟสจากบนลงล่างตาม workflow จริง — ไว้สอนผู้ใช้ทีละขั้น:
    OR1 ยังไม่มา → OR2 รอผ่าตัด(ฉุกเฉิน+นาฬิการอ) → OR3 กำลังผ่า(เขียว)
    → OR4 ใกล้ครบเวลา(ส้ม) → OR5 เกินเวลา(แดง) → OR6 ห้องรับ-ส่ง
    → OR7 ห้องพักฟื้น → OR8 จำหน่ายแล้ว(เทา) → OR9 นอกเวลา+AI ไม่มีข้อมูล"""
    from datetime import timedelta
    now = _now()

    def C(status, order, h, m, name, hn, age, proc, surg, pred, room, division='1', **extra):
        c = {'status': status, 'ororder': order, 'sched_hour': h, 'sched_min': m,
             'name': name, 'hn': hn, 'age': age, 'procedure': proc, 'surgeon': surg,
             'division': division, 'predicted_min': pred, 'effective_min': pred,
             'ai_predicted_min': pred, 'is_tf': False, '_demo': True, 'room': room,
             'diagnosis': extra.pop('diagnosis', proc)}
        c.update(extra)
        return c

    return [
        # ① OR1 — ยังไม่มา (จุดเริ่ม: เห็นค่า AI + ปุ่ม "รับเข้า")
        C('not_arrived', 1, 8, 30, 'นาย สมชาย ทดสอบ', 'DEMO001', 55, 'EGD',
          'นพ.ซี ทดสอบ', 30, 90, division='1', proc_n=142, confidence='สูงมาก'),
        # ② OR2 — รอผ่าตัด + ⚠️ ฉุกเฉิน (นาฬิการอเดิน + ไฟแดงกะพริบ + ปุ่ม "เข้าห้อง")
        C('holding_pre', 2, 9, 0, 'นาง พรรณี ทดลองใช้', 'DEMO002', 70, 'Appendectomy',
          'นพ.เอ ทดสอบ', 60, 91, division='1',
          time_arrived_holding=now - timedelta(minutes=12),
          is_emergency=True, case_type='Emergency', proc_n=85, confidence='สูง'),
        # ③ OR3 — กำลังผ่า ปกติ (เขียว นาทีเดินเอง — เหลือเวลาอีกเยอะ)
        C('in_or', 3, 9, 30, 'นาย สมศักดิ์ ทดสอบ', 'DEMO003', 62, 'TURP',
          'นพ.ดี ทดสอบ', 90, 92, division='5',
          time_entered_or=now - timedelta(minutes=40), proc_n=47, confidence='สูง'),
        # ④ OR4 — กำลังผ่า ใกล้ครบเวลา (เหลือ ~3 นาที → mm:ss สีส้ม)
        C('in_or', 4, 10, 0, 'นาง มาลี ทดสอบ', 'DEMO004', 51, 'Laparoscopic cholecystectomy',
          'นพ.บี ทดสอบ', 60, 93, division='1',
          time_entered_or=now - timedelta(minutes=57), proc_n=58, confidence='สูง'),
        # ⑤ OR5 — เกินเวลาแล้ว 35 นาที (แดงสด + เด้งแจ้งเตือนระดับสูงหน้าบริหาร
        #    เพราะเกิน 1.5 เท่าของเวลาทำนาย)
        C('in_or', 5, 10, 30, 'นาย ประสิทธิ์ ทดสอบ', 'DEMO005', 65, 'AVF creation',
          'นพ.อี ทดสอบ', 60, 94, division='7',
          time_entered_or=now - timedelta(minutes=95), proc_n=63, confidence='สูง'),
        # ⑥ OR6 — ผ่าเสร็จ → ห้องรับ-ส่ง (ปุ่ม "จำหน่าย")
        C('holding_post', 6, 8, 0, 'นาย วิชัย ทดสอบ', 'DEMO006', 58, 'Craniotomy',
          'นพ.เอฟ ทดสอบ', 180, 95, division='2',
          time_entered_or=now - timedelta(minutes=210),
          time_exited_or=now - timedelta(minutes=25),
          actual_duration_min=185, proc_n=18, confidence='ปานกลาง'),
        # ⑦ OR7 — ผ่าเสร็จ → ห้องพักฟื้น (ปลายทางอีกแบบ)
        C('recovery', 7, 8, 30, 'น.ส. กัญญา ทดลองใช้', 'DEMO007', 33, 'Q-Switch laser',
          'นพ.จี ทดสอบ', 35, 96, division='4',
          time_entered_or=now - timedelta(minutes=120),
          time_exited_or=now - timedelta(minutes=35),
          actual_duration_min=33, proc_n=210, confidence='สูงมาก'),
        # ⑧ OR8 — จำหน่ายแล้ว (แถบเทาจาง — จบ flow)
        C('discharged', 8, 8, 0, 'ด.ช. ภูมิ ทดสอบ', 'DEMO008', 12, 'Tonsillectomy',
          'นพ.เอช ทดสอบ', 45, 97, division='3',
          time_entered_or=now - timedelta(minutes=180),
          time_exited_or=now - timedelta(minutes=95),
          time_discharged=now - timedelta(minutes=10),
          actual_duration_min=42, proc_n=31, confidence='สูง'),
        # ⑨ OR9 — โบนัส: เคสนอกเวลา + หัตถการที่ AI ไม่มีประวัติ (สอนเรื่อง ✏️ override)
        C('not_arrived', 9, 18, 30, 'น.ส. อรอุมา ทดสอบ', 'DEMO009', 48,
          'Open cholecystectomy', 'นพ.บี ทดสอบ', 90, 98, division='9',
          proc_n=0, confidence='ต่ำ'),
    ]


_CUT_MIN = 15 * 60 + 30   # 15:30 = นาทีจากเที่ยงคืน


def _sched_min(c):
    h = c.get('sched_hour')
    return (h * 60 + (c.get('sched_min', 0) or 0)) if h is not None else None


def _case_end_min(c):
    """เวลาที่เคส 'จบ' (นาที) — ใช้เวลาจริงถ้ามี ไม่งั้นประเมินจาก sched + predicted
    เคส TF (ไม่ระบุเวลา — sched เป็น placeholder 23:55): ประเมินจากเวลาเข้าห้องจริง
    ถ้ายังไม่เข้าห้องถือว่ายังไม่รู้ → คืน 0 (ไม่นับเป็นรับเวรล่วงหน้า)"""
    for k in ('time_discharged', 'time_exited_or'):
        ts = c.get(k)
        if ts is not None and hasattr(ts, 'hour'):
            return ts.hour * 60 + ts.minute
    pred = int(c.get('effective_min') or c.get('predicted_min') or 60)
    if c.get('is_tf'):
        ent = c.get('time_entered_or')
        if ent is not None and hasattr(ent, 'hour'):
            return min(ent.hour * 60 + ent.minute + pred, 23 * 60 + 59)
        return 0  # TF ที่ยังไม่เริ่ม — เวลาไม่รู้จริง อย่าใช้ placeholder 23:55
    sh = c.get('sched_hour', 8) or 8
    sm = c.get('sched_min', 0) or 0
    return min(sh * 60 + sm + pred, 23 * 60 + 59)


def case_shift_class(c):
    """จัดประเภทเคส → 'นอกเวลา' / 'รับเวร' / 'ในเวลา' (3 กลุ่มไม่ทับกัน)
    - นอกเวลา: procnote ระบุ 'นอกเวลา' หรือ เวลานัดจริง >= 15:30
                (เคส TF ไม่นับ — 23:55 เป็นแค่ placeholder เรียงท้ายคิว)
    - รับเวร : ไม่ใช่นอกเวลา + ยังไม่เสร็จ/จบหลัง 15:30
    - ในเวลา : ที่เหลือ
    """
    sm = _sched_min(c)
    if c.get('is_after_note') or (not c.get('is_tf')
                                  and sm is not None and sm >= _CUT_MIN):
        return 'นอกเวลา'
    if _case_end_min(c) >= _CUT_MIN:
        return 'รับเวร'
    return 'ในเวลา'


# 🔐 PIN ปลดล็อกอัปโหลด CSV (เฉพาะผู้ดูแล) — อ่านจาก st.secrets['admin_pin']
# (เดิม hardcode ในโค้ด = ใครอ่านซอร์สบน GitHub ก็ปลดล็อกได้ — ย้ายเข้า secrets แล้ว)
from main_or_db import get_admin_pin as _get_admin_pin


def _enabled_room_options():
    """คืน [(room_no, ชื่อห้อง)] เฉพาะห้องที่เปิดใช้ (ไม่ถูกปิดในหน้าตั้งค่า)
    — ชื่อล้วน ไม่มีรหัสห้อง · ห้องที่ไม่มีใน settings = ถือว่าเปิด (default)"""
    from room_config import NEW_BUILDING_ROOMS, room_label
    try:
        from main_or_db import load_room_settings
        settings = load_room_settings()
    except Exception:
        settings = {}
    opts = []
    for r in NEW_BUILDING_ROOMS:
        s = settings.get(r)
        if s is None or s.get('enabled', True):
            opts.append((r, room_label(r)))
    return opts or [(r, room_label(r)) for r in NEW_BUILDING_ROOMS]

# สาขา (code → ชื่อ) สำหรับ dropdown ฟอร์มเพิ่มเคส — ตรงกับ DIV_CODE_MAP
_DIV_OPTIONS = [
    ('1', 'ศัลยกรรมทั่วไป'), ('2', 'ศัลยกรรมประสาทและสมอง'),
    ('3', 'ศัลยกรรมหู คอ จมูก'), ('4', 'ศัลยกรรมตกแต่ง'),
    ('5', 'ศัลยกรรมระบบทางเดินปัสสาวะ'), ('6', 'ศัลยกรรมลำไส้ใหญ่และทวารหนัก'),
    ('7', 'ศัลยกรรมหลอดเลือด'), ('8', 'ศัลยกรรมทรวงอก'),
    ('9', 'ศัลยกรรมตับ ตับอ่อน ทางเดินน้ำดี'), ('10', 'ปลูกถ่ายอวัยวะ'),
    ('41', 'ศัลยกรรมโรคหัวใจ'), ('71', 'ศัลยกรรมเด็ก'),
]


def _render_add_case_form(demo_active):
    """ฟอร์มเพิ่มเคส walk-in/แทรก — กรอกเฉพาะข้อมูลที่โมเดลใช้ แล้วทำนายเวลา เข้าบอร์ด"""
    import uuid
    if demo_active:
        st.caption("ℹ️ ปิด 🎬 Demo Mode ด้านบนก่อน เพื่อเพิ่มเคสจริง")
        return
    _room_opts = _enabled_room_options()  # เฉพาะห้องที่เปิดใช้ · ชื่อล้วน
    st.caption("กรอกเฉพาะข้อมูลที่จำเป็น — ช่องที่มี 🤖 คือข้อมูลที่ AI ใช้ทำนายเวลา "
               "(ระบบจับคู่ชื่อหัตถการ/แพทย์ใกล้เคียงให้อัตโนมัติ)")

    c1, c2 = st.columns(2)
    name = c1.text_input("ชื่อ-สกุล", key="ac_name", placeholder="ชื่อผู้ป่วย")
    age = c2.number_input("🤖 อายุ (ปี)", min_value=0, max_value=120, value=50,
                          step=1, key="ac_age")
    proc = st.text_input("🤖 หัตถการ (ICD-9) *", key="ac_proc",
                         placeholder="เช่น Laparoscopic cholecystectomy")
    diag = st.text_input("🤖 วินิจฉัย (ICD-10)", key="ac_diag",
                         placeholder="เช่น Cholelithiasis")
    c3, c4 = st.columns(2)
    surg = c3.text_input("🤖 แพทย์ผ่าตัด", key="ac_surg", placeholder="ชื่อแพทย์")
    _div_label = c4.selectbox("🤖 สาขา", [d[1] for d in _DIV_OPTIONS],
                              key="ac_div")
    c5, c6 = st.columns(2)
    _room_label = c5.selectbox("🤖 ห้อง", [lbl for _, lbl in _room_opts],
                               key="ac_room")
    from datetime import time as _time
    _sched = c6.time_input("🤖 เวลานัด", value=_time(9, 0), key="ac_time")
    ce1, ce2 = st.columns(2)
    _no_time = ce1.checkbox("ไม่ระบุเวลา (เคส TF — เรียงท้ายคิว)", key="ac_tf")
    is_emer = ce2.checkbox("🔴 เคสฉุกเฉิน (ติดไฟแดงบนบอร์ด)", key="ac_emer")
    if _no_time:
        _sched = None

    cbtn1, cbtn2 = st.columns([3, 1])
    if cbtn1.button("🤖 เพิ่มเคส + ทำนายเวลา", type="primary", width='stretch',
                    key="ac_submit"):
        if not (proc or '').strip():
            st.error("กรุณากรอก 'หัตถการ' (ช่องบังคับ)")
            return
        _div_code = next((d[0] for d in _DIV_OPTIONS if d[1] == _div_label), '75')
        _room_no = next((rn for rn, lbl in _room_opts if lbl == _room_label),
                        _room_opts[0][0])
        if _sched is not None:
            sched_h, sched_m, is_tf = _sched.hour, _sched.minute, False
        else:
            sched_h, sched_m, is_tf = 23, 55, True  # ไม่ระบุเวลา = TF (เรียงท้าย)
        # ทำนายเวลาด้วยโมเดล (ส่งข้อมูลครบที่กรอก)
        try:
            from main_or_core import predict_surgical_time
            _pred = predict_surgical_time(
                procedure=proc.strip().upper(), age=int(age),
                surgeon=(surg or '').strip(), division=str(_div_code),
                op_hour=sched_h if sched_h < 23 else 9,
                op_date=_now(), orroom=int(_room_no),
                diagnosis=(diag or '').strip())
            _pm = int(_pred.get('predicted_min') or 60)
            _conf = _pred.get('confidence')
            _pn = _pred.get('proc_n', 0)
            _rng = _pred.get('predicted_range')
            _rngm = _pred.get('range_method')
        except Exception as _ex:
            print(f"[add_case] predict ล้มเหลว: {_ex}")
            _pm, _conf, _pn, _rng, _rngm = 60, 'ต่ำ', 0, None, None
        case = {
            'id': f"MANUAL_{uuid.uuid4().hex[:8]}",
            'hn': '', 'name': (name or '').strip() or 'ไม่ระบุ',
            'age': int(age), 'diagnosis': (diag or '').strip() or '-',
            'procedure': proc.strip().upper(), 'anesthesia': '-',
            'surgeon': (surg or '').strip(), 'room': _room_no,
            'division': str(_div_code), 'ororder': 99,
            'case_type': 'Emergency' if is_emer else 'Elective',
            'is_emergency': is_emer, 'ward': '',
            'sched_date': _now().date(), 'sched_hour': sched_h,
            'sched_min': sched_m, 'is_tf': is_tf, 'is_after_note': False,
            'procnote': '', 'predicted_min': _pm, 'confidence': _conf,
            'proc_n': _pn,
            'predicted_range': _rng, 'range_method': _rngm,   # 📏 ช่วง conformal 90%
            'status': 'not_arrived', 'ai_predicted_min': _pm,
            'user_override_min': None, 'effective_min': _pm,
            'or_room_assigned': _room_no,
            'time_arrived_holding': None, 'time_entered_or': None,
            'time_exited_or': None, 'time_discharged': None,
            'actual_duration_min': None,
        }
        _cur = list(st.session_state.patient_cases)
        _cur.append(case)
        st.session_state.patient_cases = _cur
        st.session_state['_or_demo'] = False
        _mark_board_dirty(case)   # CR-2: เพิ่มเคสใหม่ → ดันขึ้นบอร์ดกลาง
        _rng_txt = (f" · ช่วง 90%: {int(_rng[0])}–{int(_rng[1])} นาที"
                    if (_rngm == 'conformal' and _rng) else "")
        from main_or_db import mask_patient_name as _mpn
        st.success(f"✅ เพิ่มเคส '{_mpn(case['name'])}' แล้ว — AI ทำนาย {_pm} นาที "
                   f"(based on {_pn} เคส){_rng_txt}")
        st.rerun()
    if cbtn2.button("ล้างฟอร์ม", key="ac_clear", width='stretch'):
        for _k in ('ac_name', 'ac_proc', 'ac_diag', 'ac_surg'):
            st.session_state.pop(_k, None)
        st.rerun()


def render_csv_upload():
    """📤 อัปโหลดตารางผ่าตัด (CSV) — ล็อก PIN · ย้ายมาหน้า ⚙️ ตั้งค่า (เดิมอยู่บนบอร์ด)"""
    _demo_active = bool(st.session_state.get('_or_demo'))
    with st.expander("📤 อัปโหลดตารางผ่าตัดวันนี้ (CSV) 🔒", expanded=False):
        if _demo_active:
            st.caption("ℹ️ ปิด 🎬 Demo Mode ในหน้าตารางผ่าตัดก่อน เพื่ออัปโหลดตารางจริง")
        if not st.session_state.get('_upload_unlocked'):
            _pin_cfg = _get_admin_pin()
            if not _pin_cfg:
                st.caption("🔒 ปิดการอัปโหลดไว้ — ผู้ดูแลยังไม่ได้ตั้งรหัส PIN "
                           "(เพิ่ม `admin_pin = \"...\"` ใน secrets แล้ว reboot)")
            else:
                st.caption("🔒 เฉพาะผู้ดูแล (Mukky) — ใส่รหัส PIN เพื่อปลดล็อกการอัปโหลด")
                _up1, _up2 = st.columns([3, 1])
                _upin = _up1.text_input("PIN", type="password", key="upload_pin",
                                        placeholder="กรอก PIN",
                                        label_visibility="collapsed")
                if _up2.button("🔓 ปลดล็อก", key="upload_unlock", width='stretch'):
                    if (_upin or '').strip() == _pin_cfg:
                        st.session_state['_upload_unlocked'] = True
                        st.rerun()
                    else:
                        st.error("PIN ไม่ถูกต้อง")
        else:
            _up = st.file_uploader("เลือกไฟล์ CSV ตารางผ่าตัด (HIS)", type=["csv"],
                                   key="orboard_csv", disabled=_demo_active)
            _rep = st.checkbox("แทนที่เคส 'ยังไม่มา' เดิม (กันซ้ำ)", value=True,
                               key="orboard_rep", disabled=_demo_active)
            if _up is not None and not _demo_active and st.button(
                    "✅ โหลดเข้าบอร์ด + ทำนายเวลา",
                    type="primary", width='stretch', key="orboard_load"):
                with st.spinner("กำลังอ่านไฟล์ + ทำนายเวลา..."):
                    try:
                        from main_or_app import parse_schedule_csv_to_cases
                        _new = parse_schedule_csv_to_cases(_up)
                    except Exception as _ex:
                        _new = []
                        st.error(f"อ่านไฟล์ไม่สำเร็จ: {_ex}")
                if not _new:
                    st.warning("ไม่พบเคสในไฟล์ — ลองตรวจหัวคอลัมน์ (hn/ชื่อ/หัตถการ/เวลา/ห้อง)")
                else:
                    _cur = list(st.session_state.patient_cases)
                    if _rep:
                        _cur = [c for c in _cur if c.get('status') != 'not_arrived']
                    _seen_hn = {c.get('hn') for c in _cur if c.get('hn')}
                    _added = 0
                    for _nc in _new:
                        if _nc.get('hn') and _nc['hn'] in _seen_hn:
                            continue
                        _cur.append(_nc)
                        _added += 1
                    st.session_state.patient_cases = _cur
                    st.session_state['_or_demo'] = False
                    st.session_state['_board_dirty'] = True   # CR-2: โหลดตารางใหม่ → ดันขึ้นบอร์ดกลาง
                    st.success(f"✅ โหลด {_added} เคสเข้าบอร์ดแล้ว — ไปดูที่หน้า 📋 ตารางผ่าตัด")
                    st.rerun()


def render_clear_board():
    """🗑️ ล้างกระดานวันนี้ (สำหรับลบเคสทดสอบ) — ย้ายมาหน้า ⚙️ ตั้งค่า (เดิมอยู่บนบอร์ด)"""
    with st.expander("🗑️ ล้างกระดานวันนี้ (สำหรับลบเคสทดสอบ) 🔒", expanded=False):
        if not st.session_state.get('_clear_unlocked'):
            _pin_cfg = _get_admin_pin()
            if not _pin_cfg:
                st.caption("🔒 ปิดการล้างกระดานไว้ — ผู้ดูแลยังไม่ได้ตั้งรหัส PIN "
                           "(เพิ่ม `admin_pin = \"...\"` ใน secrets แล้ว reboot)")
            else:
                st.caption("🔒 เฉพาะผู้ดูแล (Mukky) — ใส่รหัส PIN เพื่อปลดล็อกการล้างกระดาน")
                _cp1, _cp2 = st.columns([3, 1])
                _cpin = _cp1.text_input("PIN", type="password", key="clear_pin",
                                        placeholder="กรอก PIN",
                                        label_visibility="collapsed")
                if _cp2.button("🔓 ปลดล็อก", key="clear_unlock", width='stretch'):
                    if (_cpin or '').strip() == _pin_cfg:
                        st.session_state['_clear_unlocked'] = True
                        st.rerun()
                    else:
                        st.error("PIN ไม่ถูกต้อง")
            return
        st.caption("ลบเคสทั้งหมดของวันนี้ออกจากบอร์ด + บอร์ดกลาง (ทุกเครื่อง) — "
                   "ใช้เคลียร์ข้อมูลทดสอบ · ไม่กระทบสถิติย้อนหลัง/ฐานข้อมูลเคสที่ import")
        _ok_clear = st.checkbox("ยืนยันต้องการล้างกระดานวันนี้", key="orb_clear_ok")
        if st.button("🗑️ ล้างกระดานวันนี้", type="secondary", width='stretch',
                     disabled=not _ok_clear, key="orb_clear_btn"):
            st.session_state.patient_cases = []
            st.session_state['_or_demo'] = False
            st.session_state['_board_dirty'] = False          # ล้างแล้ว ไม่มีอะไรต้องเซฟ
            st.session_state['_board_dirty_ids'] = set()
            st.session_state['_board_was_restored'] = False
            _td = _now().date().isoformat()
            # 🧹 ล้างข้ามเครื่อง: เขียน payload "ว่าง" version+1 แทนการลบ key —
            #    ลบ key เฉยๆ เครื่องอื่นจะ fallback ไฟล์ local ตัวเอง แล้วเซฟเคสกลับมา
            #    (เคสผีคืนชีพ) · payload ว่างทำให้ทุกเครื่อง pull แล้วเห็นกระดานว่างจริง
            try:
                from main_or_db import load_board_state, save_board_state
                _ver = 0
                try:
                    _s0 = load_board_state(_td)
                    if _s0:
                        _ver = int(json.loads(_s0).get('version', 0) or 0)
                except Exception:
                    pass
                _empty = json.dumps(
                    {'date': _td, 'pii_kept': False, 'version': _ver + 1,
                     'saved_at': _now().isoformat(), 'cleared': True, 'cases': []},
                    ensure_ascii=False)
                save_board_state(_td, _empty)
                st.session_state['_board_base_version'] = _ver + 1
            except Exception as _ex:
                st.session_state['_board_base_version'] = 0
                print(f"[clear_board] DB ล้มเหลว: {_ex}")
            try:                                              # ลบไฟล์ snapshot local ด้วย
                if _os.path.exists(_SNAPSHOT_PATH):
                    _os.remove(_SNAPSHOT_PATH)
            except Exception:
                pass
            st.success("✅ ล้างกระดานวันนี้แล้ว (ทุกเครื่อง)")
            st.rerun()


def page_or_board():
    from main_or_db import div_name
    from room_config import room_label

    def _rid(c):
        """หมายเลขห้องจริง (90-97) หรือ None ถ้าไม่ระบุ/placeholder"""
        try:
            r = int(float(c.get('room')))
        except (TypeError, ValueError):
            return None
        return r if r and r != 1 else None

    def _loc(c):
        r = _rid(c)
        return room_label(r) if r else div_name(c.get('division', ''))

    def _tlabel(c):
        if c.get('is_tf'):
            return 'TF'
        return f'{c.get("sched_hour",8):02d}:{c.get("sched_min",0):02d}'

    cases = st.session_state.patient_cases

    # 🖥️ บอร์ดกลาง (shared ผ่าน DB) + auto-refresh ทุก ~30 วิ
    # ทุกเครื่อง/ผู้บริหารดึงสถานะล่าสุดเมื่อ: เปิดครั้งแรก · กด 🔄 · ครบรอบ refresh
    # ไม่ดึงตอน "เพิ่งกดปุ่มบนเครื่องตัวเอง" (กันทับการเปลี่ยนที่ยังไม่ได้ save)
    if not st.session_state.get('_or_demo'):
        # 🕛 M-10: ข้ามเที่ยงคืน → ล้างเคส "เมื่อวาน" + บังคับดึงบอร์ดของ "วันนี้"
        #          (กันเคสเก่าถูกเซฟทับด้วย key วันใหม่ → เช้ามาเห็นเคสเมื่อวานปนบอร์ด)
        _today_iso = _now().date().isoformat()
        if st.session_state.get('_board_last_date') not in (None, _today_iso):
            st.session_state.patient_cases = []
            cases = []
            st.session_state['_board_dirty'] = False
            st.session_state['_board_dirty_ids'] = set()
            st.session_state['_board_base_version'] = 0
            st.session_state['_board_force_pull'] = True
            st.session_state['_board_restored'] = False
            st.session_state['_board_was_restored'] = False
        st.session_state['_board_last_date'] = _today_iso
        try:
            from streamlit_autorefresh import st_autorefresh
            _tick = st_autorefresh(interval=30000, key='_board_live')
            if _tick != st.session_state.get('_board_tick_seen'):
                st.session_state['_board_tick_seen'] = _tick
                st.session_state['_board_force_pull'] = True
        except Exception:
            pass
        _pull = st.session_state.pop('_board_force_pull', False)
        if not cases and not st.session_state.get('_board_restored'):
            _pull = True
        st.session_state['_board_restored'] = True
        # 🚫 CR-2: ถ้าเครื่องนี้เพิ่งแก้แต่ยังไม่ได้เซฟ → อย่าดึงทับ (กันงานตัวเองหาย)
        #         เซฟท้ายหน้าจะ merge ขึ้น DB เอง แล้วรอบหน้าค่อยดึงผลรวมกลับมา
        if _pull and not st.session_state.get('_board_dirty'):
            _shared = _load_board_snapshot()
            if _shared is not None:
                st.session_state.patient_cases = _shared
                cases = _shared
                st.session_state['_board_was_restored'] = True
    if cases and st.session_state.get('_board_db_fail', 0) > 2:
        # 🔌 M-09: เซฟขึ้น DB กลางล้มเหลวติดกัน → บอกตรงๆ ว่าออฟไลน์ (ไม่โกหกว่า "ซิงก์แล้ว")
        st.warning("⚠️ บอร์ดกลางออฟไลน์ — เครื่องนี้ยังไม่ได้แชร์ขึ้นเซิร์ฟเวอร์ "
                   "(บันทึกไว้ในเครื่องชั่วคราว) · ตรวจการเชื่อมต่อแล้วกด 🔄 รีเฟรช")
    # (เอา caption "บอร์ดกลาง — ซิงก์ทุกเครื่อง" ออกเพื่อเพิ่มพื้นที่ — สถานะซิงก์โชว์เป็นชิปบนหัวแล้ว)

    # (วันที่/เวลาปรับล่าสุด ย้ายไปเป็นชิปบนแถบหัวแล้ว — board เริ่มที่แถวควบคุมเลย)

    # ---------- แถวควบคุม: Demo Mode + ปุ่มรีเฟรช (มุมขวา) ----------
    _ctl_l, _ctl_warn, _ctl_r = st.columns([3, 1.5, 1], vertical_alignment="center")
    with _ctl_r:
        if st.button("🔄 รีเฟรช", key="orboard_refresh", width='stretch',
                     type='primary',
                     help="ดึงสถานะล่าสุดจากบอร์ดกลาง (เห็นที่เครื่องอื่นกด)"):
            st.session_state['_board_force_pull'] = True   # บังคับดึงจาก DB กลาง
            st.rerun()
    with _ctl_warn:
        st.caption("⚠️ อย่ากด F5 — ใช้ปุ่มนี้แทน")
    with _ctl_l:
        _demo_on = st.toggle(
            "🎬 Demo Mode", key="orboard_demo_toggle",
            help="เปิด: โหลดเคสตัวอย่างมาลองใช้บอร์ด (ไม่ใช่ข้อมูลจริง) · ปิด: ล้างตัวอย่าง")
    if _demo_on and not st.session_state.get('_or_demo'):
        st.session_state.patient_cases = _or_board_demo()
        st.session_state['_or_demo'] = True
        st.rerun()
    if (not _demo_on) and st.session_state.get('_or_demo'):
        st.session_state.patient_cases = []
        st.session_state['_or_demo'] = False
        st.rerun()
    if st.session_state.get('_or_demo'):
        st.caption("🧪 กำลังแสดง **ข้อมูลตัวอย่าง (Demo)** — ไม่ใช่เคสจริง")

    _demo_active = bool(st.session_state.get('_or_demo'))

    # 💡 คำอธิบายปุ่มดินสอบนการ์ดเคส
    st.caption("✏️ กดปุ่ม **ดินสอ (✏️)** ที่แต่ละเคส เพื่อแก้เวลาคาดการณ์ใช้ห้อง หรือ ย้ายห้อง")

    # ---------- ➕ เพิ่มเคส (Manual) — ทุกคนเพิ่มได้ ----------
    #    (📤 อัปโหลด CSV + 🗑️ ล้างกระดานวันนี้ ย้ายไปหน้า ⚙️ ตั้งค่า แล้ว —
    #     เรียก render_csv_upload()/render_clear_board() จาก page_room_settings)
    with st.expander("➕ เพิ่มเคส (Manual)", expanded=False):
        _render_add_case_form(_demo_active)

    # ---------- empty state ----------
    if not cases:
        st.info("ยังไม่มีผู้ป่วย — เปิด '🎬 Demo Mode' ด้านบนเพื่อลองใช้ "
                "หรือกด '📤 อัปโหลดตารางผ่าตัดวันนี้ (CSV)'")
        return

    # ---------- counters ----------
    n_not = sum(1 for c in cases if c['status'] == 'not_arrived')
    n_hold = sum(1 for c in cases if c['status'] == 'holding_pre')
    n_inor = sum(1 for c in cases if c['status'] == 'in_or')
    n_post = sum(1 for c in cases if c['status'] in ('holding_post', 'recovery'))
    n_done = sum(1 for c in cases if c['status'] == 'discharged')

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("⬜ ยังไม่มา", n_not)
    m2.metric("🟡 รอผ่าตัด", n_hold)
    m3.metric("🔵 ในห้องผ่าตัด", n_inor)
    m4.metric("🚪 รอจำหน่าย", n_post)
    m5.metric("✅ จำหน่าย", n_done)

    # ---------- action handlers ----------
    # (มี guard กันกดรัว/กดซ้ำ — ถ้าสถานะเปลี่ยนไปแล้วจากคลิกก่อนหน้า ไม่ทำซ้ำ)
    def _do_arrive(idx):
        if cases[idx].get('status') != 'not_arrived':
            return  # กดซ้ำ/สถานะเปลี่ยนแล้ว — ไม่ทำซ้ำ
        cases[idx]['status'] = 'holding_pre'
        cases[idx]['time_arrived_holding'] = _now()
        _mark_board_dirty(cases[idx])   # CR-2: เครื่องนี้แก้จริง → ค่อยเซฟ + กันถูกดึงทับ
        st.rerun()

    def _do_enter(idx, R):
        if cases[idx].get('status') != 'holding_pre':
            return  # กันกดรัว
        # 🚫 กันเข้าห้องที่ถูก "ปิด" ในหน้าตั้งค่า — เคสที่ schedule ผูกห้องปิดมา ก็เข้าไม่ได้
        if R and R not in {_r for _r, _ in _enabled_room_options()}:
            st.warning(f"ห้อง {_loc(cases[idx])} ถูกปิดอยู่ (ตั้งค่า) — "
                       f"เปิดใช้งานห้องในหน้า ⚙️ ตั้งค่า ก่อน หรือเลือกห้องอื่น")
            return
        # 🚫 defense-in-depth: กันห้องซ้ำแม้ปุ่มจะ guard อยู่แล้ว (เผื่อเรียกตรง)
        if R and any(_c.get('status') == 'in_or' and _rid(_c) == R
                     for _c in cases):
            st.warning(f"ห้อง {_loc(cases[idx])} มีเคสกำลังผ่าอยู่ — เข้าห้องไม่ได้")
            return
        now = _now()
        cases[idx]['status'] = 'in_or'
        cases[idx]['or_room_assigned'] = R
        cases[idx]['time_entered_or'] = now
        _rk = R if R else 1
        _rm = st.session_state.or_rooms.setdefault(_rk, {
            'status': 'ว่าง', 'current_case': None, 'start_time': None,
            'predicted_time': None, 'override_time': None, 'is_emergency': False,
            'staff': {'scrub': '', 'circulating': ''},
            'name': room_label(R) if R else 'OR', 'specialty': ''})
        _rm['status'] = 'กำลังผ่าตัด'
        _rm['current_case'] = cases[idx]
        _rm['start_time'] = now
        _rm['predicted_time'] = cases[idx].get('effective_min', 30)
        st.session_state.statistics['total_cases'] += 1
        _mark_board_dirty(cases[idx])   # CR-2
        st.rerun()

    def _do_finish(idx, R, dest):
        if cases[idx].get('status') != 'in_or':
            return  # กันกดรัว (สถานะแสดงผลอาจเป็น 'เกินเวลา' แต่ค่าจริงคือ in_or)
        now = _now()
        cases[idx]['time_exited_or'] = now
        if cases[idx].get('time_entered_or'):
            _dur = (now - cases[idx]['time_entered_or']).total_seconds() / 60
            # กันเวลาติดลบ (เผื่อ clock เครื่องเพี้ยน) — clamp ขั้นต่ำ 1 นาที
            cases[idx]['actual_duration_min'] = max(int(_dur), 1)
        cases[idx]['status'] = 'recovery' if dest == 'ห้องพักฟื้น' else 'holding_post'
        _rk = R if R else 1
        st.session_state.or_rooms.setdefault(_rk, {}).update(
            {'status': 'ว่าง', 'current_case': None, 'start_time': None})
        st.session_state.statistics['completed_cases'] += 1
        record = {
            'timestamp': now.isoformat(),
            'case_id': cases[idx].get('id'),
            'procedure': cases[idx].get('procedure'),
            'surgeon': cases[idx].get('surgeon'),
            'division': cases[idx].get('division', '75'),
            'age': cases[idx].get('age'),
            'op_hour': cases[idx].get('op_hour'),
            'scrub': cases[idx].get('scrub_nurse', ''),
            'circ': cases[idx].get('circ_nurse', ''),
            'ai_predicted_min': cases[idx].get('ai_predicted_min', cases[idx].get('predicted_min')),
            'user_override_min': cases[idx].get('user_override_min'),
            'actual_duration_min': cases[idx].get('actual_duration_min'),
            'wait_min': cases[idx].get('wait_min', 0),
            'room': R if R else 1,
        }
        st.session_state.statistics['case_history'].append(record)
        # 🧪 เคส Demo ไม่บันทึกลงไฟล์สถิติสะสม — กันข้อมูลทดลองปนผลวิจัย
        if not cases[idx].get('_demo'):
            try:
                from main_or_core import append_case_history
                append_case_history(record)
            except Exception as ex:
                st.warning(f"บันทึก history ไม่สำเร็จ: {ex}")
        # เติมเวลาจริงเข้า override_log (ถ้าเคสนี้เคยถูกแก้เวลา) — เทียบ คน vs AI
        try:
            from main_or_db import complete_override
            complete_override(cases[idx], cases[idx].get('actual_duration_min'))
        except Exception as _ex:
            print(f"[override_log] complete_override ล้มเหลว: {_ex}")
        _mark_board_dirty(cases[idx])   # CR-2
        st.rerun()

    def _do_undo(idx):
        """ย้อนสถานะกลับหนึ่งขั้น (กันกดพลาด) — คืนค่าตัวนับ/ห้อง/history ให้ถูก."""
        c = cases[idx]
        s = c['status']
        if s == 'holding_pre':
            c['status'] = 'not_arrived'
            c['time_arrived_holding'] = None
        elif s == 'in_or':
            c['status'] = 'holding_pre'
            c['time_entered_or'] = None
            _rk = c.get('or_room_assigned') or 1
            st.session_state.or_rooms.setdefault(_rk, {}).update(
                {'status': 'ว่าง', 'current_case': None, 'start_time': None})
            st.session_state.statistics['total_cases'] = max(
                st.session_state.statistics['total_cases'] - 1, 0)
        elif s in ('holding_post', 'recovery'):
            c['status'] = 'in_or'
            c['time_exited_or'] = None
            c['actual_duration_min'] = None
            st.session_state.statistics['completed_cases'] = max(
                st.session_state.statistics['completed_cases'] - 1, 0)
            _rk = c.get('or_room_assigned') or 1
            st.session_state.or_rooms.setdefault(_rk, {}).update(
                {'status': 'กำลังผ่าตัด', 'current_case': c,
                 'start_time': c.get('time_entered_or')})
            _hist = st.session_state.statistics.get('case_history', [])
            for _i in range(len(_hist) - 1, -1, -1):
                if (_hist[_i].get('case_id') == c.get('id')
                        and _hist[_i].get('procedure') == c.get('procedure')):
                    _hist.pop(_i)
                    break
            # ลบแถวที่เพิ่งบันทึกออกจากไฟล์ CSV history ด้วย (สถิติ Top-N ไม่เพี้ยน)
            try:
                from main_or_core import remove_last_case_history
                remove_last_case_history(c.get('id'), c.get('procedure'))
            except Exception as _ex:
                print(f"[history] remove_last_case_history ล้มเหลว: {_ex}")
            # ล้างเวลาจริงใน override_log ด้วย — เคสกลับไปกำลังผ่า
            # (กัน 'ผ่าเสร็จ' ผิด → undo → เสร็จใหม่ แล้วเวลาเก่าค้างใน log)
            try:
                from main_or_db import reset_override_actual
                reset_override_actual(c)
            except Exception as _ex:
                print(f"[override_log] reset_override_actual ล้มเหลว: {_ex}")
        elif s == 'discharged':
            c['status'] = 'holding_post'
            c['time_discharged'] = None
        _mark_board_dirty(c)   # CR-2
        st.rerun()

    # ---------- กระดานติดตาม (production tracking board) ----------
    from tracking_board import render_tracking_board
    render_tracking_board(cases, _do_arrive, _do_enter, _do_finish, _do_undo,
                          _loc, _rid, _tlabel, _sched_min,
                          room_opts=_enabled_room_options(),
                          mark_dirty=_mark_board_dirty)

    # 💾 บันทึก snapshot บอร์ดปัจจุบัน — เฉพาะตอน "เครื่องนี้เพิ่งแก้จริง" (CR-2)
    #    เลิกเซฟทุก rerun แล้ว → กัน rerun เฉย ๆ (เปิด popover/refresh) เขียนทับเครื่องอื่น
    if (cases and not st.session_state.get('_or_demo')
            and st.session_state.get('_board_dirty')):
        if _save_board_snapshot(cases):
            st.session_state['_board_dirty'] = False   # เซฟสำเร็จ = สะอาด รอบหน้าดึงผลรวมได้
        # เซฟล้ม → คง dirty ไว้: (1) กัน pull ทับงานที่ยังไม่ขึ้น DB (บรรทัด 495)
        # (2) rerun หน้า/tick หน้า จะ retry เซฟเองอัตโนมัติ · เตือนผู้ใช้เมื่อล้มติดกัน >2 (M-09)


# ============================================================================
# STATISTICS PAGE
# ============================================================================

def page_statistics():
    st.markdown('<h1 style="color:#2c3e50;font-size:28px;font-weight:700;">📊 สถิติและรายงาน</h1>', unsafe_allow_html=True)

    st.markdown('<h3 style="color:#34495e;font-size:18px;font-weight:600;">📈 สรุปรายวัน</h3>', unsafe_allow_html=True)
    tc = st.session_state.statistics['total_cases']
    cc = st.session_state.statistics['completed_cases']
    xc = st.session_state.statistics['cancelled_cases']

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div style="background:white;border-radius:12px;padding:15px;box-shadow:0 2px 4px rgba(0,0,0,0.1);text-align:center;"><div style="color:#7f8c8d;font-size:14px;font-weight:600;">เคสทั้งหมด</div><div style="color:#2c3e50;font-size:32px;font-weight:bold;">{tc}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div style="background:white;border-radius:12px;padding:15px;box-shadow:0 2px 4px rgba(0,0,0,0.1);text-align:center;"><div style="color:#7f8c8d;font-size:14px;font-weight:600;">เสร็จแล้ว</div><div style="color:#27ae60;font-size:32px;font-weight:bold;">{cc}</div></div>', unsafe_allow_html=True)
    with c3:
        rate = round((cc / tc * 100) if tc > 0 else 0)
        st.markdown(f'<div style="background:white;border-radius:12px;padding:15px;box-shadow:0 2px 4px rgba(0,0,0,0.1);text-align:center;"><div style="color:#7f8c8d;font-size:14px;font-weight:600;">อัตราสำเร็จ</div><div style="color:#2c3e50;font-size:32px;font-weight:bold;">{rate}%</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div style="background:white;border-radius:12px;padding:15px;box-shadow:0 2px 4px rgba(0,0,0,0.1);text-align:center;"><div style="color:#7f8c8d;font-size:14px;font-weight:600;">ยกเลิก</div><div style="color:#e74c3c;font-size:32px;font-weight:bold;">{xc}</div></div>', unsafe_allow_html=True)

    # AI vs Actual chart
    st.markdown('<h3 style="color:#34495e;font-size:18px;font-weight:600;margin-top:20px;">🤖 AI ทำนายเวลาใช้ห้อง vs เวลาจริง</h3>', unsafe_allow_html=True)
    history = st.session_state.statistics.get('case_history', [])
    hist = [h for h in history if h.get('actual_duration_min') and h.get('ai_predicted_min')]

    if hist:
        df_h = pd.DataFrame(hist)
        df_h['proc_short'] = df_h['procedure'].str[:40]
        df_h['error'] = df_h['actual_duration_min'] - df_h['ai_predicted_min']

        fig = go.Figure(data=[
            go.Bar(name='AI ทำนายเวลาใช้ห้อง', x=df_h['proc_short'], y=df_h['ai_predicted_min'], marker_color='#3498db'),
            go.Bar(name='เวลาจริง (room duration)', x=df_h['proc_short'], y=df_h['actual_duration_min'], marker_color='#2ecc71'),
        ])
        fig.update_layout(barmode='group', title='AI ทำนายเวลาใช้ห้อง vs เวลาจริง', font=dict(family="Sarabun"), height=400, xaxis_title='หัตถการ', yaxis_title='นาที (Room Duration)')
        st.plotly_chart(fig, use_container_width=True)

        mae = df_h['error'].abs().mean()
        w10 = (df_h['error'].abs() <= 10).mean() * 100
        w15 = (df_h['error'].abs() <= 15).mean() * 100
        ec1, ec2, ec3 = st.columns(3)
        ec1.metric("MAE", f"{mae:.1f} นาที")
        ec2.metric("±10 นาที", f"{w10:.0f}%")
        ec3.metric("±15 นาที", f"{w15:.0f}%")
    else:
        st.info("ยังไม่มีข้อมูล AI vs เวลาจริง — ใช้ OR Board แล้วจะเก็บสถิติอัตโนมัติ")

    # Pie chart
    st.markdown('<h3 style="color:#34495e;font-size:18px;font-weight:600;margin-top:20px;">📉 สถานะเคส</h3>', unsafe_allow_html=True)
    fig_pie = px.pie(values=[cc, tc - cc, xc], names=['เสร็จแล้ว', 'รอดำเนินการ', 'ยกเลิก'],
                     color_discrete_map={'เสร็จแล้ว': '#27ae60', 'รอดำเนินการ': '#f39c12', 'ยกเลิก': '#e74c3c'})
    fig_pie.update_layout(font=dict(family="Sarabun"), height=350)
    st.plotly_chart(fig_pie, use_container_width=True)

    # ========================================================================
    # TOP N OPERATION STATISTICS (persistent across sessions)
    # ========================================================================
    st.markdown('<h3 style="color:#34495e;font-size:18px;font-weight:600;margin-top:28px;">🏆 Top Statistics (ข้อมูลสะสม)</h3>', unsafe_allow_html=True)
    from main_or_core import (load_case_history, top_n_procedures,
                               top_n_surgeons, top_n_surg_proc, top_n_nurses)
    df_hist = load_case_history()

    if df_hist.empty:
        st.info("ยังไม่มีข้อมูลสะสม — กด 'ผ่าเสร็จ' ใน OR Board จะเก็บเข้า case_history.csv อัตโนมัติ")
    else:
        cc1, cc2, cc3 = st.columns([1, 1, 2])
        with cc1:
            top_n = st.selectbox("แสดง Top", [5, 10, 20], index=1, key="topn_sel")
        with cc2:
            scope = st.selectbox("ขอบเขต", ["ทั้งหมด", "30 วันล่าสุด", "7 วันล่าสุด"], key="topn_scope")
        with cc3:
            st.caption(f"📦 ข้อมูลสะสมทั้งหมด: **{len(df_hist)}** เคส")

        df_v = df_hist.copy()
        df_v['timestamp'] = pd.to_datetime(df_v['timestamp'], errors='coerce')
        if scope == "30 วันล่าสุด":
            df_v = df_v[df_v['timestamp'] >= (_now() - pd.Timedelta(days=30))]
        elif scope == "7 วันล่าสุด":
            df_v = df_v[df_v['timestamp'] >= (_now() - pd.Timedelta(days=7))]

        t1, t2, t3, t4, t5 = st.tabs([
            "🔝 หัตถการยอดนิยม", "⏱️ หัตถการใช้เวลานาน",
            "👨‍⚕️ ศัลยแพทย์", "🤝 Surgeon × Procedure", "👩‍⚕️ พยาบาล"
        ])

        with t1:
            st.markdown(f"**Top {top_n} หัตถการ (ตามจำนวนเคส)**")
            df_top = top_n_procedures(df_v, by='volume', n=top_n)
            if not df_top.empty:
                st.dataframe(df_top, use_container_width=True, hide_index=True)
                fig = px.bar(df_top, x='procedure', y='n_cases',
                             title=f'Top {top_n} หัตถการที่ทำบ่อยที่สุด',
                             color='avg_duration', color_continuous_scale='Blues',
                             labels={'n_cases': 'จำนวนเคส', 'avg_duration': 'เฉลี่ย (นาที)'})
                fig.update_layout(font=dict(family="Sarabun"), height=400,
                                  xaxis_title='หัตถการ', yaxis_title='จำนวนเคส')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("ยังไม่มีข้อมูล")

        with t2:
            st.markdown(f"**Top {top_n} หัตถการ (ตามเวลาเฉลี่ยที่ใช้)**")
            df_dur = top_n_procedures(df_v, by='avg_duration', n=top_n)
            if not df_dur.empty:
                st.dataframe(df_dur, use_container_width=True, hide_index=True)
                fig = px.bar(df_dur, x='procedure', y='avg_duration',
                             title=f'Top {top_n} หัตถการที่ใช้เวลานานที่สุด',
                             color='avg_duration', color_continuous_scale='Reds',
                             labels={'avg_duration': 'เฉลี่ย (นาที)'})
                fig.update_layout(font=dict(family="Sarabun"), height=400,
                                  xaxis_title='หัตถการ', yaxis_title='นาที (เฉลี่ย)')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("ยังไม่มีข้อมูล")

        with t3:
            st.markdown(f"**Top {top_n} ศัลยแพทย์ (ตามจำนวนเคส)**")
            df_surg = top_n_surgeons(df_v, by='volume', n=top_n)
            if not df_surg.empty:
                st.dataframe(df_surg, use_container_width=True, hide_index=True)
                fig = px.bar(df_surg, x='surgeon', y='n_cases',
                             title=f'Top {top_n} ศัลยแพทย์ (จำนวนเคส)',
                             color='avg_duration', color_continuous_scale='Greens',
                             labels={'n_cases': 'จำนวนเคส', 'avg_duration': 'เฉลี่ย (นาที)'})
                fig.update_layout(font=dict(family="Sarabun"), height=400,
                                  xaxis_title='ศัลยแพทย์', yaxis_title='จำนวนเคส')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("ยังไม่มีข้อมูล")

        with t4:
            st.markdown(f"**Top {top_n} คู่ ศัลยแพทย์ × หัตถการ**")
            df_sp = top_n_surg_proc(df_v, n=top_n)
            if not df_sp.empty:
                st.dataframe(df_sp, use_container_width=True, hide_index=True)
            else:
                st.caption("ยังไม่มีข้อมูล")

        with t5:
            role_label = st.radio("บทบาทพยาบาล", ["scrub", "circ"],
                                  horizontal=True, key="nurse_role_sel")
            st.markdown(f"**Top {top_n} พยาบาล ({role_label})**")
            df_nur = top_n_nurses(df_v, role=role_label, n=top_n)
            if not df_nur.empty:
                st.dataframe(df_nur, use_container_width=True, hide_index=True)
            else:
                st.caption("ยังไม่มีข้อมูลพยาบาลใน case_history")