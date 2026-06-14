"""
check_cases_columns.py — ตรวจว่าคอลัมน์ใน cloud (orsurg.cases) ครบที่โค้ดต้องใช้ไหม
ใช้หลังลบ/แก้คอลัมน์ใน Supabase · อ่าน database_url จาก .streamlit/secrets.toml
ใช้:  python supabase/check_cases_columns.py
หมายเหตุ (2026-06): ถอด 7 คอลัมน์ออกแล้ว → EXPECTED/CRITICAL ตรง schema ใหม่ (33 คอลัมน์)
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".streamlit" / "secrets.toml"

EXPECTED = [
    "case_id", "op_date", "is_ipd", "diagnosis", "procedure_name", "surgeon_name",
    "division_code", "case_category", "patient_type", "op_type", "estimated_time",
    "procnote", "status", "cancel_reason", "ai_predicted_min", "user_override_min",
    "actual_duration_min", "scrub_nurse", "circ_nurse", "anesthesia_type", "wait_min",
    "room_no", "arrived_at", "in_or_at", "op_end_at", "discharged_at", "post_op_dest",
    "scheduled_surgeon", "age", "ai_predicted_min_legacy", "ai_model_ver",
    "created_at", "updated_at",
]

CRITICAL = {
    "case_id", "op_date", "is_ipd", "diagnosis", "procedure_name", "surgeon_name",
    "scheduled_surgeon", "division_code", "case_category", "patient_type", "op_type",
    "estimated_time", "procnote", "anesthesia_type", "status", "ai_predicted_min",
    "actual_duration_min", "scrub_nurse", "circ_nurse", "wait_min", "room_no",
    "arrived_at", "in_or_at", "op_end_at", "discharged_at", "age",
    "ai_predicted_min_legacy", "ai_model_ver",
}


def main():
    try:
        import psycopg2
    except ImportError:
        print("ต้องติดตั้งก่อน: pip install psycopg2-binary toml"); sys.exit(1)
    import toml
    s = toml.load(SECRETS)
    url = (s.get("database_url") or "").strip()
    schema = (s.get("db_schema") or "orsurg").strip()
    if not url:
        print("ไม่มี database_url ใน secrets.toml"); sys.exit(1)

    pg = psycopg2.connect(url)
    cur = pg.cursor()
    cur.execute('SET search_path TO "%s", public' % schema.replace('"', ""))
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='cases' AND table_schema=current_schema()")
    current = {r[0] for r in cur.fetchall()}
    pg.close()

    if not current:
        print("ไม่เจอตาราง cases ใน schema '%s'" % schema); sys.exit(1)

    missing = [c for c in EXPECTED if c not in current]
    extra = sorted(current - set(EXPECTED))
    missing_critical = [c for c in missing if c in CRITICAL]
    missing_ok = [c for c in missing if c not in CRITICAL]

    print("=" * 60)
    print("ตรวจคอลัมน์ orsurg.cases - มีจริง %d / ควรมี %d" % (len(current), len(EXPECTED)))
    print("=" * 60)
    if not missing:
        print("OK คอลัมน์ครบทุกตัว - แอปทำงานได้ปกติ")
    else:
        if missing_critical:
            print("\n[!] ลบคอลัมน์สำคัญที่โค้ดใช้ (%d) - แอปจะพัง ควรเพิ่มคืน:" % len(missing_critical))
            for c in missing_critical:
                print("    - " + c)
        if missing_ok:
            print("\n[~] ลบคอลัมน์ที่ไม่ค่อยใช้ (%d) - น่าจะไม่กระทบหลัก:" % len(missing_ok))
            for c in missing_ok:
                print("    - " + c)
    if extra:
        print("\n[i] มีคอลัมน์เกินจาก schema (%d): %s" % (len(extra), extra))
    if missing_critical:
        print("\n-> เพิ่มคืนด้วย ALTER TABLE cases ADD COLUMN ...")


if __name__ == "__main__":
    main()
