# -*- coding: utf-8 -*-
"""
check_research_day.py : ✅ ตรวจว่าข้อมูลวิจัยของวันหนึ่งจับคู่ครบหรือยัง (อ่านอย่างเดียว)
══════════════════════════════════════════════════════════════════
สร้าง 23 พ.ย. 2026 (มุกกี้ถาม: "แล้วจะดูได้อย่างไรว่าจับคู่กันครบแล้ว")

ทุกเคสในข้อมูลวิจัยของวันนั้นควรลงเอยที่ช่องใดช่องหนึ่ง :
  ผ่าตัดแล้ว (มีเวลาจริงจาก intraop หรือจากปุ่ม) · ยกเลิก · เลื่อน
เคสที่ไม่อยู่ช่องไหนเลย = "ยังไม่ทราบผล" คือสิ่งที่ต้องตามต่อ (ครบ = ช่องนี้เป็น 0)

ใช้ (จากโฟลเดอร์ main_OR_app ต้องมี .streamlit\\secrets.toml ตัวจริง):
    python check_research_day.py               # วันนี้
    python check_research_day.py 2026-11-23
⛔ ไม่เขียนฐานข้อมูล · ไม่พิมพ์ HN หรือชื่อ : เคสที่ยังไม่ทราบผลพิมพ์เฉพาะ ห้อง เวลานัด หัตถการ
"""
from __future__ import annotations

import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def main(day=None):
    from datetime import datetime, timezone, timedelta
    # 🌐 24 พ.ย. 2026: รับวันที่ตรง ๆ ได้ ให้หน้าเว็บ (research_upload_panel) เรียกใช้รายงานชุดเดียวกัน
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    day = day or (args[0] if args else datetime.now(timezone(timedelta(hours=7))).date().isoformat())
    from db_connection import IS_POSTGRES, DB_SCHEMA
    print("=" * 66)
    print(f" check_research_day {day} · DB: {'Supabase schema ' + DB_SCHEMA if IS_POSTGRES else 'SQLite local'}")
    print("=" * 66)
    import research_log as RL
    from main_or_db import get_conn, _table_columns
    conn = get_conn()
    try:
        RL._ensure_table(conn)
        cols = _table_columns(conn, 'research_case_log')
        oc = 'outcome' if 'outcome' in cols else 'NULL'
        ts = 'time_source' if 'time_source' in cols else 'NULL'
        rows = [tuple(r) for r in conn.execute(
            f"SELECT room_no, sched_time, procedure_name, pred_ai_min, actual_or_min, actual_source, "
            f"entered_or_at, {oc}, {ts}, hn_hash FROM research_case_log WHERE log_date=? "
            f"ORDER BY room_no, sched_time", (day,)).fetchall()]
    finally:
        conn.close()
    if not rows:
        print("ไม่มีแถวของวันนี้ในข้อมูลวิจัย : รัน seed_research_from_board.py ก่อน")
        return
    done = [r for r in rows if r[4] is not None]
    canc = [r for r in rows if r[4] is None and r[7] == 'cancelled']
    post = [r for r in rows if r[4] is None and r[7] == 'postponed']
    # 🚫 24 พ.ย. 2026: 'cancel_postpone' = ไม่พบใน intraop ตอนอัปโหลดผ่านหน้าเว็บ (รวมเลื่อนกับยกเลิก)
    cp = [r for r in rows if r[4] is None and r[7] == 'cancel_postpone']
    unk = [r for r in rows if r[4] is None and r[7] not in ('cancelled', 'postponed', 'cancel_postpone')]
    print(f"เคสในข้อมูลวิจัยทั้งหมด : {len(rows)}")
    print(f"  ผ่าตัดแล้ว (มีเวลาจริง) : {len(done)}"
          f"   [เวลาจริงจาก intraop {sum(1 for r in done if r[5] == 'csv')} · จากปุ่มบนบอร์ด {sum(1 for r in done if r[5] != 'csv')}]")
    print(f"      เวลาเข้าห้องจากปุ่ม {sum(1 for r in done if r[6] and r[8] != 'his')} · เติมจาก HIS {sum(1 for r in done if r[8] == 'his')}")
    print(f"  ยกเลิก : {len(canc)}")
    print(f"  เลื่อน : {len(post)}")
    print(f"  เลื่อน/ยกเลิก (ไม่พบใน intraop) : {len(cp)}")
    print(f"  ยังไม่ทราบผล : {len(unk)}")
    print(f"ไม่มีค่าทำนาย : {sum(1 for r in rows if r[3] is None)} · ไม่มีรหัสจับคู่ HN : {sum(1 for r in rows if not r[9])}")
    if unk:
        print("\nเคสที่ยังไม่ทราบผล (ไม่มีใน intraop และไม่อยู่ในรายการยกเลิกหรือเลื่อน) :")
        for r in unk:
            print(f"  ห้อง {r[0]} · นัด {r[1] or '-'} · {str(r[2] or '-')[:50]}")
        print("\n→ ยังไม่ครบ : เช็กเคสเหล่านี้ใน HIS ว่าผ่าแล้ว ยกเลิก หรือเลื่อน")
    else:
        print("\n✅ ครบ : ทุกเคสมีผลแล้ว")
    if done:
        # 📊 23 พ.ย. 2026 (มุกกี้สั่ง): ตารางรายเคส pred_ai_min เทียบ actual_or_min · ต่าง = จริง ลบ ทำนาย (บวก = ผ่านานกว่าที่ทำนาย)
        pair = [r for r in done if r[3] is not None]
        if pair:
            print(f"\nเทียบค่าทำนายกับเวลาจริงรายเคส ({len(pair)} เคส) : หน่วยนาที · ต่าง = จริง ลบ ทำนาย")
            print(f"  {'ห้อง':<5}{'นัด':<7}{'ทำนาย':>7}{'จริง':>7}{'ต่าง':>7}  หัตถการ")
            for r in pair:
                d = r[4] - r[3]
                print(f"  {str(r[0]):<5}{str(r[1] or '-'):<7}{r[3]:>7.0f}{r[4]:>7.0f}{d:>+7.0f}  {str(r[2] or '-')[:40]}")
            err = [abs(r[4] - r[3]) for r in pair]
            bias = sum(r[4] - r[3] for r in pair) / len(pair)
            print(f"\n  คลาดเฉลี่ย (MAE) {sum(err) / len(err):.1f} นาที · ต่างเฉลี่ย {bias:+.1f} นาที"
                  f" · คลาดไม่เกิน 30 นาที {sum(1 for e in err if e <= 30)}/{len(err)} เคส")


if __name__ == '__main__':
    main()
