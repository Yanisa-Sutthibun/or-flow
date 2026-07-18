# -*- coding: utf-8 -*-
"""
backfill_actual.py — 📥 เติม/แก้เวลาผ่าตัดจริงใน research_case_log จากไฟล์ HIS
════════════════════════════════════════════════════════════════════════════
ใช้เมื่อ: อยากทับค่า actual จากปุ่มบอร์ด ('board') ด้วยค่าทางการจากไฟล์
intraop/รายงาน HIS ('csv' — ถือว่าแม่นกว่า และจะไม่ถูกปุ่มบอร์ดทับกลับ)

รูปแบบไฟล์ที่รับ (.csv / .xlsx): ต้องมีคอลัมน์ (ชื่อยืดหยุ่น เดาให้อัตโนมัติ)
  · hn                     — HN ผู้ป่วย (ใช้ hash จับคู่ ไม่เก็บลง DB)
  · date / op_date         — วันที่ผ่าตัด (YYYY-MM-DD หรือ พ.ศ. ก็แปลงให้)
  · duration / นาที        — เวลาใช้ห้องจริง (นาที)  ← มีอันนี้ใช้อันนี้เลย
    หรือ in_time + out_time — เวลาเข้า/ออกห้อง (HH:MM) ให้คำนวณนาทีให้

วิธีใช้ (จากเครื่องที่มี secrets — เครื่อง รพ.):
    python backfill_actual.py ไฟล์.csv            # DRY-RUN: โชว์ว่าจะจับคู่/แก้อะไร
    python backfill_actual.py ไฟล์.csv --apply    # เขียนจริง

⚠️ salt: ต้องรันบนเครื่องที่ตั้ง hn_salt ตัวเดียวกับแอป (secrets/ENV)
ไม่งั้น hash ไม่ตรง จับคู่ไม่เจอ
"""
from __future__ import annotations

import sys

from research_log import hn_hash


def _read_rows(path: str):
    import pandas as pd
    if path.lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(path, dtype=str)
    else:
        df = pd.read_csv(path, dtype=str, encoding='utf-8-sig')
    df.columns = [str(c).strip().lower() for c in df.columns]

    def _pick(*names):
        for n in names:
            if n in df.columns:
                return n
        return None

    c_hn = _pick('hn', 'เลข hn', 'hn.')
    c_date = _pick('op_date', 'date', 'วันที่', 'opdate')
    c_dur = _pick('duration', 'duration_min', 'นาที', 'room_use', 'เวลาใช้ห้อง')
    c_in = _pick('in_time', 'time_in', 'เข้าห้อง', 'in_or')
    c_out = _pick('out_time', 'time_out', 'ออกห้อง', 'out_or')
    if not c_hn or not c_date or not (c_dur or (c_in and c_out)):
        raise SystemExit(f"❌ หาคอลัมน์ไม่ครบ (เจอ: {list(df.columns)}) — "
                         f"ต้องมี hn + date + (duration หรือ in_time/out_time)")

    rows = []
    for _, r in df.iterrows():
        hn = str(r.get(c_hn) or '').strip()
        d = str(r.get(c_date) or '').strip()[:10].replace('/', '-')
        # พ.ศ. → ค.ศ. (2569-07-15 → 2026-07-15)
        try:
            y = int(d.split('-')[0])
            if y > 2400:
                d = f"{y - 543}{d[4:]}"
        except (ValueError, IndexError):
            continue
        dur = None
        if c_dur and r.get(c_dur):
            try:
                dur = int(round(float(r[c_dur])))
            except (TypeError, ValueError):
                dur = None
        if dur is None and c_in and c_out and r.get(c_in) and r.get(c_out):
            try:
                h1, m1 = str(r[c_in]).strip().split(':')[:2]
                h2, m2 = str(r[c_out]).strip().split(':')[:2]
                dur = (int(h2) * 60 + int(m2)) - (int(h1) * 60 + int(m1))
                if dur < 0:
                    dur += 24 * 60          # ข้ามเที่ยงคืน
            except (ValueError, IndexError):
                dur = None
        if hn and d and dur and dur > 0:
            rows.append((hn_hash(hn), d, dur))
    return rows


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = sys.argv[1]
    apply = '--apply' in sys.argv
    rows = _read_rows(path)
    print(f"อ่านไฟล์ได้ {len(rows)} แถวที่ข้อมูลครบ")

    from main_or_db import get_conn, _now
    conn = get_conn()
    matched, updated, missed = 0, 0, []
    try:
        for hh, d, dur in rows:
            row = conn.execute(
                "SELECT id, actual_or_min, actual_source FROM research_case_log "
                "WHERE log_date=? AND hn_hash=?", (d, hh)).fetchone()
            if row is None:
                missed.append((d, hh[:6]))
                continue
            matched += 1
            _id, old, _src = row
            print(f"  {d} · {hh[:6]}… : {old if old is not None else '—'} → {dur} นาที"
                  + ("" if apply else "  (dry-run)"))
            if apply:
                conn.execute(
                    "UPDATE research_case_log SET actual_or_min=?, "
                    "actual_source='csv', csv_updated_at=? WHERE id=?",
                    (dur, _now().isoformat(timespec='seconds'), _id))
                updated += 1
        if apply:
            conn.commit()
    finally:
        conn.close()

    print(f"\nจับคู่ได้ {matched}/{len(rows)} แถว · "
          + (f"เขียนจริง {updated} แถว ✅" if apply
             else "ยังไม่เขียน (เติม --apply เพื่อเขียนจริง)"))
    if missed:
        print(f"ไม่เจอคู่ {len(missed)} แถว (เคสอาจไม่อยู่บนบอร์ดวันนั้น "
              f"หรือ hn_salt ไม่ตรงกัน): {missed[:5]}{'…' if len(missed) > 5 else ''}")


if __name__ == '__main__':
    main()
