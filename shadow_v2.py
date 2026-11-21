# -*- coding: utf-8 -*-
"""
shadow_v2.py — 🕶️ Shadow mode: โมเดลวิทยานิพนธ์ 13 features (thesis_ML_v2) ทำนายเทียบเงียบ ๆ
════════════════════════════════════════════════════════════════════════════
บอร์ดยังแสดง thesis_ML ตามเดิมทุกอย่าง — v2 แค่ทำนาย "คู่ขนาน" แล้วบันทึกลงตาราง
shadow_v2_log ตอนกด "ผ่าเสร็จ" (จังหวะที่รู้เวลาจริงแล้ว) → ได้ตารางเทียบ
head-to-head บนเคสจริง: thesis_ML vs thesis_ML_v2 vs พยาบาล override vs เวลาจริง

✅ ไม่ติด ethics lock: thesis_ML_v2 ใช้ข้อมูล พ.ศ. 2565-2567 (เทรน 65-66 ทดสอบ 67, ethics-approved)
   เท่านั้น — shadow คือ "การทำนาย" (prospective validation) ไม่ใช่การเทรน
🔒 PDPA: surgeon ถูก mask เป็น SURG_xxx ก่อนลง log (ชุดเดียวกับ override_log)
🛡️ Fail-safe ทุกชั้น: ไม่มีโฟลเดอร์ models/thesis_ML_v2 / โหลดพัง / DB พัง
   → ข้ามเงียบ ๆ ไม่กระทบบอร์ด · เคส demo ไม่บันทึก

ดูผลเทียบ (SQL):
    SELECT logged_at, procedure_name, pred_thesis_ml, pred_v2,
           user_override_min, actual_duration_min FROM shadow_v2_log;
"""
from __future__ import annotations

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
# 🧠 21 พ.ย. 2026 (มุกกี้เคาะ): แบบจำลองหลักเปลี่ยนเป็น thesis_ML_v4 (เทรน พ.ศ. 2564 ถึง มิ.ย. 2569 รู้จักห้องตึกใหม่ 90-98)
#    โฟลเดอร์ models/thesis_ML_v2 ยังอยู่ในเครื่องไว้อ้างอิง แต่ไม่ถูกโหลดแล้ว
MODEL_NAME = 'thesis_ML_v4'
_MODEL_DIR = os.path.join(_DIR, 'models', MODEL_NAME)

_mv2 = None            # โหลดครั้งเดียวต่อ process (ไฟล์แบบจำลองราว 1.3 MB)
_load_failed = False


def _get_model():
    """โหลด ModelV2 แบบ lazy — พังครั้งเดียวจำไว้ ไม่ลองซ้ำทุกเคส"""
    global _mv2, _load_failed
    if _mv2 is not None or _load_failed:
        return _mv2
    try:
        if not os.path.isdir(_MODEL_DIR):
            raise FileNotFoundError(f"ไม่พบ {_MODEL_DIR}")
        if _MODEL_DIR not in sys.path:
            sys.path.insert(0, _MODEL_DIR)
        from predictor import ModelV2   # models/thesis_ML_v4/predictor.py (ชื่อคลาสคงเดิม)
        _mv2 = ModelV2(_MODEL_DIR)
        print(f"[shadow_v2] โหลด {MODEL_NAME} สำเร็จ")
    except Exception as ex:
        _load_failed = True
        print(f"[shadow_v2] โหลดไม่ได้ (ปิด shadow ไว้ · บอร์ดทำงานปกติ): {ex}")
    return _mv2


def model_sched_hour(sched_h, sched_m=0):
    """🕘 เวลานัดบนบอร์ด (ชั่วโมง, นาที จาก estmtime ของตารางผ่าตัด · ต่อคิว = 23:55) → ช่วงเวลานัดแบบที่แบบจำลองเรียน
    ตอนเทรนใช้ opetime ของ HIS ซึ่งเท่ากับ estmtime ลบ 5 นาที (09:00 → ชั่วโมง 8 · ต่อคิว → 23) · ไม่ทราบเวลา = None"""
    try:
        return int(((int(sched_h) * 60 + int(sched_m or 0) - 5) % 1440) // 60)
    except (TypeError, ValueError):
        return None


_baseline = None       # ตารางมัธยฐานรายกลุ่มหัตถการ (โหลดครั้งเดียว) · False = โหลดไม่ได้


def _baseline_min(proc_group):
    """📐 15 พ.ย. 2026 (มุกกี้สั่ง): ค่าทำนายแบบพื้นฐานที่ไม่ใช้ machine learning
    = มัธยฐานเวลาใช้ห้องผ่าตัดของกลุ่มหัตถการเดียวกัน จากชุดเทรนชุดเดียวกับแบบจำลอง (พ.ศ. 2565-2566)
    กลุ่มที่ไม่มีในตาราง = มัธยฐานรวม · ไม่มีไฟล์/ไม่รู้กลุ่ม = None (ไม่เดา)
    ตารางสร้างโดย train/scripts/build_baseline_median.py → models/thesis_ML_v2/baseline_median.json
    จดคู่กับ pred_v2 (แบบจำลอง) และ user_override_min (พยาบาล) ใน shadow_v2_log ตอนเคสจบ
    เพื่อเทียบ 3 วิธีบนเคสจริงชุดเดียวกัน"""
    global _baseline
    if _baseline is None:
        try:
            import json as _json
            with open(os.path.join(_MODEL_DIR, 'baseline_median.json'), encoding='utf-8') as f:
                _baseline = _json.load(f)
        except Exception as ex:
            _baseline = False
            print(f"[shadow_v2] ไม่มีตารางค่าพื้นฐาน (ข้ามคอลัมน์ pred_baseline_min): {ex}")
    if not _baseline or not proc_group:
        return None
    try:
        g = (_baseline.get('per_proc_group') or {}).get(str(proc_group))
        return int(g['median']) if g else int(_baseline['global_median'])
    except Exception:
        return None


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shadow_v2_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at TEXT NOT NULL,
            case_ref TEXT,
            procedure_name TEXT,
            surgeon_code TEXT,
            division TEXT,
            room_no INTEGER,
            pred_thesis_ml INTEGER,
            user_override_min INTEGER,
            pred_v2 INTEGER,
            v2_range_lo INTEGER,
            v2_range_hi INTEGER,
            v2_confidence TEXT,
            v2_proc_n INTEGER,
            actual_duration_min INTEGER
        )""")
    conn.commit()
    # 🧭 15 พ.ย. 2026 (มุกกี้สั่ง): คอลัมน์ใหม่ pred_source (ชั้นที่ให้คำทำนายบนบอร์ด)
    #    และ features_json (ปัจจัยที่ป้อนแบบจำลอง) · pred_thesis_ml คงคอลัมน์ไว้แต่เลิกเขียน
    try:
        from main_or_db import _table_columns
        _cols = _table_columns(conn, 'shadow_v2_log')
        for _ck in ('pred_source', 'features_json'):
            if _ck not in _cols:
                conn.execute(f"ALTER TABLE shadow_v2_log ADD COLUMN {_ck} TEXT")
        if 'pred_baseline_min' not in _cols:   # 📐 ค่าทำนายแบบพื้นฐาน (มัธยฐานกลุ่มหัตถการ)
            conn.execute("ALTER TABLE shadow_v2_log ADD COLUMN pred_baseline_min INTEGER")
        conn.commit()
    except Exception as _mx:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"[shadow_v2] เพิ่มคอลัมน์ใหม่ไม่สำเร็จ (ใช้ต่อได้): {_mx}")
    # 🔒 เปิด RLS ทันทีที่ตารางเกิด (26 ก.ค. 2026) — sqlite ข้ามเงียบ
    try:
        conn.execute("ALTER TABLE shadow_v2_log ENABLE ROW LEVEL SECURITY")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def _features_for_log(case, r, masked_surgeon):
    """🧭 ปัจจัยที่ป้อนแบบจำลองของเคสนี้ (ค่าดิบก่อนเติมค่าแทน ว่าง = ไม่มีข้อมูล)
    ใช้วิเคราะห์ว่าเคสที่ทำนายพลาดมากขาดปัจจัยตัวไหน
    🔒 ไม่มีชื่อคน ไม่มี HN ไม่มีข้อความวินิจฉัย: แพทย์เป็นรหัส SURG_xxx
    การวินิจฉัยเก็บแค่ว่าแบบจำลองรู้จักหรือไม่ ค่าหมวดหมู่ตัดความยาวกันข้อความอิสระหลุด"""
    d = (r or {}).get('details') or {}
    te = d.get('te_hit') or {}
    def _n(v):
        try:
            f = float(v)
            return round(f, 1) if f == f else None
        except (TypeError, ValueError):
            return None
    def _c(v, k=20):
        s = str(v).strip() if v is not None else ''
        return s[:k] if s and s.lower() not in ('nan', 'none') else None
    return {
        'surgeon': masked_surgeon, 'surgeon_known': bool(d.get('surgeon_known')),
        'สาขา': _c(d.get('สาขา'), 40), 'proc_group': _c(d.get('proc_group'), 40),
        'procedure_canon': _c(d.get('procedure_canon'), 80),
        'procedure_known': bool(te.get('procedure')),
        'diagnosis_known': bool(te.get('diagnosis')),
        'is_inpatient': 1 if str(case.get('ward') or '').strip() else 0,
        'planicu': _c(case.get('planicu')), 'blood': _c(case.get('blood')),
        'ASA': _c(case.get('ASA'), 10), 'sex': _c(case.get('sex'), 10),
        'BMI': _n(case.get('BMI')), 'age': _n(case.get('age')),
        # 🏥🕘 21 พ.ย. 2026: ปัจจัยที่แบบจำลองรุ่นปัจจุบันใช้เพิ่ม (ห้องตามตาราง + ช่วงเวลานัด)
        'or_room': _n(case.get('room')),
        'sched_hour': model_sched_hour(case.get('sched_hour'), case.get('sched_min')),
    }


def log_shadow(case: dict, actual_min=None) -> bool:
    """เรียกจากปุ่ม 'ผ่าเสร็จ' — ทำนายด้วย thesis_ML_v2 แล้วบันทึกเทียบ (เงียบเมื่อพัง)"""
    try:
        # 🚪 ประตูวิจัย (19 ก.ค. 2026): สาธิต/ทดสอบ/ฉุกเฉิน — ไม่เข้า log วิจัย
        try:
            from research_log import in_research_scope
            if not in_research_scope(case):
                return False
        except ImportError:                     # fallback เดิม
            if not case or case.get('_demo'):
                return False
        # 🔄 บทบาทสลับ 7 ก.ค. 2026: บอร์ดโชว์ thesis_ML_v2 แล้ว →
        #    ai_predicted_min จากบอร์ด = v2 · ชั้น shadow เรียก thesis_ML สดมาเทียบ
        ai0 = case.get('ai_predicted_min') or case.get('predicted_min')   # = v2 (บนบอร์ด)
        # 🧹 15 พ.ย. 2026 (มุกกี้สั่ง): เลิกเรียกแบบจำลองรุ่นก่อน (thesis_ML) มาทำนายเงียบ
        #    การเทียบสองแบบจำลองจบแล้วตั้งแต่ขั้นพัฒนาบนชุดทดสอบปี 2567 เทียบซ้ำบนเคสจริง
        #    ไม่ตอบวัตถุประสงค์ข้อใด · thesis_ML ยังเป็นชั้นสำรองลำดับ 2 ของสายทำนายตามเดิม
        #    คอลัมน์ pred_thesis_ml คงไว้ (ข้อมูลเก่า) แต่เขียนเป็นค่าว่าง
        _thesis_pred = None
        mv2 = _get_model()
        _r90, _conf2, _pn2 = None, None, None
        r = None
        if mv2 is not None:
            r = mv2.predict_case({
                'procedure': case.get('procedure'),
                'diagnosis': case.get('diagnosis'),
                'surgeon': case.get('surgeon'),
                'division': case.get('division'),
                'age': case.get('age'),
                'ward': case.get('ward'),
                # 💉 feature จาก preop วิสัญญี (ถ้าเคสมี — 19 ก.ค. 2026)
                'ASA': case.get('ASA'), 'BMI': case.get('BMI'),
                'sex': case.get('sex'), 'planicu': case.get('planicu'),
                'blood': case.get('blood'),
                # 🏥🕘 ห้องตามตารางผ่าตัด + ช่วงเวลานัด (ชุดเดียวกับตอนทำนายขึ้นบอร์ด)
                'or_room': case.get('room'),
                'sched_hour': model_sched_hour(case.get('sched_hour'), case.get('sched_min')),
            })
            _r90 = r.get('range90')
            _conf2, _pn2 = r.get('confidence'), r.get('proc_n')
        from main_or_db import get_conn, _mask_staff_for_log, _now
        conn = get_conn()
        try:        # 🔌 finally — exception ห้ามกิน connection จาก pool
            _ensure_table(conn)
            try:
                room = int(float(case.get('or_room_assigned')
                                 or case.get('room') or 0)) or None
            except (TypeError, ValueError):
                room = None
            lo, hi = (_r90 or (None, None))
            _surg_code = _mask_staff_for_log(case.get('surgeon'))
            _cols = ['logged_at', 'case_ref', 'procedure_name', 'surgeon_code',
                     'division', 'room_no', 'pred_thesis_ml', 'user_override_min',
                     'pred_v2', 'v2_range_lo', 'v2_range_hi', 'v2_confidence',
                     'v2_proc_n', 'actual_duration_min']
            _vals = [_now(), str(case.get('id') or ''),
                     str(case.get('procedure') or ''), _surg_code,
                     str(case.get('division') or ''), room,
                     _thesis_pred,                       # เลิกเขียนแล้ว (ว่าง)
                     case.get('user_override_min'),
                     int(ai0) if ai0 else None,          # ค่าที่บอร์ดใช้จริง
                     lo, hi, _conf2, _pn2,
                     int(actual_min) if actual_min else None]
            # 🧭 คอลัมน์ใหม่: เขียนเฉพาะเมื่อตารางมีคอลัมน์แล้ว (เติมคอลัมน์ไม่สำเร็จ = แถวเดิมยังลงได้)
            try:
                from main_or_db import _table_columns as _tc
                _have = _tc(conn, 'shadow_v2_log')
            except Exception:
                _have = set()
            if 'pred_source' in _have:
                _cols.append('pred_source')
                _vals.append(case.get('pred_source'))
            if 'pred_baseline_min' in _have:
                _cols.append('pred_baseline_min')
                _vals.append(_baseline_min(((r or {}).get('details') or {}).get('proc_group')))
            if 'features_json' in _have:
                import json as _json
                _cols.append('features_json')
                _vals.append(_json.dumps(_features_for_log(case, r, _surg_code),
                                         ensure_ascii=False, default=str))
            conn.execute(
                f"INSERT INTO shadow_v2_log ({', '.join(_cols)}) "
                f"VALUES ({','.join('?' * len(_cols))})", tuple(_vals))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as ex:
        print(f"[shadow_v2] ข้ามเคสนี้ (ไม่กระทบบอร์ด): {ex}")
        return False
