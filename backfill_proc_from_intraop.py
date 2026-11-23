# -*- coding: utf-8 -*-
"""
backfill_proc_from_intraop.py : 🔁 แก้ชื่อหัตถการในสถิติย้อนหลังให้ใช้ชื่อที่ลงรหัสหลังผ่าตัดใน intraop
══════════════════════════════════════════════════════════════════
สร้าง 23 พ.ย. 2026 (มุกกี้สั่ง: "ไปจัดการสถิติย้อนหลังด้วยนะ เลือกจาก intraop ก่อนถ้าไม่มีค่อยไปเลือกจาก schedule
แก้ใน supabase ด้วย")

คู่กับ update_stats_from_his.py ที่ใช้กติกาเดียวกันกับวันที่นำเข้าใหม่ : สคริปต์นี้ทำกับแถวที่อยู่ในตาราง cases แล้ว
  · จับคู่แถวสถิติกับแถว intraop ด้วย (วันผ่าตัด, ห้อง, เวลาเข้าห้อง) : กุญแจซ้ำ ข้าม ไม่เดา
  · intraop มี icd9cmnm และต่างจากชื่อเดิม → เปลี่ยน procedure_name เป็นชื่อจาก intraop
    intraop ไม่มี icd9cmnm → คงชื่อเดิม (ชื่อจากตารางผ่าตัด)
  · เก็บชื่อเดิมไว้ในคอลัมน์ procedure_plan (สร้างให้ถ้ายังไม่มี) : ย้อนกลับได้ และยังรู้ว่าแผนเดิมคืออะไร
  · ไม่เพิ่มแถว ไม่ลบแถว ไม่แตะเวลา ค่าทำนาย หรือชื่อบุคลากร · รันซ้ำได้
  · ถ้าเปลี่ยนชื่อแล้วจะชนกับแถวอื่น (วัน ห้อง หัตถการ เวลาเข้าห้อง ซ้ำกัน) ข้ามแถวนั้น

ใช้ (จากโฟลเดอร์ main_OR_app ต้องมี .streamlit\\secrets.toml ตัวจริง):
    python backfill_proc_from_intraop.py <intraop ไฟล์ที่ 1> [ไฟล์ที่ 2 ...]            # DRY-RUN
    python backfill_proc_from_intraop.py <intraop ไฟล์ที่ 1> [ไฟล์ที่ 2 ...] --apply    # เขียนจริง
⛔ ใช้เฉพาะวันที่ ห้อง เวลา และชื่อหัตถการ · ไม่อ่าน HN หรือชื่อผู้ป่วย ไม่พิมพ์เนื้อหาแถว
"""
from __future__ import annotations

import collections
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def read_procs(path):
    """ไฟล์ intraop → {(op_date, room, in_ts): set ของ icd9cmnm ที่ไม่ว่าง} + (จำนวนแถว, แถวที่มี icd9cmnm)"""
    import his_csv as HC
    import update_stats_from_his as U
    ih, irows, _info = U._read_intraop(path)
    I = {k: HC.col(ih, k) for k in ('opedate', 'roomdatein', 'roomtimein', 'orroom', 'icd9cmnm')}
    if min(I['opedate'], I['roomtimein']) < 0:
        sys.exit(f"⛔ ไฟล์ไม่ใช่ intraop (ไม่พบ opedate / roomtimein) : {path}")
    if I['icd9cmnm'] < 0:
        print(f"    ไฟล์นี้ไม่มีคอลัมน์ icd9cmnm : ข้าม ({os.path.basename(path)})")
        return {}, len(irows), 0
    order = U._date_order(r[I['opedate']] for r in irows)

    def g(row, ix):
        return row[ix].strip() if 0 <= ix < len(row) else ''

    out = collections.defaultdict(set)
    n_has = 0
    for r in irows:
        op_date = HC.to_iso(g(r, I['opedate']), order)
        nm = U._clean(g(r, I['icd9cmnm']))
        if not op_date or not nm:
            continue
        room_s = g(r, I['orroom'])
        room = int(room_s) if room_s.isdigit() else -1
        in_ts = U._ts(HC.to_iso(g(r, I['roomdatein']), order) or op_date, g(r, I['roomtimein']))
        if not in_ts:
            continue
        n_has += 1
        out[(op_date, room, in_ts)].add(nm)
    return out, len(irows), n_has


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    if not paths:
        sys.exit("ใช้ : python backfill_proc_from_intraop.py <intraop ไฟล์ที่ 1> [ไฟล์ที่ 2 ...] [--apply]")
    for p in paths:
        if not os.path.exists(p):
            sys.exit(f"⛔ ไม่พบไฟล์ : {p}")

    from db_connection import IS_POSTGRES, DB_SCHEMA
    print("=" * 66)
    print(f" backfill_proc_from_intraop · {'APPLY (เขียนจริง)' if apply else 'DRY-RUN (อ่านอย่างเดียว)'}"
          f" · DB: {'Supabase schema ' + DB_SCHEMA if IS_POSTGRES else 'SQLite local'}")
    print("=" * 66)

    procs = collections.defaultdict(set)
    for p in paths:
        m, n_rows, n_has = read_procs(p)
        for k, v in m.items():
            procs[k] |= v
        print(f"① {os.path.basename(p)} : {n_rows} แถว · มีหัตถการหลังผ่าตัด {n_has}")

    from main_or_db import get_conn, _table_columns
    conn = get_conn()
    try:
        has_plan = 'procedure_plan' in _table_columns(conn)
        if apply and not has_plan:
            conn.execute("ALTER TABLE cases ADD COLUMN procedure_plan TEXT")
            conn.commit()
            has_plan = True
        rows = [tuple(r) for r in conn.execute(
            "SELECT case_id, op_date, room_no, in_or_at, procedure_name FROM cases "
            "WHERE in_or_at IS NOT NULL AND status IN ('post_op','discharged','done')").fetchall()]

        def _key(d, rm, t):
            return (str(d)[:10], int(rm) if rm is not None else -1, str(t)[:19])
        key_n = collections.Counter(_key(d, rm, t) for _, d, rm, t, _p in rows)
        taken = {(_key(d, rm, t), str(p or '')) for _, d, rm, t, p in rows}
        by_year = collections.Counter()
        n_nofile = n_same = n_amb = n_clash = 0
        todo = []
        for cid, d, rm, t, old in rows:
            k = _key(d, rm, t)
            got = procs.get(k)
            if not got:
                n_nofile += 1
                continue
            if len(got) > 1 or key_n[k] > 1:               # กุญแจซ้ำ : ไม่เดา
                n_amb += 1
                continue
            new = next(iter(got))
            if new == str(old or ''):
                n_same += 1
                continue
            if (k, new) in taken:                           # จะชน unique (วัน ห้อง หัตถการ เวลาเข้าห้อง)
                n_clash += 1
                continue
            taken.add((k, new))
            todo.append((new, old, cid))
            by_year[k[0][:4]] += 1
        print(f"② เคสในสถิติ : {len(rows)}")
        print(f"    จะเปลี่ยนชื่อหัตถการ {len(todo)} · ชื่อตรงกันอยู่แล้ว {n_same} · "
              f"intraop ไม่มีหัตถการหลังผ่าตัดหรือไม่พบในไฟล์ {n_nofile} (คงชื่อเดิม)")
        print(f"    กุญแจซ้ำ ข้าม {n_amb} · จะชนกับแถวอื่น ข้าม {n_clash}")
        for y in sorted(by_year):
            print(f"    พ.ศ. {int(y) + 543} : {by_year[y]:>5} เคส")
        if not apply:
            print("③ DRY-RUN : ยังไม่ได้เขียน · ใส่ --apply เพื่อเขียนจริง")
            return
        for i, (new, old, cid) in enumerate(todo, 1):
            conn.execute("UPDATE cases SET procedure_plan=COALESCE(procedure_plan, ?), procedure_name=? "
                         "WHERE case_id=?", (old, new, cid))
            if i % 500 == 0:
                conn.commit()
                print(f"    {i}/{len(todo)}", flush=True)
        conn.commit()
        print(f"③ เขียนแล้ว {len(todo)} เคส · ชื่อเดิมเก็บไว้ในคอลัมน์ procedure_plan")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
