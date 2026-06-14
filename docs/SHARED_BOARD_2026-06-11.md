# บอร์ดกลาง OR Live (shared real-time board) — 11 มิ.ย. 2026

> โจทย์: ทุกห้องดูบอร์ดกลางเดียวกันได้ · ผู้บริหารเห็น flow ทีมแบบ real-time แม้อยู่คนละเครื่อง
> ตัดสินใจ: บอร์ดกลางเต็มรูปแบบ + **demo names บน cloud สาธารณะ** (ข้อมูลจริงเฉพาะ deploy ในเครือข่าย รพ.)

## ทำงานยังไง (สถาปัตยกรรม)

เดิม: สถานะบอร์ดอยู่ใน `session_state` (แยกต่อเครื่อง) + ไฟล์ snapshot local → แชร์ข้ามเครื่องไม่ได้

ใหม่: **snapshot บอร์ด เก็บใน Supabase** (ตาราง `app_settings` คีย์ `board_state_YYYY-MM-DD`) → ทุกเครื่องอ่าน/เขียนที่เดียวกัน = บอร์ดกลาง

- `main_or_db.save_board_state / load_board_state` — อ่าน/เขียน DB (ใช้ app_settings ที่มีอยู่ ไม่ต้องสร้างตารางใหม่)
- `_save_board_snapshot` เขียน **DB ก่อน** + ไฟล์ local เป็น backup
- `_load_board_snapshot` อ่าน **DB ก่อน** → fallback ไฟล์ local (โหมด offline/sqlite)
- บอร์ดดึงสถานะล่าสุดเมื่อ: **เปิดครั้งแรก · กด 🔄 · ครบรอบ auto-refresh (~30 วิ)**
- **ไม่ดึงตอนเพิ่งกดปุ่มบนเครื่องตัวเอง** (กันทับการเปลี่ยนที่ยังไม่ได้ save) — ใช้ tick ของ autorefresh + flag `_board_force_pull`
- **หน้าบริหาร (ผู้บริหารคนละเครื่อง):** ถ้า session ว่าง → โหลด shared snapshot มาแสดง flow ห้อง + auto-refresh 30 วิ → เห็นทีมทำงานสดจากห้องทำงาน

## 3 ข้อมูลที่ "เฉพาะบอร์ดเก็บได้" (ไม่มีใน HIS) — เก็บครบ ✅

ทดสอบ roundtrip ผ่าน shared state แล้ว:

| ข้อมูล | เก็บที่ | ได้มาจาก |
|---|---|---|
| **เวลารอ** (กดรับเข้า → เข้าห้อง) | `time_arrived_holding` + `time_entered_or` ใน snapshot | คำนวณ entered − arrived |
| **เวลา AI ทำนาย** | `ai_predicted_min` | โมเดล honest_v1 ตอนโหลดเคส |
| **เวลา user แก้/override** | `user_override_min` | กด ✏️ บนบอร์ด |

ข้อมูลอื่น (หัตถการ/แพทย์/เวลาจริง room-in/out) มาจาก HIS import ตามเดิม

## 🔒 PII / การ deploy (สำคัญ)

บอร์ดกลาง "แชร์ชื่อ" = ชื่อต้องอยู่ใน DB กลาง → ดังนั้น:

- **Demo บน cloud สาธารณะ:** ใส่เฉพาะ **demo/ข้อมูลสังเคราะห์** เท่านั้น — ห้ามอัปโหลดผู้ป่วยจริง
  (ตั้ง `snapshot_keep_pii = true` เพื่อให้ชื่อ demo แสดง · ถ้าปล่อย false ชื่อจะขึ้น "ไม่ระบุ")
- **ใช้จริงในเครือข่าย รพ. (on-prem/Supabase ส่วนตัว):** ใส่ชื่อจริงได้ตามกฎหมาย (ระบบของสถานพยาบาลเอง) + เปิด RLS

โค้ดชุดเดียวกัน — ต่างกันแค่ "deploy ที่ไหน + ใส่ข้อมูลอะไร"

## วิธีทดสอบ (2–3 เครื่อง)

ต้อง `db_mode = "supabase"` (sqlite local = เครื่องเดียว แชร์ไม่ได้)

1. เครื่อง A: เปิดหน้า "ตารางผ่าตัด" → อัปโหลด/Demo → กด "รับเข้า" เคสหนึ่ง
2. เครื่อง B (อีกเบราว์เซอร์/เครื่อง): เปิดหน้าเดียวกัน → ภายใน ~30 วิ (หรือกด 🔄) เห็นเคสนั้นเป็น "รอผ่าตัด" ตาม A
3. เครื่อง C (ผู้บริหาร): เปิด "บริหารจัดการ → ภาพรวมวันนี้" → เห็นการ์ดห้อง + ไทม์ไลน์ flow สด อัปเดตเอง

ถ้าเครื่อง B ไม่อัปเดต: เช็ก (ก) ทั้งคู่ `db_mode=supabase` ชี้ DB เดียวกัน (ข) ตาราง `app_settings` มีบน Supabase (มาจาก schema_postgres.sql)

## ⚠️ ข้อจำกัด (เขียนใน limitation บทที่ 5)

1. **Concurrency = last-writer-wins ทั้งบอร์ด** — ถ้า 2 คนกดคนละเคส "พร้อมกันภายในวินาทีเดียว" การเปลี่ยนหนึ่งอาจถูกทับ (หน้าต่างเสี่ยง ~1 render = มิลลิวินาที) ในทางปฏิบัติ พยาบาลคุมคนละห้อง + refresh ถี่ → โอกาสชนต่ำมาก
2. **auto-refresh 30 วิ ระหว่างกรอกฟอร์ม** — ค่าที่พิมพ์ไม่หาย (เก็บใน session ตาม key) แต่ popover/focus อาจรีเซ็ต · ยอมรับได้สำหรับบอร์ดดูสถานะ
3. **ความสด ~30 วิ** ไม่ใช่ instant push (เป็น polling) — เพียงพอสำหรับ OR แต่ไม่ใช่ sub-second

## ▶️ v2 (ถ้าจะดันเป็น production จริงเต็มตัว)

เปลี่ยนจาก "snapshot ทั้งบอร์ด" → **เขียนราย-เคสลงตาราง `cases`** ผ่านฟังก์ชันที่มีอยู่แล้ว:
`mark_arrived` / `mark_in_or` (คำนวณ wait_min ให้) / `mark_op_end` / `mark_discharged` + `update_case(user_override_min=...)` — keyed by `case_id`
→ กัน concurrency ได้จริง (เขียนเฉพาะ field ที่เปลี่ยน ไม่ทับทั้งก้อน) + ข้อมูลเข้าตาราง cases ใช้ทำสถิติได้ทันที
ต้องทำ mapping เคสบอร์ด (id `CSV_xxx`) ↔ `case_id` ก่อน

## ไฟล์ที่แก้

`main_or_db.py` (save/load_board_state) · `main_or_pages.py` (snapshot→DB, pull logic, autorefresh) · `main_or_admin.py` (manager view โหลด shared + autorefresh) · `command_center.py` (มาจากงาน turnover ก่อนหน้า)
