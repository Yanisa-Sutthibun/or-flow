"""
room_config.py — แหล่งข้อมูลห้องผ่าตัดกลาง (single source of truth)
====================================================================
ตึกใหม่ (ตั้งแต่ 1 มี.ค. 2569 = 2026-03-01): 9 ห้อง รหัส orroom 90–98
ตึกเก่า (ก่อน 1 มี.ค. 2569): รหัส 1, 3, 4, 5

ใช้ร่วมกันทั้ง dashboard (main_or_db.get_room_status/get_kpi),
การ์ดห้อง (main_or_admin), และ import (main_or_db.import_schedule)
"""
from __future__ import annotations

# วันย้ายเข้าตึกใหม่ (ISO date — เทียบเป็น string ได้เพราะ op_date เก็บเป็น YYYY-MM-DD)
MOVE_DATE = "2026-03-01"

# ---- ตึกใหม่: 9 ห้อง (รหัส orroom ในไฟล์ HIS = 90–98) ✅ ยืนยันโดยหัวหน้า 2026-06 ----
NEW_BUILDING_ROOMS = [90, 91, 92, 93, 94, 95, 96, 97, 98]
ROOM_INFO = {
    90: ("OR1", "SCOPE"),    91: ("OR2", "EM"),      92: ("OR3", "URO"),
    93: ("OR4", "GEN"),      94: ("OR5", "VAS"),     95: ("OR6", "NEURO"),
    96: ("OR7", "PLASTIC"),  97: ("OR8", "ENT"),     98: ("OR9", "GEN&ENT"),
}

# ---- ตึกเก่า (คงไว้ดูข้อมูลย้อนหลังก่อนย้าย) ----
OLD_BUILDING_ROOMS = [1, 3, 4, 5]

SPECIALTY_FULL = {
    "GEN": "ศัลย์ทั่วไป", "NEURO": "ประสาท/สมอง", "ENT": "หู คอ จมูก",
    "PLASTIC": "ตกแต่ง", "URO": "ทางเดินปัสสาวะ", "VAS": "หลอดเลือด",
    "EM": "ฉุกเฉิน", "SCOPE": "ส่องกล้อง",
    "GEN&ENT": "ศัลย์ทั่วไป/หู คอ จมูก",
}


def room_label(room_no) -> str:
    """ป้ายแสดงบนการ์ด เช่น 'OR1 · SCOPE' — ถ้าไม่รู้จักคืน 'ห้อง {n}'"""
    try:
        r = int(float(room_no))
    except (TypeError, ValueError):
        return f"ห้อง {room_no}"
    if r in ROOM_INFO:
        name, spec = ROOM_INFO[r]
        return f"{name} · {spec}"
    return f"ห้อง {r}"


def get_active_rooms(op_date: str | None = None) -> list:
    """คืนรายการห้องตามวันที่: ตึกใหม่ถ้า op_date >= วันย้าย, ไม่งั้นตึกเก่า
    (ถ้าไม่ส่ง op_date = ใช้ตึกใหม่ ซึ่งเป็นค่าปัจจุบัน)"""
    if op_date and str(op_date) < MOVE_DATE:
        return list(OLD_BUILDING_ROOMS)
    return list(NEW_BUILDING_ROOMS)


# ============================================================
# Room mapping เก่า↔ใหม่ (สำหรับ ML fine-tune ข้ามตึก)
# ============================================================
# หมายเหตุสำคัญ: ตึกใหม่จัดห้อง/specialty ใหม่หมด ไม่มี mapping 1:1 เชิงกายภาพ
#   → วิธีที่ "ข้ามตึกได้" จริงคือใช้ 'division' (specialty) ซึ่งโมเดลใช้เป็น feature อยู่แล้ว
#   ฟังก์ชันด้านล่างไว้สร้าง feature specialty ที่ consistent ทั้งสองตึก (ถ้าต้องการ)

# รหัสห้อง HIS ตึกเก่า (ในข้อมูล train ปี 64–67) → specialty
# มาจาก division ที่พบบ่อยสุดในแต่ละห้องจากข้อมูลจริง (ควรให้พยาบาล OR ยืนยัน)
OLD_HIS_ROOM_INFO = {
    11: "GEN",   12: "NEURO", 13: "GEN",   14: "URO",
    15: "ENT",   16: "PLASTIC", 17: "VAS",
}

# division code → specialty (ยืนยันจากข้อมูลปี 69: ห้องใหม่ 90–97 + division ที่พบบ่อย)
DIVISION_SPECIALTY = {
    1: "GEN", 2: "NEURO", 3: "ENT", 4: "PLASTIC",
    5: "URO", 6: "GEN", 7: "VAS", 9: "GEN",
}


def room_specialty(orroom) -> str:
    """specialty ของห้อง — ครอบทั้งตึกใหม่ (90–97) และตึกเก่า HIS (11–17)
    ใช้เป็น feature ข้ามตึกได้ ถ้าไม่รู้จักคืน 'UNKNOWN'"""
    try:
        r = int(float(orroom))
    except (TypeError, ValueError):
        return "UNKNOWN"
    if r in ROOM_INFO:
        return ROOM_INFO[r][1]          # ตึกใหม่ 90–97
    if r in OLD_HIS_ROOM_INFO:
        return OLD_HIS_ROOM_INFO[r]     # ตึกเก่า 11–17
    return "UNKNOWN"


def division_specialty(division) -> str:
    """specialty จาก division code — building-independent (แนะนำใช้ตัวนี้เป็นหลัก)"""
    try:
        d = int(float(division))
    except (TypeError, ValueError):
        return "UNKNOWN"
    return DIVISION_SPECIALTY.get(d, "UNKNOWN")
