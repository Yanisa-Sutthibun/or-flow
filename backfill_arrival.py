# -*- coding: utf-8 -*-
"""
backfill_arrival.py : ⏱️ เติมเวลามาถึงห้องผ่าตัด (arrived_at) ย้อนหลังจากไฟล์ intraop ของ HIS
══════════════════════════════════════════════════════════════════
สร้าง 22 พ.ย. 2026 (มุคกี้สั่ง: "เวลารอ คือ เวลาเข้าห้อง - arrivetime ... ถือว่าเป็นสถิติย้อนหลัง")

เหตุผล : เคสสถิติปี 64-67 ที่นำเข้ารุ่นแรกไม่ได้เก็บเวลามาถึง การ์ด "เวลารอผู้ป่วย"
ในหน้าสถิติย้อนหลังจึงไม่มีอะไรให้คำนวณ · สคริปต์นี้เติมเฉพาะ 2 ช่อง arrived_at และ wait_min
ของเคสที่ arrived_at ยังว่าง ไม่แตะช่องอื่น ไม่เพิ่มแถว ไม่ลบแถว

จับคู่ด้วย (วันผ่าตัด, ห้อง, เวลาเข้าห้อง) : กุญแจเดียวกับที่ตัวนำเข้าสถิติใช้กันซ้ำ
  · กุญแจที่ซ้ำกันในไฟล์หรือในฐานข้อมูล ข้าม ไม่เดา
  · เวลารอที่ติดลบหรือเกิน 12 ชั่วโมง = ลงเวลาผิด เติม arrived_at แต่ไม่เติม wait_min

กติกาความปลอดภัย
  1. ไม่ใส่ --apply = DRY-RUN อ่านอย่างเดียว
  2. ใช้เฉพาะวันที่ ห้อง และเวลา · ไม่อ่าน HN หรือชื่อผู้ป่วย ไม่พิมพ์เนื้อหาแถว

ใช้ (จากโฟลเดอร์ main_OR_app ต้องมี .streamlit\\secrets.toml ตัวจริง):
    python backfill_arrival.py <intraop ไฟล์ที่ 1> [ไฟล์ที่ 2 ...]            # DRY-RUN
    python backfill_arrival.py <intraop ไฟล์ที่ 1> [ไฟล์ที่ 2 ...] --apply    # เขียนจริง
"""
from __future__ import annotations

import collections
import os
import sys
from datetime import datetime as _dt

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def read_arrivals(path):
    """ไฟล์ intraop → {(op_date, room, in_ts): set ของ arr_ts} + จำนวนแถวที่ไม่มีเวลามาถึง"""
    import his_csv as HC
    import update_stats_from_his as U
    ih, irows, _info = U._read_intraop(path)
    I = {k: HC.col(ih, k) for k in ('opedate', 'roomdatein', 'roomtimein', 'orroom',
                                    'arrivdate', 'arrivtime')}
    if min(I['opedate'], I['roomtimein'], I['arrivtime']) < 0:
        sys.exit(f"⛔ ไฟล์ไม่ใช่ intraop (ไม่พบ opedate / roomtimein / arrivtime) : {path}")
    order = U._date_order(r[I['opedate']] for r in irows)

    def g(row, ix):
        return row[ix].strip() if 0 <= ix < len(row) else ''

    out = collections.defaultdict(set)
    n_noarr = 0
    for r in irows:
        op_date = HC.to_iso(g(r, I['opedate']), order)
        if not op_date:
            continue
        room_s = g(r, I['orroom'])
        room = int(room_s) if room_s.isdigit() else -1
        in_ts = U._ts(HC.to_iso(g(r, I['roomdatein']), order) or op_date, g(r, I['roomtimein']))
        arr_ts = U._ts(HC.to_iso(g(r, I['arrivdate']), order) or op_date, g(r, I['arrivtime']))
        if not in_ts:
            continue
        if not arr_ts:
            n_noarr += 1
            continue
        out[(op_date, room, in_ts)].add(arr_ts)
    return out, len(irows), n_noarr


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    if not paths:
        sys.exit("ใช้ : python backfill_arrival.py <intraop ไฟล์ที่ 1> [ไฟล์ที่ 2 ...] [--apply]")
    for p in paths:
        if not os.path.exists(p):
            sys.exit(f"⛔ ไม่พบไฟล์ : {p}")

    from db_connection import IS_POSTGRES, DB_SCHEMA
    print("=" * 66)
    print(f" backfill_arrival · {'APPLY (เขียนจริง)' if apply else 'DRY-RUN (อ่านอย่างเดียว)'}"
          f" · DB: {'Supabase schema ' + DB_SCHEMA if IS_POSTGRES else 'SQLite local'}")
    print("=" * 66)

    arr = collections.defaultdict(set)
    for p in paths:
        m, n_rows, n_noarr = read_arrivals(p)
        for k, v in m.items():
            arr[k] |= v
        print(f"① {os.path.basename(p)} : {n_rows} แถว · ไม่มีเวลามาถึง {n_noarr}")

    from main_or_db import get_conn
    conn = get_conn()
    try:
        rows = [tuple(r) for r in conn.execute(
            "SELECT case_id, op_date, room_no, in_or_at FROM cases "
            "WHERE arrived_at IS NULL AND in_or_at IS NOT NULL "
            "AND status IN ('post_op','discharged','done')").fetchall()]
        key_n = collections.Counter(
            (str(d)[:10], int(rm) if rm is not None else -1, str(t)[:19]) for _, d, rm, t in rows)
        by_year = collections.Counter()
        n_nofile = n_amb = n_badwait = 0
        todo = []
        for cid, d, rm, t in rows:
            k = (str(d)[:10], int(rm) if rm is not None else -1, str(t)[:19])
            got = arr.get(k)
            if not got:
                n_nofile += 1
                continue
            if len(got) > 1 or key_n[k] > 1:               # กุญแจซ้ำ : ไม่เดา
                n_amb += 1
                continue
            a = next(iter(got))
            wait = int((_dt.fromisoformat(k[2]) - _dt.fromisoformat(a)).total_seconds() // 60)
            if not (0 <= wait <= 720):
                wait = None
                n_badwait += 1
            todo.append((a, wait, cid))
            by_year[k[0][:4]] += 1
        print(f"② เคสที่ยังไม่มีเวลามาถึงในฐานข้อมูล : {len(rows)}")
        print(f"    เติมได้ {len(todo)} · ไม่พบในไฟล์ {n_nofile} · กุญแจซ้ำ ข้าม {n_amb} · "
              f"เวลารอผิดปกติ (เติมเฉพาะเวลามาถึง) {n_badwait}")
        for y in sorted(by_year):
            print(f"    พ.ศ. {int(y) + 543} : {by_year[y]:>5} เคส")
        if not apply:
            print("③ DRY-RUN : ยังไม่ได้เขียน · ใส่ --apply เพื่อเขียนจริง")
            return
        for i, (a, wait, cid) in enumerate(todo, 1):
            conn.execute("UPDATE cases SET arrived_at=?, wait_min=? "
                         "WHERE case_id=? AND arrived_at IS NULL", (a, wait, cid))
            if i % 500 == 0:
                conn.commit()
                print(f"    {i}/{len(todo)}", flush=True)
        conn.commit()
        print(f"③ เขียนแล้ว {len(todo)} เคส")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
