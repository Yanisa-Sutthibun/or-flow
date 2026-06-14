# -*- coding: utf-8 -*-
"""purge_board_state.py — ลบ snapshot บอร์ดกลาง (board_state_*) ออกจาก Supabase
ใช้ครั้งเดียวหลังเหตุ PII 11 มิ.ย. 2026 (ชื่อ/HN เต็มขึ้น cloud ช่วงทดสอบ 10:35 น.)
และใช้ซ้ำได้ทุกเมื่อที่อยากล้าง snapshot เก่า

วิธีใช้ (รันบนเครื่องที่มี .streamlit/secrets.toml ตัวจริง):
    python purge_board_state.py            # ดูรายการก่อน แล้วถามยืนยันก่อนลบ
    python purge_board_state.py --yes      # ลบเลยไม่ถาม
"""
import re
import sys
from pathlib import Path

SECRETS = Path(__file__).parent / '.streamlit' / 'secrets.toml'


def _read_key(txt: str, key: str) -> str:
    m = re.search(rf'^{key}\s*=\s*"([^"]*)"', txt, re.M)
    return m.group(1) if m else ''


def main() -> None:
    txt = SECRETS.read_text(encoding='utf-8')
    url = _read_key(txt, 'database_url')
    schema = _read_key(txt, 'db_schema') or 'public'
    mode = _read_key(txt, 'db_mode')
    if mode != 'supabase' or not url:
        sys.exit('db_mode ไม่ใช่ supabase หรือไม่มี database_url — ไม่มีอะไรต้องลบบน cloud')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', schema):
        sys.exit(f'db_schema ไม่ปลอดภัย: {schema!r}')

    import psycopg2  # มีอยู่แล้วบนเครื่องที่รันแอปโหมด supabase
    conn = psycopg2.connect(url, connect_timeout=15)
    try:
        cur = conn.cursor()
        cur.execute(f'SET search_path TO "{schema}", public')
        cur.execute(
            "SELECT key, length(value) FROM app_settings "
            "WHERE key LIKE 'board_state_%' ORDER BY key")
        rows = cur.fetchall()
        if not rows:
            print('✅ ไม่พบ board_state_* บน Supabase — สะอาดอยู่แล้ว')
            return
        print(f'พบ {len(rows)} key:')
        for k, ln in rows:
            print(f'  - {k} ({ln:,} bytes)')
        if '--yes' not in sys.argv:
            ans = input('ลบทั้งหมด? (พิมพ์ yes): ').strip().lower()
            if ans != 'yes':
                print('ยกเลิก — ไม่ได้ลบอะไร')
                return
        cur.execute("DELETE FROM app_settings WHERE key LIKE 'board_state_%'")
        conn.commit()
        cur.execute(
            "SELECT count(*) FROM app_settings WHERE key LIKE 'board_state_%'")
        left = cur.fetchone()[0]
        print(f'🗑 ลบแล้ว {len(rows)} key · เหลือ {left} (ต้องเป็น 0)')
        if left == 0:
            print('✅ เรียบร้อย — snapshot ที่มีข้อมูลผู้ป่วยถูกลบออกจาก cloud แล้ว')
            print('   (บอร์ดที่เซฟหลังจากนี้เป็นข้อมูล mask เสมอตามโค้ดเวอร์ชันใหม่)')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
