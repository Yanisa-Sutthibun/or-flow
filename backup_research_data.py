# -*- coding: utf-8 -*-
"""
backup_research_data.py — 💾 สำรองข้อมูลวิจัยจากฐานข้อมูล → CSV ในเครื่อง
════════════════════════════════════════════════════════════════════
ทำไมต้องมี: ข้อมูล prospective ของวิทยานิพนธ์ (override_log, shadow_v2_log,
prediction_log, cases) อยู่บน Supabase/SQLite ที่เดียว — ถ้าโปรเจกต์หาย
= ข้อมูลเล่มหายแบบย้อนคืนไม่ได้ · สคริปต์นี้ export ทุกตารางเป็น CSV

ใช้:
    python backup_research_data.py            # สำรองลง backups_research/YYYY-MM-DD/
    python backup_research_data.py --list     # ดูรายการ backup ที่มี

ตั้งอัตโนมัติรายสัปดาห์ (Windows — รันครั้งเดียวใน PowerShell แบบ Admin):
    schtasks /Create /TN "ORFlow_backup" /SC WEEKLY /D MON /ST 07:30 ^
      /TR "python C:\Dev\main_OR_app\backup_research_data.py"

หมายเหตุ: อ่านอย่างเดียว (SELECT) — ไม่แตะข้อมูล · โฟลเดอร์ backups_research/
ถูก gitignore (ข้อมูลวิจัยจริง ห้ามขึ้น repo) · ต่อ DB ตาม secrets.toml เหมือนแอป
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(_DIR)   # ให้ secrets/db path ทำงานเหมือนตอนรันแอป
OUT_ROOT = os.path.join(_DIR, 'backups_research')

# ตารางข้อมูลวิจัย (ตารางไหนยังไม่ถูกสร้าง = ข้ามพร้อมแจ้ง)
TABLES = ['cases', 'override_log', 'shadow_v2_log', 'prediction_log']


def export_table(conn, table: str, out_dir: str):
    try:
        cur = conn.execute(f"SELECT * FROM {table}")   # ชื่อตารางจาก list คงที่ — ปลอดภัย
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    except Exception as ex:
        print(f"  ⏭️  {table}: ข้าม ({str(ex)[:70]})")
        return 0
    path = os.path.join(out_dir, f"{table}.csv")
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    print(f"  ✅ {table}: {len(rows):,} แถว → {os.path.relpath(path, _DIR)}")
    return len(rows)


def main():
    if '--list' in sys.argv:
        if not os.path.isdir(OUT_ROOT):
            print("ยังไม่เคยสำรอง")
            return
        for d in sorted(os.listdir(OUT_ROOT)):
            full = os.path.join(OUT_ROOT, d)
            n = len([f for f in os.listdir(full) if f.endswith('.csv')])
            print(f"  {d}: {n} ตาราง")
        return

    from db_connection import get_connection, IS_POSTGRES
    stamp = datetime.now().strftime('%Y-%m-%d')
    out_dir = os.path.join(OUT_ROOT, stamp)
    os.makedirs(out_dir, exist_ok=True)
    print(f"💾 สำรองข้อมูลวิจัย ({'Supabase' if IS_POSTGRES else 'SQLite local'}) → {out_dir}")

    conn = get_connection()
    total = 0
    try:
        for t in TABLES:
            total += export_table(conn, t, out_dir)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    with open(os.path.join(out_dir, '_summary.txt'), 'w', encoding='utf-8') as f:
        f.write(f"backup: {datetime.now().isoformat(timespec='seconds')}\n"
                f"source: {'postgres/supabase' if IS_POSTGRES else 'sqlite'}\n"
                f"rows_total: {total}\n")
    print(f"เสร็จ — รวม {total:,} แถว · เก็บอย่างน้อย 2 ชุดล่าสุดไว้เสมอ")


if __name__ == '__main__':
    main()
