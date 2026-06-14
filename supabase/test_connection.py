"""
🩺 Test Supabase Connection — เช็คก่อน migrate
ใช้: python supabase/test_connection.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    import psycopg2
    import toml
except ImportError as e:
    print(f"❌ Missing package: {e}")
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"


def main() -> None:
    print("═" * 60)
    print("🩺 Supabase Connection Test")
    print("═" * 60)

    if not SECRETS_PATH.exists():
        print(f"❌ ไม่เจอ {SECRETS_PATH}")
        sys.exit(1)

    secrets = toml.load(SECRETS_PATH)
    url = secrets.get("database_url", "").strip()

    if not url or "YOUR_PASSWORD_HERE" in url:
        print("❌ database_url ยังเป็น placeholder — แก้ใน secrets.toml ก่อน")
        sys.exit(1)

    # Parse + แสดงให้ดู (mask password)
    parsed = urlparse(url)
    pwd = parsed.password or ""
    masked_pwd = f"{pwd[:2]}...{pwd[-2:]}" if len(pwd) > 4 else "***"

    print(f"📋 Parsed URL:")
    print(f"   - scheme    : {parsed.scheme}")
    print(f"   - user      : {parsed.username}")
    print(f"   - password  : {masked_pwd}  (len={len(pwd)})")
    print(f"   - host      : {parsed.hostname}")
    print(f"   - port      : {parsed.port}")
    print(f"   - database  : {parsed.path.lstrip('/')}")
    print()

    # ตรวจ special chars ใน password
    special_chars = set("@#/:?&%+ ")
    found_special = [c for c in pwd if c in special_chars]
    if found_special:
        print(f"⚠️  Password มีอักขระพิเศษ: {set(found_special)}")
        print(f"   → ต้อง URL-encode (@→%40, #→%23, /→%2F, :→%3A, ?→%3F, &→%26, %→%25)")
        print()

    # ลองเชื่อม
    print("🔌 ทดสอบเชื่อมต่อ...", end=" ", flush=True)
    try:
        conn = psycopg2.connect(url, connect_timeout=10)
        print("✅")
        cur = conn.cursor()
        cur.execute("SELECT current_user, current_database(), version()")
        user, db, ver = cur.fetchone()
        print(f"\n✅ เชื่อมต่อสำเร็จ!")
        print(f"   - User     : {user}")
        print(f"   - Database : {db}")
        print(f"   - Version  : {ver.split(',')[0]}")

        # นับ tables — ใช้ schema ของแอป (orsurg) ไม่ใช่ public
        # 🔒 นับคอลัมน์แบบ filter ตาม schema ด้วย (ไม่งั้นจะนับซ้ำข้าม schema → เลขเบิ้ล)
        _schema = (secrets.get("db_schema") or "orsurg").strip()
        cur.execute("""
            SELECT t.table_name,
                   (SELECT COUNT(*) FROM information_schema.columns c
                    WHERE c.table_name = t.table_name
                      AND c.table_schema = t.table_schema) AS cols
            FROM information_schema.tables t
            WHERE t.table_schema = %s
            ORDER BY t.table_name
        """, (_schema,))
        tables = cur.fetchall()
        print(f"\n📊 พบ {len(tables)} tables ใน schema '{_schema}':")
        for name, cols in tables:
            print(f"   - {name:20s}  ({cols} columns)")

        # เตือนถ้ามีตารางเก่าค้างใน public (จากตอนตั้งค่าก่อนแยก schema)
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN
              ('cases','override_log','audit_log','prediction_log',
               'backup_log','room_settings','app_settings')
            ORDER BY table_name
        """)
        _pub = [r[0] for r in cur.fetchall()]
        if _pub:
            print(f"\n⚠️  พบตารางชื่อซ้ำใน schema 'public' (อาจเป็นของเก่าก่อนแยก schema): {_pub}")
            print("   → แอปใช้ orsurg อยู่แล้ว · ถ้า public เป็นของเก่า/ของ minor ให้ตรวจก่อนลบ")

        conn.close()
        print("\n🎉 พร้อม migrate! รัน: python supabase/migrate_to_supabase.py")

    except psycopg2.OperationalError as e:
        print("❌")
        err = str(e).strip()
        print(f"\n❌ Error:\n   {err}\n")

        if "password authentication failed" in err.lower():
            print("💡 สาเหตุที่เป็นไปได้:")
            print("   1. Password ผิด → reset ที่ Supabase Dashboard → Settings → Database")
            print("   2. Password มีอักขระพิเศษ → ต้อง URL-encode")
            print("   3. Copy ผิด → มี space/newline หลุดมา")
        elif "could not translate" in err.lower() or "no such host" in err.lower():
            print("💡 host ผิด — ตรวจสอบ project ref ใน URL")
        elif "timeout" in err.lower():
            print("💡 timeout — ตรวจสอบ internet หรือ firewall")

        sys.exit(1)


if __name__ == "__main__":
    main()
