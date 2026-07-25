# -*- coding: utf-8 -*-
"""
staff_map_sync.py — 🔐 พจนานุกรมแพทย์ (staff_mapping.csv) สำหรับเครื่องที่ไม่มีไฟล์
════════════════════════════════════════════════════════════════════════════
ปัญหา: staff_mapping.csv (ชื่อจริง ↔ SURG_xxx) ห้ามขึ้น git (PDPA) →
Streamlit Cloud ไม่มีไฟล์ → โมเดลมองไม่เห็นตัวแพทย์ (~24% ของความแม่น)
+ dropdown เลือกแพทย์ว่าง

ทางแก้ (มุคกี้เลือกทาง A — 14 ก.ค. 2026): เก็บสำเนาไว้ในตาราง `staff_map`
บน Supabase (ล็อกด้วย credentials ใน secrets) → ตอนแอปบูต ถ้าไม่เจอไฟล์
ให้ดึงจากตารางมาเขียนเป็น staff_mapping.csv ข้างแอป

ข้อดีของวิธี "สร้างไฟล์คืน": โค้ดเดิมทุกจุด (predictor ของ thesis_ML_v2,
staff_unmask, dropdown สาขา→แพทย์, normalize ตอน import) อ่านไฟล์เดิม
path เดิม ผ่านฟังก์ชัน normalize ตัวเดิมเป๊ะ — เส้นทางเทียบชื่อไม่เปลี่ยนเลย

วิธีใช้:
    python staff_map_sync.py --upload   # รันครั้งเดียวจากเครื่อง รพ. (มีไฟล์จริง)
                                        # → สร้าง/แทนที่ตาราง staff_map บน Supabase
    แอปเรียก ensure_staff_mapping() เองตอนบูต (hook ใน main_or_app.main)

อัปเดตรายชื่อภายหลัง: แก้ staff_mapping.csv ที่เครื่อง รพ. แล้วรัน --upload ซ้ำ
"""
from __future__ import annotations

import csv
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(_DIR, 'staff_mapping.csv')
_COLS = ('role', 'masked_code', 'original_name')   # หัวคอลัมน์ตามไฟล์จริง

_failed = False          # DB พังครั้งเดียวจำไว้ — ไม่ลองซ้ำทุก rerun


def ensure_staff_mapping() -> str | None:
    """ตอนแอปบูต: มีไฟล์อยู่แล้ว → 'local' · ไม่มี → ดึงจาก Supabase มาเขียนไฟล์
    ('cloud') · ดึงไม่ได้ → None (แอปทำงานต่อแบบไม่เห็นตัวแพทย์ — เหมือนก่อนแก้)"""
    global _failed
    if os.path.exists(CSV_PATH):
        return 'local'
    if _failed:
        return None
    try:
        from main_or_db import get_conn
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT role, masked_code, original_name FROM staff_map").fetchall()
        finally:
            conn.close()
        if not rows:
            print("[staff_map_sync] ตาราง staff_map ว่าง — ยังไม่เคยรัน --upload จากเครื่อง รพ.")
            _failed = True
            return None
        with open(CSV_PATH, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(_COLS)
            w.writerows(rows)
        print(f"[staff_map_sync] ✅ สร้าง staff_mapping.csv จาก Supabase ({len(rows)} แถว)")
        return 'cloud'
    except Exception as ex:
        _failed = True
        print(f"[staff_map_sync] ดึงจาก DB ไม่ได้ (ข้าม — ระบบทำงานต่อได้): {ex}")
        return None


def upload_staff_mapping() -> int:
    """รันจากเครื่อง รพ.: อ่านไฟล์จริง → แทนที่ตาราง staff_map ทั้งตาราง (full refresh)"""
    if not os.path.exists(CSV_PATH):
        raise SystemExit(f"❌ ไม่พบ {CSV_PATH} — ต้องรันจากเครื่องที่มีไฟล์จริง")
    # 🧹 กรองก่อนขึ้น cloud (19 ก.ค. 2026 — มุคกี้พบชื่อหัตถการ/วินิจฉัย/ทีมห้องเล็กปน):
    #   ① เอาเฉพาะ role แพทย์ (surgeon/SURG) — scrub/circ ห้องเล็ก cloud ไม่ใช้
    #   ② ชื่อต้องมีอักษรไทย (ขยะจาก HIS เป็นอังกฤษล้วน: 'CKD III', 'Excision of...')
    #   ③ ตัด resident · ชื่อยาวผิดปกติ
    #   ⚠️ กรองเฉพาะตอนอัปโหลด — ไฟล์ CSV ต้นทางไม่ถูกแตะ (รหัสเก่าต้องคงอยู่
    #      เพื่อถอด log ย้อนหลังได้)
    import re as _re
    _TH = _re.compile(r'[ก-๙]')
    with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
        raw = [r for r in csv.DictReader(f) if (r.get('masked_code') or '').strip()]
    rows, skipped = [], 0
    for r in raw:
        name = (r.get('original_name') or '').strip()
        role = (r.get('role') or '').strip().lower()
        if (role in ('surgeon', 'surg') and _TH.search(name)
                and 'resident' not in name.lower() and len(name) < 60):
            rows.append((r['role'], r['masked_code'], name))
        else:
            skipped += 1
    print(f"กรองแล้ว: ขึ้น cloud {len(rows)} แถว · คัดออก {skipped} แถว "
          f"(ขยะ/ทีมห้องเล็ก/resident)")
    if not rows:
        raise SystemExit("❌ ไม่มีแถวที่ผ่านเกณฑ์ — ไม่อัปโหลด")
    from main_or_db import get_conn
    conn = get_conn()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS staff_map ("
                     "role TEXT, masked_code TEXT, original_name TEXT)")
        conn.execute("DELETE FROM staff_map")        # แทนที่ทั้งตาราง — แก้ชื่อ/ลบคนออกก็ตามไฟล์
        for r in rows:
            conn.execute("INSERT INTO staff_map (role, masked_code, original_name) "
                         "VALUES (?,?,?)", r)
        conn.commit()
    finally:
        conn.close()
    print(f"✅ อัปโหลด {len(rows)} แถวขึ้นตาราง staff_map แล้ว — "
          f"reboot แอปบน cloud หนึ่งรอบเพื่อให้ดึงไปใช้")
    return len(rows)


if __name__ == '__main__':
    import sys
    if '--upload' in sys.argv:
        upload_staff_mapping()
    else:
        print("ผลตรวจ:", ensure_staff_mapping() or "ไม่มีไฟล์และดึงจาก DB ไม่ได้")
