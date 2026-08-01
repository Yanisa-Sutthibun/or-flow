# -*- coding: utf-8 -*-
"""
cleanup_test_data.py — 🧹 ล้างข้อมูล "วันทดสอบระบบ" ออกจากฐานข้อมูล (Supabase/SQLite)
════════════════════════════════════════════════════════════════════
ใช้เมื่อ: ทดสอบระบบด้วย CSV โดย "ลืมติ๊ก 🧪 โหมดทดสอบ" → มีรอยหลุดเข้า
override_log / shadow_v2_log / prediction_log + บอร์ดกลางของวันนั้น

⚠️ ลบข้อมูล "ทั้งวัน" ที่ระบุ — ใช้เฉพาะวันที่มีแต่เคสทดสอบล้วนเท่านั้น
   (วันที่มีเคสจริงปน ห้ามใช้ — ให้ลบมือทีละแถวแทน)

ใช้:
    python cleanup_test_data.py 2026-07-05            # DRY-RUN: โชว์ว่าจะลบอะไร (ไม่แตะจริง)
    python cleanup_test_data.py 2026-07-05 --apply    # ลบจริง

หมายเหตุ: ถ้าตอนทดสอบติ๊ก 🧪 ไว้ → ไม่ต้องใช้สคริปต์นี้เลย
แค่ติ๊ก "🗑️ ล้างกระดานวันนี้" ใน 📤 อัปโหลด CSV บนหน้าตารางผ่าตัด ก็จบ (log ไม่เคยถูกเขียน)
"""
from __future__ import annotations

import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ตาราง log วิจัย: (ชื่อตาราง, คอลัมน์เวลา)
# 🔧 1 ส.ค. 2026: เพิ่ม research_case_log (ตารางวิจัยถาวร เขียนทุกปุ่มบนบอร์ด)
#    — เดิมสคริปต์ไม่ครอบคลุม ทดสอบจริงแล้วมีรอยค้าง
LOG_TABLES = [('override_log', 'logged_at'),
              ('shadow_v2_log', 'logged_at'),
              ('prediction_log', 'created_at'),
              ('research_case_log', 'log_date')]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit("ระบุวันที่: python cleanup_test_data.py YYYY-MM-DD [--apply]")
    day = args[0].strip()
    if len(day) != 10 or day[4] != '-' or day[7] != '-':
        sys.exit(f"รูปแบบวันที่ผิด: {day} (ต้องเป็น YYYY-MM-DD)")
    apply = '--apply' in sys.argv

    from main_or_db import get_conn
    from db_connection import IS_POSTGRES
    print("=" * 62)
    print(f" cleanup_test_data · วัน {day} · "
          f"{'APPLY (ลบจริง)' if apply else 'DRY-RUN (ดูเฉย ๆ)'} · "
          f"DB: {'Supabase' if IS_POSTGRES else 'SQLite local'}")
    print("=" * 62)

    conn = get_conn()
    try:
        for table, ts_col in LOG_TABLES:
            try:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {ts_col} LIKE ?",
                    (day + '%',)).fetchone()[0]
            except Exception as ex:
                print(f"  ⏭️  {table}: ข้าม ({str(ex)[:60]})")
                continue
            if apply and n:
                conn.execute(f"DELETE FROM {table} WHERE {ts_col} LIKE ?",
                             (day + '%',))
                conn.commit()
            print(f"  {'🗑️ ลบแล้ว' if apply else '📋 จะลบ'} {table}: {n} แถว")

        # บอร์ดกลางของวันนั้น (app_settings: board_state_YYYY-MM-DD)
        try:
            has = conn.execute(
                "SELECT COUNT(*) FROM app_settings WHERE key = ?",
                (f'board_state_{day}',)).fetchone()[0]
            if apply and has:
                conn.execute("DELETE FROM app_settings WHERE key = ?",
                             (f'board_state_{day}',))
                conn.commit()
            print(f"  {'🗑️ ลบแล้ว' if apply else '📋 จะลบ'} board_state_{day}: "
                  f"{'มี' if has else 'ไม่มี'}")
        except Exception as ex:
            print(f"  ⏭️  board_state: ข้าม ({str(ex)[:60]})")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not apply:
        print("-" * 62)
        print(" นี่คือ DRY-RUN — ถ้ารายการถูกต้อง รันซ้ำด้วย --apply")
    else:
        print(" เสร็จ — แนะนำรัน backup_research_data.py ก่อนลบครั้งหน้า")
    print("=" * 62)


if __name__ == '__main__':
    main()
