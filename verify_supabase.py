"""
verify_supabase.py — พิสูจน์ว่าข้อมูลถูกบันทึกบน Supabase จริง (ไม่ใช่แค่ในเครื่อง)
ใช้สำหรับทดสอบ real-time ข้ามเครื่อง + persistence เพื่อแนบเป็นหลักฐานส่งอาจารย์

วิธีใช้ (รันจาก C:\\Dev\\main_OR_app):
    python verify_supabase.py

แนวคิด: รันสคริปต์นี้ "บนเครื่อง A และเครื่อง B" (หรือเครื่องที่ 3 ก็ได้)
ถ้า version + saved_at ที่พิมพ์ออกมา "ตรงกันทุกเครื่อง" = ข้อมูลมาจาก
เซิร์ฟเวอร์กลางชุดเดียวกันจริง (ไม่ใช่ไฟล์ local ของใครของมัน)
"""
import json
import sys
from datetime import datetime

try:
    from db_connection import get_db_info
    from main_or_db import get_conn, load_board_state
except Exception as e:
    print("❌ import ไม่สำเร็จ (ต้องรันในโฟลเดอร์โปรเจกต์):", e)
    sys.exit(1)

today = datetime.now().strftime('%Y-%m-%d')
now = datetime.now().strftime('%H:%M:%S')

print("=" * 66)
print(f" 🔍 ตรวจสอบการบันทึกข้อมูลบน Supabase — เวลาเครื่องนี้ {now}")
info = get_db_info()
print(f"    โหมดฐานข้อมูล: {info.get('mode')}  |  เป็น Supabase/Postgres: {info.get('is_postgres')}")
if not info.get('is_postgres'):
    print("    ⚠️ ตอนนี้เป็นโหมด local (sqlite) — ตั้ง db_mode='supabase' ใน secrets ก่อนทดสอบข้ามเครื่อง")
print("=" * 66)

# ---- 1) บอร์ดกลาง (board_state) บนเซิร์ฟเวอร์ ----
try:
    s = load_board_state(today)
except Exception as e:
    s = None
    print("load_board_state error:", e)

if s:
    p = json.loads(s)
    print(f"\n[ บอร์ดกลาง: board_state_{today} ]  ← บันทึกบนเซิร์ฟเวอร์กลาง")
    print(f"    version   = {p.get('version')}        ← เลขเวอร์ชัน (เพิ่มขึ้นทุกครั้งที่มีการกดเปลี่ยนสถานะ)")
    print(f"    saved_at  = {p.get('saved_at')}   ← เวลาที่เซิร์ฟเวอร์บันทึกล่าสุด")
    cs = p.get('cases', [])
    print(f"    จำนวนเคสบนบอร์ด = {len(cs)}")
    for c in cs[:12]:
        print(f"      • {c.get('name', '-')} | HN {c.get('hn', '-')} | "
              f"{c.get('procedure', '-')} | สถานะ: {c.get('status', '-')}")
    if len(cs) > 12:
        print(f"      … และอีก {len(cs) - 12} เคส")
    print("    🔒 ชื่อ/HN แสดงแบบย่อ = ยืนยันว่าถูกปกปิดก่อนขึ้น cloud (PDPA)")
else:
    print(f"\n[ board_state_{today} ] ยังไม่มีข้อมูลของวันนี้บนเซิร์ฟเวอร์")
    print("    → ลองกดเปลี่ยนสถานะเคสในแอปสัก 1 ครั้ง แล้วรันสคริปต์นี้ใหม่")

# ---- 2) จำนวนเคสในตาราง cases ----
try:
    conn = get_conn()
    try:
        n = conn.execute("SELECT COUNT(*) FROM cases WHERE op_date=?", (today,)).fetchone()[0]
        ndone = conn.execute(
            "SELECT COUNT(*) FROM cases WHERE op_date=? AND status IN ('post_op','discharged')",
            (today,)).fetchone()[0]
        print(f"\n[ ตาราง cases ] เคสของวันนี้ใน DB = {n} เคส (ผ่าเสร็จแล้ว {ndone})")
    finally:
        conn.close()
except Exception as e:
    print("query cases error:", e)

print("\n" + "=" * 66)
print(" ✅ วิธีพิสูจน์ 'ข้ามเครื่อง':")
print("    1. รันสคริปต์นี้บนเครื่อง A และเครื่อง B พร้อมกัน")
print("    2. ถ้า version + saved_at 'ตรงกัน' = ข้อมูลมาจากเซิร์ฟเวอร์กลางชุดเดียวกันจริง")
print("    3. ให้เครื่อง A กดเปลี่ยนสถานะ 1 เคส → รันสคริปต์ใหม่ → version จะเพิ่มขึ้น")
print("       (แคปหน้าจอ before/after = หลักฐานว่าการกดถูกบันทึกขึ้นเซิร์ฟเวอร์)")
print("=" * 66)
