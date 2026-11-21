"""
👩‍⚕️ backfill_nurses_cloud.py — เติมชื่อพยาบาล (scrub/circ) จากไฟล์ intraop ขึ้น cloud
═══════════════════════════════════════════════════════════════════════
ทำอะไร:
  1. reimport_timestamps(intraop) — จับคู่เคสเดิมด้วย (วันที่ + ห้อง + เวลาเข้าห้อง)
     แล้วเติม scrub_nurse / circ_nurse (+ เวลา/หมอ) ที่ยังว่าง
  2. mask_unmasked_staff() — แปลงชื่อจริงทุก role (หมอ/scrub/circ) → รหัส (PDPA)

ใช้กับเฉพาะปีที่มีไฟล์ intraop (เช่น 68, 69) · ปีที่ไม่มีไฟล์จะยังว่าง (ต้นทางไม่มี)
หมายเหตุ: เขียนลง DB ตาม db_mode ใน secrets (supabase) — ใช้ connection/รหัสของมุ้กกเอง

ใช้:
  python supabase/backfill_nurses_cloud.py  <intraopปี68.xls>  <intraopปี69.xls> --dry-run   # นับอย่างเดียว ไม่เขียน
  python supabase/backfill_nurses_cloud.py  <intraopปี68.xls>  <intraopปี69.xls>             # เขียนจริง + mask
🧪 22 พ.ย. 2026 (มุกกี้สั่ง ให้แท็บ Data analysis ใช้ชื่อพยาบาลจาก intraop ปี 68-69):
   เพิ่ม --dry-run เพราะฐานข้อมูลชุด 1 ม.ค. 68 ถึง 21 พ.ค. 69 (year68_69_completed.csv) ไม่มีคอลัมน์ชื่อพยาบาล
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    dry = '--dry-run' in sys.argv
    files = [a for a in sys.argv[1:] if a and not a.startswith('--')]
    if not files:
        print("ใช้:  python supabase/backfill_nurses_cloud.py <ไฟล์ intraop> [เพิ่มได้หลายไฟล์]")
        sys.exit(1)

    try:
        from import_historical import reimport_timestamps
        from main_or_db import mask_unmasked_staff
    except Exception as e:
        print(f"❌ import ไม่สำเร็จ: {e}")
        sys.exit(1)

    print("═" * 60)
    print("👩‍⚕️ Backfill ชื่อพยาบาล (scrub/circ) → cloud + mask (PDPA)")
    print("═" * 60)

    total_updated = 0
    for p in files:
        if not Path(p).exists():
            print(f"  ❌ ไม่เจอไฟล์: {p}")
            continue
        print(f"\n→ {Path(p).name}")
        try:
            res = reimport_timestamps(p, dry_run=dry)
            if dry:
                n_match = len(res.get('samples') or [])
                total_updated += n_match
                print(f"   [DRY-RUN] จับคู่เคสในฐานข้อมูลได้ {n_match} เคส จาก {res.get('total', 0)} แถว · "
                      f"ไม่เจอใน DB {res.get('not_found', 0)} แถว (ยังไม่เขียนอะไร)")
                continue
            up = res.get("updated", 0)
            total_updated += up
            print(f"   เติมเวลา/พยาบาล: อัปเดต {up} เคส · "
                  f"ไม่เจอใน DB {res.get('not_found', 0)} เคส")
        except Exception as e:
            print(f"   ⚠️ ข้าม (error): {e}")

    if dry:
        print(f"\n[DRY-RUN] รวมจับคู่ได้ {total_updated} เคส · ยังไม่เขียนฐานข้อมูล ถ้าตัวเลขโอเค รันซ้ำโดยไม่ใส่ --dry-run")
        return
    print("\n🎭 mask ชื่อหมอ/พยาบาลจริง → รหัส ...")
    try:
        n = mask_unmasked_staff()
        print(f"✅ mask {n} ชื่อ → รหัส (PDPA)")
    except Exception as e:
        print(f"⚠️ mask ไม่สำเร็จ: {e}")

    print(f"\nเสร็จ · อัปเดตรวม {total_updated} เคส")
    print("ตรวจได้ที่ Supabase → orsurg.cases → scrub_nurse/circ_nurse ควรเป็น SCRUB_xxx/CIRC_xxx")


if __name__ == "__main__":
    main()
