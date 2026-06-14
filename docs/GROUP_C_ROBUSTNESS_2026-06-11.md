# Major กลุ่ม C — ความทนทานระบบ (M-02 / M-09 / M-10)

วันที่: 11 มิ.ย. 2026

## M-02 — Connection leak → pool 12 เส้นหมด → แอปล่มทั้งเครื่อง
**ปัญหา:** ฟังก์ชัน read หลายตัว `conn = get_conn()` แล้วไม่มี try/finally → ถ้า query throw
connection ไม่คืน pool → สะสมจนเต็ม (12) → ทั้งเครื่องเชื่อม DB ไม่ได้

**แก้:**
- เพิ่ม **decorator `@with_conn`** + context manager `db_session()` ใน `main_or_db.py`
  → เปิด connection ส่งเป็น arg แรก แล้ว **ปิดใน finally เสมอ** (exception ก็ไม่ leak)
  ครอบฟังก์ชัน hot-path: `get_summary` · `get_room_status` · `get_kpi` · `get_workload` · `import_schedule`
  (callers ไม่ต้องแก้ — wrapper inject conn ให้ ลายเซ็นเดิมใช้ได้)
- `db_connection.py`: ตอน pool getconn ล้มเหลวแล้ว rebuild → เรียก **`pool.closeall()`** ปิด
  connection ของ pool เก่าทั้งหมดก่อน (กันค้างฝั่ง Supabase นับชนเพดาน)
- ที่เหลือมี safety net `_PgConnection.__del__` คืน connection ตอน GC อยู่แล้ว

## M-09 — บอร์ดเซฟล้มเหลวเงียบ แต่ caption โชว์ "ซิงก์ทุกเครื่อง" เสมอ
**แก้:** `_save_board_snapshot` เช็ก return ของ `save_board_state`
- สำเร็จ → รีเซ็ต `_board_db_fail = 0`
- ล้มเหลว (False/exception) → `_board_db_fail += 1`
- บนบอร์ด: ถ้า fail ติดกัน > 2 → `st.warning("⚠️ บอร์ดกลางออฟไลน์ — เครื่องนี้ยังไม่แชร์...")`
  แทนข้อความ "ซิงก์ทุกเครื่อง" (ไม่โกหกผู้ใช้)

## M-10 — เปิดจอข้ามเที่ยงคืน → เคสเมื่อวานถูกเซฟด้วย key วันใหม่
**แก้:** `page_or_board` เก็บ `_board_last_date`
- ถ้า ≠ วันนี้ (ข้ามเที่ยงคืน) → ล้าง `patient_cases` + รีเซ็ต dirty/version + บังคับ `_board_force_pull`
  → ดึงบอร์ด "วันนี้" สดแทน ไม่เอาเคสเมื่อวานมาปน

## ไฟล์ที่แก้ (compile ผ่านทั้งหมด)
`main_or_db.py` · `db_connection.py` · `main_or_pages.py`

## ก่อน commit (บน Windows)
```powershell
python -m py_compile main_or_db.py db_connection.py main_or_pages.py
git add main_or_db.py db_connection.py main_or_pages.py docs/GROUP_C_ROBUSTNESS_2026-06-11.md
git commit -m "fix(robustness): กลุ่ม C — M-02 conn leak (with_conn + closeall) + M-09 board offline warning + M-10 midnight rollover"
```

## หมายเหตุ
- `@with_conn` ครอบฟังก์ชัน hot-path 5 ตัวที่รีวิวระบุ (ที่ถูกเรียกทุก render) ส่วน read อื่นๆ
  พึ่ง `__del__` safety net + closeall — ถ้าต้องการความเข้มขึ้น ค่อยทยอยครอบ `@with_conn` เพิ่มได้
