# Major กลุ่ม D — รายงาน/ตัวชี้วัด/เครื่องมือลบ (M-07 / M-08 / M-03)

วันที่: 11 มิ.ย. 2026

## M-07 — Excel export อ่าน key ที่ get_summary ไม่เคยคืน
**ปัญหา:** อ่าน `total_treatment`/`total_revenue`/`total_patho` (มรดก Minor OR) → โชว์ 0 บาท ·
อ่าน `ai_accuracy` ที่ไม่มี → ตาราง AI หายทั้งแผ่น
**แก้ (`main_or_export.py`):** ตัดแถวการเงิน/ชิ้นเนื้อออก + คำนวณ MAE/MAPE/±15/±30 จาก
`summary['ai_df']` ที่ get_summary คืนมาจริง

## M-08 — utilization 3 นิยาม 3 หน้า → เลือกนิยามเดียว ✅ (มุ้กกเลือก A)
**นิยามมาตรฐาน (ทั้งระบบ):** utilization = เวลาที่ห้องถูกใช้ในช่วง **8:00–16:00 (clip รายห้อง-วัน)**
÷ (จำนวนห้อง × 480 นาที) → **util ≤ 100% เสมอ** · turnover นับเฉพาะช่วง **1–90 นาที**
- เพิ่ม helper กลาง `_inhours_min()` (clip เวลาเข้า–ออกห้องให้อยู่ใน 8:00–16:00)
- `get_kpi` (วันนี้) + `live_link` (บอร์ดสด): **clip จริง** จาก timestamp → แก้ปัญหาเช้าๆ util เกิน 100%
- สถิติย้อนหลัง: **cap 480 นาที/ห้อง-วัน** (ข้อมูล import บางส่วนไม่มี timestamp รายเคส → cap แทน clip, ผล util ≤ 100% เหมือนกัน)
- หน้า Utilization: clip อยู่แล้ว (ของเดิมถูก) + เพิ่ม footnote นิยาม
- turnover range รวมเป็น 1–90 นาที ทุกจุด (เดิม get_kpi/board ใช้ 0–180)
- ✅ ทดสอบ `_inhours_min`: 09:00–10:30→90 · 07:00–09:00→60 (clip เช้า) · 15:00–18:00→60 (clip เย็น) · 18:00–20:00→0
- **ในเล่มให้ระบุนิยามนี้** เวลาอ้างค่า utilization

## M-03 — เครื่องมือลบข้อมูล 3 จุดอ่อน
- **(ก) `clear_all_data`** (PG): เดิม except set 0 เงียบ ไม่ rollback → table ถัดไปพังตาม (PG abort) ผู้ใช้คิดว่าลบสำเร็จ
  → **commit ต่อ table + rollback กู้ transaction + เก็บ error จริงใน `_errors`** (UI โชว์ "ลบไม่สำเร็จบางส่วน")
- **(ข) "ลบเฉพาะวันที่"** เดิมมี date picker แล้ว import `_gc_count` เฉยๆ = UI ตัน (`clear_cases_by_date_range` ไม่เคยถูกเรียก)
  → **เติม branch ครบ**: นับเคสในช่วง + ยืนยัน + ปุ่มลบที่เรียก `clear_cases_by_date_range`
- **(ค) ลบทั้ง DB**: เดิม checkbox เดียว → **ต้องพิมพ์ "DELETE" ยืนยัน + สำรองอัตโนมัติ (`backup_db`) ก่อนลบ**

## ไฟล์ที่แก้ (compile ผ่านทั้งหมด)
`main_or_export.py` · `main_or_db.py` · `main_or_admin.py` · `live_link.py` · `main_or_utilization.py`

## ก่อน commit (บน Windows)
```powershell
python -m py_compile main_or_export.py main_or_db.py main_or_admin.py live_link.py main_or_utilization.py
git add main_or_export.py main_or_db.py main_or_admin.py live_link.py main_or_utilization.py docs/GROUP_D_REPORTING_2026-06-11.md
git commit -m "fix(reporting): กลุ่ม D — M-07 export + M-08 utilization นิยามเดียว (clip 8-16) + M-03 delete tools"
```
