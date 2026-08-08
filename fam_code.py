"""
fam_code.py — รหัสผู้รับบริการสำหรับจอญาติ (แหล่งเดียวของทั้งระบบ เหมือน room_config.py)

ใช้แทนการโชว์ HN บนจอญาติ: รหัส 1 ตัวอักษร + 3 หลัก เช่น "B482"
สุ่มแบบ deterministic จาก seed (โดยปกติคือ case['id']) → เคสเดียวกันได้รหัสเดิมตลอดวัน
แม้อัปโหลดไฟล์ซ้ำหรือหน้าจอ refresh (เพราะ id เป็น deterministic hash ของเนื้อเคสอยู่แล้ว)
ไม่ผูกกับ HN จริง จึงเดา HN จากรหัสนี้ย้อนกลับไม่ได้
"""
import random

_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # ตัด I, O ออก กันสับสนกับเลข 1, 0 บนจอทีวี


def gen_fam_code(seed) -> str:
    """สุ่มรหัส 1 ตัวอักษร + 3 หลัก (เช่น 'B482') แบบ deterministic จาก seed"""
    rng = random.Random(str(seed or ''))
    letter = rng.choice(_LETTERS)
    digits = rng.randrange(1000)
    return f"{letter}{digits:03d}"
