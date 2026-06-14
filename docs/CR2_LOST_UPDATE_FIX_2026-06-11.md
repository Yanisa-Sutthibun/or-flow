# CR-2 — แก้บอร์ดกลางเขียนทับงานกันเอง (lost-update race)

วันที่: 11 มิ.ย. 2026 · ไฟล์: `main_or_pages.py`

## ปัญหาเดิม
- บอร์ดกลางเซฟลง Supabase **ทุก rerun** (แม้แค่เปิด popover/refresh) → เครื่องที่ถือ
  สถานะเก่าเขียนทับงานที่เครื่องอื่นเพิ่งกด ภายในหน้าต่าง 30 วิ (ก่อน pull รอบถัดไป)
- `save_board_state()` เขียนทับตรง ไม่มี version check → งานหายเงียบ

## ทางแก้ (2 ชั้น)

### ชั้น 1 — เซฟเฉพาะเมื่อ "เครื่องนี้แก้จริง" (dirty flag)
- เพิ่ม `_mark_board_dirty(case)` ตั้ง `_board_dirty=True` + เก็บ `id` เคสที่แก้ใน `_board_dirty_ids`
- เรียกใน `_do_arrive / _do_enter / _do_finish / _do_undo` + เพิ่มเคส (form) + อัปโหลด CSV
- save ท้ายหน้าทำงาน **เฉพาะตอน `_board_dirty=True`** แล้วล้าง flag → rerun เฉย ๆ ไม่เซฟอีก
- pull block **ข้ามการดึงทับเมื่อ `_board_dirty`** (กันงานตัวเองที่ยังไม่เซฟหาย)

### ชั้น 2 — optimistic concurrency (version + merge ราย-เคส)
- payload เพิ่ม `version` + `saved_at`
- `_load_board_snapshot()` จำ `_board_base_version` = เวอร์ชันที่โหลดมา
- ตอนเซฟ: re-load DB ก่อนเขียน
  - `db_version > base_version` → มีเครื่องอื่นเขียนแซง → **merge**: เริ่มจากเคสของ DB ล่าสุด
    แล้ว overlay เฉพาะเคสที่เครื่องนี้แก้ (`_board_dirty_ids`) ทับ → ไม่ทับทั้งกระดาน
  - ไม่ชน → เขียนปกติ `version = db_version + 1`
- รองรับ payload เก่าที่ไม่มี `version` (ถือเป็น 0) → อัปเกรดได้เนียน
- ปุ่มล้างกระดานรีเซ็ต `_board_dirty / _board_dirty_ids / _board_base_version`

## ผลการทดสอบ
- `py_compile` ผ่าน (อ่านสด 58,820 B / 925 บรรทัด)
- Simulation 2 เครื่องแก้คนละเคสพร้อมกัน:
  - แบบใหม่ (merge): A=in_or, B=in_or → ✅ งานครบ
  - แบบเก่า (เขียนทับ): A=not_arrived (หาย!), B=in_or → ❌
- Rerun เฉย ๆ (dirty=False) → ไม่เซฟ = ไม่เขียนทับ ✅

## ข้อจำกัดที่เหลือ (เก็บไว้ v2)
- กรณี 2 เครื่องแก้ **เคสเดียวกัน** พร้อมกัน → last-writer-wins ระดับเคส (ยอมรับได้ พบยาก)
- กรณีหลายเครื่องค้างเปิดตอนกดล้างกระดาน → เครื่องที่ยังถือ local เก่าอาจ re-save กลับ
  (เครื่องอื่นกด 🔄 หรือปิด-เปิดแก้ได้) — ทางถาวรตามแผน v2: เขียนราย-เคสลงตาราง `cases`

## ต้องทำก่อน commit (บน Windows — authoritative)
```powershell
python -m py_compile main_or_pages.py
git add main_or_pages.py docs/CR2_LOST_UPDATE_FIX_2026-06-11.md
git commit -m "fix(board): CR-2 ป้องกัน lost-update — เซฟเฉพาะตอนแก้จริง + version/merge ราย-เคส"
```
