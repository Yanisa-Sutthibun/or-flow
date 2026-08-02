# -*- coding: utf-8 -*-
"""
research_log.py — 📊 ตารางวิจัยถาวร `research_case_log` (1 เคสจริง = 1 แถว)
════════════════════════════════════════════════════════════════════════════
มุคกี้อนุมัติดีไซน์ 15 ก.ค. 2026 — เก็บ 3 เรื่องที่ board_state (วนทับ 7 วัน) ไม่เก็บถาวร:
  ① waiting time ห้องรับ-ส่ง (รับเข้า→เข้าห้อง) = ตัวชี้วัดหลักของวิทยานิพนธ์
  ② AI vs actual + ช่วง/ความมั่นใจ ณ ตอนทำนาย — เติม/แก้ actual จากไฟล์ HIS
     ภายหลังได้ด้วย backfill_actual.py (actual_source: 'board' → 'csv')
  ③ ค่าที่พยาบาล ✏️ override

กติกา PDPA/วิจัย:
  · เคส 🎬 สาธิต / 🧪 ทดสอบ (_demo) ไม่เขียนเด็ดขาด
  · surgeon → SURG_xxx (mask ชุดเดียวกับ log อื่น)
  · ผู้ป่วยเก็บเฉพาะ hn_hash = SHA-256(salt+HN) ตัด 16 ตัว — จับคู่ CSV ได้
    แต่ถอดกลับเป็น HN ไม่ได้ · ⚠️ ควรตั้ง `hn_salt = "..."` ใน secrets ทั้ง
    เครื่อง รพ. และ cloud (ใช้ค่าเดียวกัน ไม่งั้น hash ไม่ตรงกัน จับคู่ไม่เจอ)

วิธีใช้: เรียก log_case_state(case) หลังทุกปุ่มบนบอร์ด (รับเข้า/เข้าห้อง/เสร็จ/
จำหน่าย/↩️ undo) — upsert ตาม (log_date, case_ref) เรียกซ้ำกี่ครั้งก็ได้
undo ก็แค่เขียนสถานะล่าสุดทับ (เวลาที่ถูกล้างจะกลายเป็น NULL ตามจริง)
fail-safe ทุกชั้น: DB พัง → คืน False เงียบ ๆ บอร์ดทำงานต่อปกติ
"""
from __future__ import annotations

import hashlib
import os


# ─────────────────────────── helpers ───────────────────────────

def in_research_scope(case) -> bool:
    """🚪 ประตูข้อมูลวิจัย — เกณฑ์คัดเข้าบังคับด้วยซอฟต์แวร์:
    ① ไม่ใช่เคสสาธิต/ทดสอบ (_demo) ② เป็น elective เท่านั้น
    ③ ไม่ใช่เคสนอกเวลา (นัดจริง ≥ 15:30 หรือระบุ "นอกเวลา") — เพิ่ม 2 ส.ค. 2026
      ตามขอบเขตวิทยานิพนธ์: elective ในเวลา 8:00–16:00 เท่านั้น
      (เคส "รับเวร" = เริ่มในเวลาแต่จบช้า ยังอยู่ในขอบเขต · TF ไม่นับนอกเวลา
      เพราะ 23:55 เป็นแค่ placeholder เรียงท้ายคิว)
    เคสนอกขอบเขตทุกชนิดใช้บอร์ด/AI ได้ครบ แต่ไม่ทิ้งรอยใน log วิจัยใด ๆ
    (research_case_log / override_log / shadow_v2_log ใช้ประตูนี้ร่วมกัน)"""
    if case is None or case.get('_demo'):
        return False
    if case.get('is_emergency'):
        return False
    ct = str(case.get('case_type') or 'Elective').strip().lower()
    if ct != 'elective':
        return False
    # ③ นอกเวลา — เกณฑ์เดียวกับ case_shift_class (ทำซ้ำในนี้ กัน circular import)
    if case.get('is_after_note'):
        return False
    if not case.get('is_tf'):
        try:
            _sm = int(case.get('sched_hour')) * 60 + int(case.get('sched_min') or 0)
            if _sm >= 15 * 60 + 30:
                return False
        except (TypeError, ValueError):
            pass
    return True


def _salt() -> str:
    """salt สำหรับ hash HN — ลำดับ: secrets → env → default (ควรตั้งใน secrets!)"""
    try:
        import streamlit as st
        s = st.secrets.get('hn_salt')
        if s:
            return str(s)
    except Exception:
        pass
    return os.environ.get('OR_HN_SALT') or 'orflow-default-salt'


def hn_hash(hn) -> str | None:
    """SHA-256(salt+HN) ตัด 16 hex — ใช้ร่วมกับ backfill_actual.py"""
    hn = str(hn or '').strip()
    if not hn:
        return None
    return hashlib.sha256((_salt() + hn).encode('utf-8')).hexdigest()[:16]


def _to_dt(t):
    """รับได้ทั้ง datetime และ ISO string (เคสที่ถูก restore จากบอร์ดกลาง)"""
    if t is None or not isinstance(t, str):
        return t
    from datetime import datetime
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _iso(t) -> str | None:
    t = _to_dt(t)
    try:
        return t.isoformat(timespec='seconds') if t else None
    except Exception:
        return None


def _mins(a, b) -> int | None:
    """นาทีจาก a→b (คืน None ถ้าข้อมูลไม่ครบ · clamp ≥0 กัน clock เพี้ยน)"""
    a, b = _to_dt(a), _to_dt(b)
    if not a or not b:
        return None
    return int(max((b - a).total_seconds() / 60, 0))


def _int(v):
    try:
        return int(round(float(v))) if v is not None else None
    except (TypeError, ValueError):
        return None


# ─────────────────────────── table ───────────────────────────

def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_case_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL,
            case_ref TEXT NOT NULL,
            hn_hash TEXT,
            room_no INTEGER,
            division TEXT,
            procedure_name TEXT,
            surgeon_code TEXT,
            age INTEGER,
            ward TEXT,
            sched_time TEXT,
            arrived_holding_at TEXT,
            entered_or_at TEXT,
            exited_or_at TEXT,
            exit_to TEXT,
            discharged_at TEXT,
            wait_holding_min INTEGER,
            wait_post_min INTEGER,
            pred_ai_min INTEGER,
            pred_lo INTEGER,
            pred_hi INTEGER,
            pred_confidence TEXT,
            pred_proc_n INTEGER,
            user_override_min INTEGER,
            actual_or_min INTEGER,
            actual_source TEXT,
            csv_updated_at TEXT,
            updated_at TEXT
        )""")
    conn.commit()
    # 🔒 เปิด RLS ทันทีที่ตารางเกิด (26 ก.ค. 2026) — กันประตู REST API ของ
    #    Supabase โดยไม่ต้องจำไปรัน SQL มือ · sqlite ไม่รู้จักคำสั่งนี้ = ข้ามเงียบ
    try:
        conn.execute("ALTER TABLE research_case_log ENABLE ROW LEVEL SECURITY")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def log_case_state(case) -> bool:
    """upsert สถานะปัจจุบันของเคสลง research_case_log — เรียกหลังทุกปุ่มบนบอร์ด"""
    try:
        if not in_research_scope(case):    # 🚪 สาธิต/ทดสอบ/ฉุกเฉิน — ไม่เข้าข้อมูลวิจัย
            return False
        cref = str(case.get('id') or '')
        if not cref:
            return False

        from main_or_db import get_conn, _mask_staff_for_log, _now
        now = _now()
        log_date = now.date().isoformat()

        # ── เตรียมค่าจาก case dict (ความจริงล่าสุด รวมผล undo แล้ว) ──
        arrived = case.get('time_arrived_holding')
        entered = case.get('time_entered_or')
        exited = case.get('time_exited_or')
        disch = case.get('time_discharged')
        status = case.get('status')
        exit_to_new = ('recovery' if status == 'recovery'
                       else 'holding' if status == 'holding_post' else None)
        try:
            room = int(float(case.get('or_room_assigned')
                             or case.get('room') or 0)) or None
        except (TypeError, ValueError):
            room = None
        _sh, _sm = case.get('sched_hour'), case.get('sched_min')
        sched = (f"{int(_sh):02d}:{int(_sm or 0):02d}"
                 if _sh is not None else None)
        rng = case.get('predicted_range') or (None, None)
        try:
            lo, hi = _int(rng[0]), _int(rng[1])
        except (TypeError, IndexError):
            lo, hi = None, None
        actual_new = _int(case.get('actual_duration_min'))

        vals = {
            'hn_hash': hn_hash(case.get('hn')),
            'room_no': room,
            'division': str(case.get('division') or ''),
            'procedure_name': str(case.get('procedure') or ''),
            'surgeon_code': _mask_staff_for_log(case.get('surgeon')),
            'age': _int(case.get('age')),
            'ward': str(case.get('ward') or ''),
            'sched_time': sched,
            'arrived_holding_at': _iso(arrived),
            'entered_or_at': _iso(entered),
            'exited_or_at': _iso(exited),
            'discharged_at': _iso(disch),
            'wait_holding_min': _mins(arrived, entered),
            'wait_post_min': _mins(exited, disch),
            'pred_ai_min': _int(case.get('ai_predicted_min')
                                or case.get('predicted_min')),
            'pred_lo': lo, 'pred_hi': hi,
            'pred_confidence': case.get('confidence'),
            'pred_proc_n': _int(case.get('proc_n')),
            'user_override_min': _int(case.get('user_override_min')),
            'updated_at': now.isoformat(timespec='seconds'),
        }

        conn = get_conn()
        try:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT id, exit_to, actual_or_min, actual_source "
                "FROM research_case_log WHERE log_date=? AND case_ref=?",
                (log_date, cref)).fetchone()

            # exit_to: จำครั้งแรกที่รู้ไว้ (ตอน discharged สถานะไม่บอกแล้วว่าออกไปทางไหน)
            # actual: ค่าจาก CSV (ทางการ) ห้ามโดนปุ่มบอร์ดทับ/ล้าง
            if row is not None:
                _id, exit_old, act_old, src_old = row[0], row[1], row[2], row[3]
                vals['exit_to'] = exit_to_new or exit_old
                if src_old == 'csv':
                    vals['actual_or_min'] = act_old
                    vals['actual_source'] = 'csv'
                else:
                    vals['actual_or_min'] = actual_new
                    vals['actual_source'] = 'board' if actual_new is not None else None
                sets = ', '.join(f"{k}=?" for k in vals)
                conn.execute(
                    f"UPDATE research_case_log SET {sets} WHERE id=?",
                    (*vals.values(), _id))
            else:
                vals['exit_to'] = exit_to_new
                vals['actual_or_min'] = actual_new
                vals['actual_source'] = 'board' if actual_new is not None else None
                cols = ['log_date', 'case_ref'] + list(vals.keys())
                qs = ','.join('?' * len(cols))
                conn.execute(
                    f"INSERT INTO research_case_log ({', '.join(cols)}) "
                    f"VALUES ({qs})", (log_date, cref, *vals.values()))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as ex:
        print(f"[research_log] ข้ามเคสนี้ (ไม่กระทบบอร์ด): {ex}")
        return False
