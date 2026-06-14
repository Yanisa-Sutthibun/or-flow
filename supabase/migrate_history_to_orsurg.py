"""
🔒 Bulk migrate ข้อมูลเก่า: local main_or.db → Supabase schema 'orsurg' (de-identified)

- ตัดคอลัมน์ name / hn / an ออก (ตัวระบุตัวผู้ป่วย — ไม่ขึ้น cloud)
- แปลง an → is_ipd (1 ถ้ามี AN = IPD, 0 = OPD)
- ส่งเข้าแบบ batch (execute_values) + ON CONFLICT DO NOTHING (กดซ้ำไม่เพิ่มซ้ำ)

ใช้:  python supabase/migrate_history_to_orsurg.py

หมายเหตุ: อ่าน database_url + db_schema จาก .streamlit/secrets.toml (ไม่ต้องใส่รหัสในไฟล์นี้)
"""
from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT / "main_or.db"
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"
BATCH = 1000
PII = {"name", "hn", "an"}


def _norm_is_ipd(an_value) -> int:
    """มี AN (ที่ไม่ว่าง) = IPD (1) · ไม่มี = OPD (0) — ไม่เก็บเลข AN"""
    s = str(an_value or "").strip()
    return 0 if s.upper() in ("", "NAN", "NONE", "-") else 1


def build_deidentified_rows(sqlite_path, target_cols):
    """อ่าน cases จาก SQLite → คืน (rows, n_ipd) แบบ de-identified ตาม target_cols
    target_cols = คอลัมน์ปลายทาง (orsurg) ที่ตัด name/hn/an/case_id ออกแล้ว และมี is_ipd
    """
    lite = sqlite3.connect(str(sqlite_path))
    try:
        local_cols = {r[1] for r in lite.execute("PRAGMA table_info(cases)").fetchall()}
        # คอลัมน์ที่อ่านตรงจาก local ได้ (ไม่รวม is_ipd ที่ต้อง derive)
        read_direct = [c for c in target_cols if c in local_cols and c != "is_ipd"]
        read_cols = read_direct + (["an"] if "an" in local_cols else [])
        raw = lite.execute(
            "SELECT %s FROM cases" % ",".join(read_cols)).fetchall()
    finally:
        lite.close()

    rows = []
    n_ipd = 0
    for r in raw:
        d = dict(zip(read_cols, r))
        ipd = _norm_is_ipd(d.get("an"))
        n_ipd += ipd
        rows.append(tuple(ipd if c == "is_ipd" else d.get(c) for c in target_cols))
    return rows, n_ipd, read_direct


def _load_cfg():
    import toml
    if not SECRETS_PATH.exists():
        print(f"❌ ไม่เจอ {SECRETS_PATH}")
        sys.exit(1)
    s = toml.load(SECRETS_PATH)
    url = (s.get("database_url") or "").strip()
    schema = (s.get("db_schema") or "orsurg").strip()
    if not url or "YOUR" in url.upper() or "[password" in url.lower():
        print("❌ ใส่ database_url จริงใน .streamlit/secrets.toml ก่อน")
        sys.exit(1)
    return url, schema


def main():
    if not SQLITE_PATH.exists():
        print(f"❌ ไม่เจอ {SQLITE_PATH}")
        sys.exit(1)
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        print("❌ ต้องติดตั้งก่อน:  pip install psycopg2-binary toml")
        sys.exit(1)

    url, schema = _load_cfg()
    print("═" * 60)
    print(f"🔒 Migrate ข้อมูลเก่า → Supabase schema '{schema}' (de-identified)")
    print("═" * 60)

    # 1) ต่อ orsurg + อ่านคอลัมน์ปลายทาง (ตัด PII + case_id ที่ auto)
    pg = psycopg2.connect(url)
    pg.autocommit = False
    cur = pg.cursor()
    cur.execute('SET search_path TO "%s", public' % schema.replace('"', ""))
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='cases' AND table_schema=current_schema() "
        "ORDER BY ordinal_position")
    orsurg_cols = [r[0] for r in cur.fetchall()]
    if not orsurg_cols:
        print(f"❌ ไม่เจอตาราง cases ใน schema '{schema}' — รัน schema_postgres.sql ก่อน")
        sys.exit(1)
    target = [c for c in orsurg_cols if c not in PII and c != "case_id"]
    if PII & set(target):
        print(f"❌ orsurg ยังมีคอลัมน์ PII: {PII & set(target)} — รัน schema ใหม่ก่อน")
        sys.exit(1)
    if "is_ipd" not in target:
        print("❌ orsurg ยังไม่มีคอลัมน์ is_ipd — รัน schema_postgres.sql ฉบับใหม่ก่อน")
        sys.exit(1)

    # 2) อ่าน local + แปลง de-identified
    rows, n_ipd, used = build_deidentified_rows(SQLITE_PATH, target)
    print(f"📥 อ่านจาก local: {len(rows):,} เคส")
    print(f"   ย้าย {len(target)} คอลัมน์ · 🔒 ตัด name/hn/an · an → is_ipd")
    print(f"   is_ipd=1 (IPD): {n_ipd:,} · is_ipd=0 (OPD): {len(rows) - n_ipd:,}")

    # 3) ยืนยันก่อนเขียน
    ans = input(
        f"\n➡️  จะเขียน {len(rows):,} เคสเข้า '{schema}.cases' บน Supabase · "
        f"พิมพ์ 'yes' เพื่อยืนยัน: ").strip().lower()
    if ans != "yes":
        print("ยกเลิก")
        pg.close()
        return

    # 4) batch insert (กันซ้ำด้วย unique index ที่มีอยู่)
    collist = ",".join('"' + c + '"' for c in target)
    sql = f"INSERT INTO cases ({collist}) VALUES %s ON CONFLICT DO NOTHING"
    done = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        execute_values(cur, sql, chunk, page_size=BATCH)
        done += len(chunk)
        print(f"   ... {done:,}/{len(rows):,}")
    pg.commit()

    cur.execute("SELECT COUNT(*) FROM cases")
    total = cur.fetchone()[0]
    pg.close()
    print(f"\n✅ เสร็จ · '{schema}.cases' ตอนนี้มี {total:,} แถว (de-identified)")


if __name__ == "__main__":
    main()
