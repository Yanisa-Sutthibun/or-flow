"""
🎭 mask_surgeons_cloud.py — แทนชื่อบุคลากรจริงบน Supabase ด้วยรหัส (PDPA)
═══════════════════════════════════════════════════════════════════════
   SURG_xxx (หมอ) · SCRUB_xxx (พยาบาลส่งเครื่องมือ) · CIRC_xxx (พยาบาลวิ่ง)

ทำไม: cloud ไม่ควรเก็บชื่อบุคลากรจริง — เก็บเป็นรหัส แล้ว unmask ตอนแสดงด้วย staff_mapping.csv

ทำอะไร:
  1. ดึงชื่อจริง (ที่ยังไม่ใช่รหัส) จาก cases.surgeon_name/scheduled_surgeon/
     scrub_nurse/circ_nurse และ prediction_log.surgeon_name
  2. ให้รหัสตาม role — ใช้รหัสเดิมจาก staff_mapping.csv ถ้าชื่อตรง, ที่เหลือสร้างใหม่
  3. UPDATE บน cloud → เป็นรหัส  · 4. เซฟ staff_mapping.csv ครบถ้วน

ปลอดภัย: dry-run + ถาม yes ก่อนเขียน · ไม่ print ชื่อจริงออกจอ
         อ่าน database_url จาก .streamlit/secrets.toml (ไม่ต้องใส่รหัสในไฟล์นี้)

ใช้:  python supabase/mask_surgeons_cloud.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".streamlit" / "secrets.toml"
MAPPING = ROOT / "staff_mapping.csv"

# role -> [(table, column), ...]
ROLE_TARGETS = {
    "SURG":  [("cases", "surgeon_name"), ("cases", "scheduled_surgeon"),
              ("prediction_log", "surgeon_name")],
    "SCRUB": [("cases", "scrub_nurse")],
    "CIRC":  [("cases", "circ_nurse")],
}


def _load_cfg():
    import toml
    if not SECRETS.exists():
        print(f"❌ ไม่เจอ {SECRETS}"); sys.exit(1)
    s = toml.load(SECRETS)
    url = (s.get("database_url") or "").strip()
    schema = (s.get("db_schema") or "orsurg").strip()
    if not url or "YOUR" in url.upper() or "[password" in url.lower():
        print("❌ ใส่ database_url จริงใน .streamlit/secrets.toml ก่อน"); sys.exit(1)
    return url, schema


def _load_rows():
    if MAPPING.exists():
        with open(MAPPING, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    return []


def _name2code_max(rows, role):
    pref = role + "_"
    n2c, mx = {}, 0
    for r in rows:
        code = (r.get("masked_code") or "").strip()
        nm = (r.get("original_name") or "").strip()
        if code.startswith(pref) and nm:
            n2c[nm] = code
            try:
                mx = max(mx, int(code.split("_")[1]))
            except ValueError:
                pass
    return n2c, mx


def main():
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        print("❌ ต้องติดตั้งก่อน:  pip install psycopg2-binary toml"); sys.exit(1)

    url, schema = _load_cfg()
    rows = _load_rows()

    print("═" * 60)
    print("🎭 Mask ชื่อหมอ+พยาบาลบน Supabase → รหัส (PDPA)")
    print("═" * 60)

    pg = psycopg2.connect(url)
    pg.autocommit = False
    cur = pg.cursor()
    cur.execute('SET search_path TO "%s", public' % schema.replace('"', ""))

    plan = {}  # role -> (name2code, new_entries, real_count)
    for role, targets in ROLE_TARGETS.items():
        is_code = re.compile(r"^%s_\d+$" % role)
        n2c, mx = _name2code_max(rows, role)
        real = set()
        for tbl, col in targets:
            try:
                cur.execute(f"SELECT DISTINCT {col} FROM {tbl} "
                            f"WHERE {col} IS NOT NULL AND TRIM({col}) <> ''")
                for (v,) in cur.fetchall():
                    v = (v or "").strip()
                    if v and not is_code.match(v):
                        real.add(v)
            except psycopg2.Error:
                pg.rollback()
        new, n = [], mx
        for nm in sorted(real):
            if nm not in n2c:
                n += 1
                n2c[nm] = f"{role}_{n:03d}"
                new.append({"role": role, "masked_code": n2c[nm], "original_name": nm})
        plan[role] = (n2c, new, len(real))

    if sum(v[2] for v in plan.values()) == 0:
        print("✅ ไม่มีชื่อจริงค้างบน cloud แล้ว — mask ครบเรียบร้อย")
        pg.close(); return

    for role, (_n2c, new, cnt) in plan.items():
        if cnt:
            print(f"  {role}: จะ mask {cnt} ชื่อ (ใช้รหัสเดิม {cnt - len(new)} · ใหม่ {len(new)})")
    if input("\n➡️  พิมพ์ 'yes' เพื่อยืนยันการแก้ข้อมูลบน cloud: ").strip().lower() != "yes":
        print("ยกเลิก"); pg.close(); return

    total, all_new = 0, []
    for role, targets in ROLE_TARGETS.items():
        n2c, new, cnt = plan[role]
        if not cnt:
            continue
        pairs = [(nm, code) for nm, code in n2c.items()]
        for tbl, col in targets:
            try:
                execute_values(
                    cur,
                    f"UPDATE {tbl} SET {col} = m.code "
                    f"FROM (VALUES %s) AS m(nm, code) WHERE {tbl}.{col} = m.nm",
                    pairs, page_size=500)
                total += cur.rowcount
            except psycopg2.Error as e:
                pg.rollback(); print(f"⚠️ ข้าม {tbl}.{col}: {e}")
        all_new += new
    pg.commit()

    allrows = rows + all_new
    with open(MAPPING, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["role", "masked_code", "original_name"])
        w.writeheader()
        for r in allrows:
            w.writerow({"role": r.get("role", "SURG"),
                        "masked_code": r["masked_code"],
                        "original_name": r["original_name"]})

    left = 0
    for role, targets in ROLE_TARGETS.items():
        for tbl, col in targets:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IS NOT NULL "
                            f"AND TRIM({col}) <> '' AND {col} !~ '^{role}_[0-9]+$'")
                left += cur.fetchone()[0]
            except psycopg2.Error:
                pg.rollback()
    pg.close()
    print(f"\n✅ อัปเดต {total} แถว · เหลือชื่อจริงที่ยังไม่ mask: {left} (ควร 0)")
    print(f"   mapping เซฟที่ {MAPPING} ({len(allrows)} รายการ) — ใช้ unmask ตอนแสดง")
    print("   ⚠️ อย่า commit staff_mapping.csv ขึ้น git (gitignored อยู่แล้ว)")


if __name__ == "__main__":
    main()
