# -*- coding: utf-8 -*-
"""
mark_cancel_postpone.py : 🚫 บันทึกเคสยกเลิกและเคสเลื่อนลงข้อมูลวิจัย (research_case_log)
══════════════════════════════════════════════════════════════════
สร้าง 23 พ.ย. 2026 (มุกกี้สั่ง: ส่งรายการเคสเลื่อนและยกเลิกจากหน้าจอ HIS มา "จับคู่แล้วบันทึกใน supabase ที")

เหตุผล : ไฟล์ intraop มีเฉพาะเคสที่ผ่าตัดเสร็จ เคสที่ไม่มีใน intraop แยกไม่ออกว่ายกเลิกหรือเลื่อน
(ยกเลิก = ไม่กลับมาอีก · เลื่อน = โผล่วันอื่น) · HIS รู้คำตอบที่แท็บ ยกเลิกผ่าตัด กับ เลื่อนผ่าตัด
แต่ไฟล์ export รายงานเลื่อนยกเลิกเป็นยอดรวมตามสาเหตุ ไม่มีรายผู้ป่วย จึงรับเป็นไฟล์รายการเล็ก ๆ แทน

ไฟล์รายการ (.csv UTF-8 เก็บในโฟลเดอร์ data\\ ซึ่งไม่ขึ้น git) มี 3 คอลัมน์ :
    date,hn,outcome
    2026-11-23,25491/69,cancelled        ← HN แบบที่ HIS แสดง (เลข/ปี) หรือแบบ 9 หลักก็ได้
    2026-11-23,48311/64,postponed

สิ่งที่ทำ : จับคู่ด้วย วันที่ + รหัสจับคู่ HN (hash) แล้วเขียนคอลัมน์ outcome = cancelled / postponed
  · เคสที่มีเวลาผ่าตัดจริงแล้ว (จับคู่ intraop ได้) ไม่เขียนทับ : รายงานเป็นข้อขัดแย้งให้ตรวจ
  · ไม่ลบแถว ไม่แตะค่าทำนาย · เคสที่ไม่พบในข้อมูลวิจัย (เช่น นอกเกณฑ์วิจัย) รายงานจำนวน
  · ควรรันหลัง seed_research_from_board.py และ backfill_actual.py ของวันนั้น

ใช้ (จากโฟลเดอร์ main_OR_app ต้องมี .streamlit\\secrets.toml ตัวจริง):
    python mark_cancel_postpone.py <ไฟล์รายการ.csv>            # DRY-RUN
    python mark_cancel_postpone.py <ไฟล์รายการ.csv> --apply    # เขียนจริง
⛔ ไม่พิมพ์ HN หรือชื่อ : พิมพ์เฉพาะรหัสจับคู่ 6 ตัวแรกและจำนวน
"""
from __future__ import annotations

import csv
import os
import re
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

_OUT = {'cancelled': 'cancelled', 'cancel': 'cancelled', 'ยกเลิก': 'cancelled',
        'postponed': 'postponed', 'postpone': 'postponed', 'เลื่อน': 'postponed'}


def norm_hn(v) -> str:
    """'13369/55' (แบบที่ HIS แสดง : เลข/ปี) → '550013369' (แบบในไฟล์ export : ปี 2 หลัก + เลข 7 หลัก)
    เป็นเลขล้วนอยู่แล้วคืนตามเดิม · รูปแบบอื่นคืน ''"""
    s = str(v or '').strip().replace(' ', '')
    m = re.fullmatch(r'(\d{1,7})/(\d{2})', s)
    if m:
        return m.group(2) + m.group(1).zfill(7)
    return s if s.isdigit() else ''


def read_list(path):
    rows, bad = [], 0
    with open(path, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            d = str(r.get('date') or '').strip()[:10]
            hn = norm_hn(r.get('hn'))
            oc = _OUT.get(str(r.get('outcome') or '').strip().lower())
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', d) and hn and oc:
                rows.append((d, hn, oc))
            else:
                bad += 1
    return rows, bad


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    if len(args) != 1 or not os.path.exists(args[0]):
        sys.exit("ใช้ : python mark_cancel_postpone.py <ไฟล์รายการ.csv> [--apply]")
    rows, bad = read_list(args[0])

    from db_connection import IS_POSTGRES, DB_SCHEMA
    print("=" * 66)
    print(f" mark_cancel_postpone · {'APPLY (เขียนจริง)' if apply else 'DRY-RUN (อ่านอย่างเดียว)'}"
          f" · DB: {'Supabase schema ' + DB_SCHEMA if IS_POSTGRES else 'SQLite local'}")
    print("=" * 66)
    print(f"① รายการ : {len(rows)} เคส (ยกเลิก {sum(1 for r in rows if r[2] == 'cancelled')} · "
          f"เลื่อน {sum(1 for r in rows if r[2] == 'postponed')}) · แถวที่อ่านไม่ได้ {bad}")

    import research_log as RL
    from main_or_db import get_conn, _now, _table_columns
    conn = get_conn()
    n_set = n_conf = n_miss = 0
    try:
        RL._ensure_table(conn)
        has_col = 'outcome' in _table_columns(conn, 'research_case_log')
        if apply and not has_col:
            conn.execute("ALTER TABLE research_case_log ADD COLUMN outcome TEXT")
            conn.execute("ALTER TABLE research_case_log ADD COLUMN outcome_at TEXT")
            conn.commit()
            has_col = True
        for d, hn, oc in rows:
            hh = RL.hn_hash(hn)
            found = [tuple(r) for r in conn.execute(
                "SELECT id, actual_or_min FROM research_case_log WHERE log_date=? AND hn_hash=?",
                (d, hh)).fetchall()]
            if not found:
                n_miss += 1
                print(f"  {d} · {hh[:6]}… : ไม่พบในข้อมูลวิจัย ({oc})")
                continue
            for _id, actual in found:
                if actual is not None:
                    n_conf += 1
                    print(f"  {d} · {hh[:6]}… : ⚠️ มีเวลาผ่าตัดจริงแล้ว {actual} นาที แต่รายการระบุ {oc} : ไม่เขียนทับ")
                    continue
                n_set += 1
                print(f"  {d} · {hh[:6]}… : {oc}" + ("" if apply else "  (dry-run)"))
                if apply:
                    conn.execute("UPDATE research_case_log SET outcome=?, outcome_at=? WHERE id=?",
                                 (oc, str(_now()), _id))
        if apply:
            conn.commit()
    finally:
        conn.close()
    print(f"② {'เขียนแล้ว' if apply else 'จะเขียน'} {n_set} เคส · ขัดแย้งกับ intraop (ข้าม) {n_conf} · ไม่พบในข้อมูลวิจัย {n_miss}")
    if not apply:
        print("③ DRY-RUN : ยังไม่ได้เขียน · ใส่ --apply เพื่อเขียนจริง")


if __name__ == '__main__':
    main()
