# -*- coding: utf-8 -*-
"""
seed_research_from_board.py : 🌱 สร้างแถวข้อมูลวิจัยย้อนหลังจากบอร์ดที่เก็บไว้บนฐานข้อมูล
══════════════════════════════════════════════════════════════════
สร้าง 23 พ.ย. 2026 (มุกกี้สั่ง: "ถ้า upload ก็เริ่มบันทึกได้เลย แล้วเคสไหนไม่มีก็บันทึกข้อมูลย้อนหลังจาก intraop")

ใช้เมื่อ : วันที่อัปโหลดตารางไปก่อนที่ระบบจะสร้างแถวข้อมูลวิจัยให้เองตอนอัปโหลด (เช่น 23 พ.ย. 2026)
หรือวันที่การสร้างแถวตอนอัปโหลดล้ม · อ่านบอร์ดของวันนั้น (เก็บไว้ 7 วัน) แล้วสร้างแถวให้เคสที่เข้าเกณฑ์วิจัย
และยังไม่มีแถว พร้อมค่าที่ AI ทำนายตอนอัปโหลด · ไม่แตะแถวที่มีอยู่แล้ว รันซ้ำได้

จากนั้นรัน backfill_actual.py <ไฟล์ intraop> เพื่อเติมเวลาจริง

ใช้ (จากโฟลเดอร์ main_OR_app ต้องมี .streamlit\\secrets.toml ตัวจริง):
    python seed_research_from_board.py                 # DRY-RUN ของวันนี้
    python seed_research_from_board.py 2026-11-23      # DRY-RUN ของวันที่ระบุ
    python seed_research_from_board.py 2026-11-23 --apply
⛔ ไม่พิมพ์รายละเอียดเคส (บอร์ดมีชื่อและ HN แบบปิดบัง) : พิมพ์เฉพาะจำนวน
"""
from __future__ import annotations

import json
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    from datetime import datetime, timezone, timedelta
    day = args[0] if args else datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    try:
        datetime.strptime(day, '%Y-%m-%d')
    except ValueError:
        sys.exit("⛔ วันที่ต้องเป็นรูปแบบ YYYY-MM-DD เช่น 2026-11-23")

    from db_connection import IS_POSTGRES, DB_SCHEMA
    print("=" * 66)
    print(f" seed_research_from_board · {'APPLY (เขียนจริง)' if apply else 'DRY-RUN (อ่านอย่างเดียว)'}"
          f" · DB: {'Supabase schema ' + DB_SCHEMA if IS_POSTGRES else 'SQLite local'}")
    print("=" * 66)

    from main_or_db import load_board_state, get_conn
    raw = load_board_state(day)
    if not raw:
        sys.exit(f"⛔ ไม่พบบอร์ดของวันที่ {day} ในฐานข้อมูล (บอร์ดเก็บย้อนหลัง 7 วัน)")
    payload = json.loads(raw)
    from main_or_pages import _deser
    cases = [{k: _deser(v) for k, v in c.items()} for c in payload.get('cases', [])]

    import research_log as RL
    scope = [c for c in cases if RL.in_research_scope(c) and str(c.get('id') or '')]
    conn = get_conn()
    try:
        RL._ensure_table(conn)
        have = {str(r[0]) for r in conn.execute(
            "SELECT case_ref FROM research_case_log WHERE log_date=?", (day,)).fetchall()}
    finally:
        conn.close()
    new = [c for c in scope if str(c.get('id')) not in have]
    print(f"① บอร์ดวันที่ {day} : {len(cases)} เคส · เข้าเกณฑ์วิจัย {len(scope)} เคส")
    print(f"    มีแถวอยู่แล้ว {len(scope) - len(new)} · ต้องสร้างใหม่ {len(new)}")
    print(f"    ในชุดที่จะสร้าง : มีค่าทำนาย {sum(1 for c in new if c.get('ai_predicted_min') or c.get('predicted_min'))}"
          f" · มีรหัสจับคู่ HN {sum(1 for c in new if c.get('hn_hash'))}")
    if not apply:
        print("② DRY-RUN : ยังไม่ได้เขียน · ใส่ --apply เพื่อเขียนจริง")
        return
    n = RL.seed_cases(cases, log_date=day)
    print(f"② สร้างแล้ว {n} แถว")
    if n != len(new):
        print("    ⚠️ จำนวนไม่ตรงกับที่คาด : ดูข้อความ [research_log] ด้านบน")


if __name__ == '__main__':
    main()
