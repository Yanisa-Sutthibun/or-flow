# -*- coding: utf-8 -*-
"""
shadow_v2.py — 🕶️ Shadow mode: โมเดลวิทยานิพนธ์ 13 features (thesis_ML_v2) ทำนายเทียบเงียบ ๆ
════════════════════════════════════════════════════════════════════════════
บอร์ดยังแสดง thesis_ML ตามเดิมทุกอย่าง — v2 แค่ทำนาย "คู่ขนาน" แล้วบันทึกลงตาราง
shadow_v2_log ตอนกด "ผ่าเสร็จ" (จังหวะที่รู้เวลาจริงแล้ว) → ได้ตารางเทียบ
head-to-head บนเคสจริง: thesis_ML vs thesis_ML_v2 vs พยาบาล override vs เวลาจริง

✅ ไม่ติด ethics lock: thesis_ML_v2 เทรนด้วยข้อมูล พ.ศ. 2564-2567 (ethics-approved)
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
_V2_DIR = os.path.join(_DIR, 'models', 'thesis_ML_v2')

_mv2 = None            # โหลดครั้งเดียวต่อ process (โมเดล ~0.4MB — เบา)
_load_failed = False


def _get_model():
    """โหลด ModelV2 แบบ lazy — พังครั้งเดียวจำไว้ ไม่ลองซ้ำทุกเคส"""
    global _mv2, _load_failed
    if _mv2 is not None or _load_failed:
        return _mv2
    try:
        if not os.path.isdir(_V2_DIR):
            raise FileNotFoundError(f"ไม่พบ {_V2_DIR}")
        if _V2_DIR not in sys.path:
            sys.path.insert(0, _V2_DIR)
        from predictor import ModelV2   # models/thesis_ML_v2/predictor.py
        _mv2 = ModelV2(_V2_DIR)
        print("[shadow_v2] โหลด thesis_ML_v2 สำเร็จ — เริ่ม shadow logging")
    except Exception as ex:
        _load_failed = True
        print(f"[shadow_v2] โหลดไม่ได้ (ปิด shadow ไว้ · บอร์ดทำงานปกติ): {ex}")
    return _mv2


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
    # 🔒 เปิด RLS ทันทีที่ตารางเกิด (26 ก.ค. 2026) — sqlite ข้ามเงียบ
    try:
        conn.execute("ALTER TABLE shadow_v2_log ENABLE ROW LEVEL SECURITY")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


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
        _thesis_pred = None
        try:
            import or_time_model as _otm
            _thesis_pred = int(_otm.predict_detail({
                'procedure_name': case.get('procedure'),
                'surgeon_name': case.get('surgeon'),
                'division': case.get('division'),
                'orroom': case.get('or_room_assigned') or case.get('room') or 11,
                'age': case.get('age'), 'planned_hour': 9,
            }, 'room_use')['predicted_min'])
        except Exception as _tx:
            print(f"[shadow_v2] thesis_ML เงียบไม่ได้ (ข้ามช่องนั้น): {_tx}")
        mv2 = _get_model()
        _r90, _conf2, _pn2 = None, None, None
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
            conn.execute(
                "INSERT INTO shadow_v2_log (logged_at, case_ref, procedure_name, "
                "surgeon_code, division, room_no, pred_thesis_ml, "
                "user_override_min, pred_v2, v2_range_lo, v2_range_hi, "
                "v2_confidence, v2_proc_n, actual_duration_min) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_now(), str(case.get('id') or ''),
                 str(case.get('procedure') or ''),
                 _mask_staff_for_log(case.get('surgeon')),
                 str(case.get('division') or ''), room,
                 _thesis_pred,                       # thesis_ML (ทำนายเงียบ)
                 case.get('user_override_min'),
                 int(ai0) if ai0 else None,          # v2 = ค่าที่บอร์ดใช้จริง
                 lo, hi, _conf2, _pn2,
                 int(actual_min) if actual_min else None))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as ex:
        print(f"[shadow_v2] ข้ามเคสนี้ (ไม่กระทบบอร์ด): {ex}")
        return False
