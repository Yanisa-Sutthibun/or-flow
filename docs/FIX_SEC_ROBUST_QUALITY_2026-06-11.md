# บันทึกแก้ไข หมวดความปลอดภัย / ความทนทาน / คุณภาพโค้ด — 11 มิ.ย. 2026

> ปิดประเด็นคงค้างจากรายงานตรวจส่วนที่ 1 (หมวด 2–4) · ทดสอบ 8 ข้อผ่านครบ

## 🔒 หมวด 2: ความปลอดภัยของข้อมูล

| ประเด็นเดิม | การแก้ |
|---|---|
| PIN `'muke'` hardcode ใน 2 ไฟล์ (ใครอ่านซอร์สก็ปลดล็อกได้ถึง Clean Wipe) | ✅ ย้ายไป `st.secrets['admin_pin']` ผ่าน `main_or_db.get_admin_pin()` — **fail-closed**: ไม่ตั้งค่า = ฟีเจอร์ล็อกพร้อมข้อความแนะนำ (อัปโหลด CSV บนบอร์ด / Maintenance / Progress พยาบาล ทั้ง 4 จุด) |
| snapshot บอร์ดเก็บ **ชื่อ+HN ผู้ป่วย** ลงดิสก์ (บน cloud = ดิสก์เซิร์ฟเวอร์นอก รพ.) | ✅ ค่าเริ่มต้น**ไม่เก็บ** ชื่อ→"ไม่ระบุ", HN→ว่าง (ข้อมูลงานอื่นครบ กู้บอร์ดได้ปกติ) · เครื่องใน รพ. ที่ต้องการชื่อ: ตั้ง `snapshot_keep_pii = true` ใน secrets · ตอนกู้บอร์ดมี caption บอกว่าชื่อไม่ถูกเก็บ |
| `database_url` ไม่มี `sslmode=require` | ✅ เติมให้แล้วใน secrets.toml เครื่องนี้ (อย่าลืมใช้ URL แบบเดียวกันบน cloud) |
| `secrets.toml.example` ไม่มีคีย์ใหม่ | ✅ เพิ่ม `admin_pin`, `snapshot_keep_pii`, หมายเหตุ sslmode |

**RLS (ทำเองใน Supabase Dashboard — โค้ดทำแทนไม่ได้):** SQL Editor รัน
```sql
SELECT c.relname AS table, c.relrowsecurity AS rls_enabled
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'orsurg' AND c.relkind = 'r';
```
ทุกตารางต้องได้ `rls_enabled = true` (ถ้า false → รันท่อน RLS ใน `supabase/schema_postgres.sql`)
⚠️ จุดที่ต้องเขียนให้ตรงในเล่ม: แอปต่อผ่าน `DATABASE_URL` (role จริง) ซึ่ง **bypass RLS** —
เกราะหลักของระบบคือ "DB ไม่เก็บ name/HN/AN + masking บุคลากร + เก็บ credentials เป็นความลับ"
ส่วน RLS เป็นเกราะกัน anon key เท่านั้น

## 🛡 หมวด 3: ความทนทานของระบบ

| ประเด็นเดิม | การแก้ |
|---|---|
| DB ต่อไม่ติด → traceback แดงเต็มจอใส่พยาบาล | ✅ `main()` ครอบ `init_db()` — ขึ้นข้อความไทยอ่านรู้เรื่อง + วิธีปฏิบัติ + รายละเอียดเทคนิคพับเก็บใน expander |
| pool DB เต็ม/ล่มซ้ำ → exception ดิบ | ✅ ครั้งที่สองขึ้นข้อความ "รอ ~1 นาทีแล้วรีเฟรช" |
| auto-refresh 30 นาที **ไม่เคยทำงานจริง** (`<script>` ใน st.markdown ไม่ execute) | ✅ เปลี่ยนเป็น `streamlit_autorefresh` (มีใน requirements อยู่แล้ว) |
| สถานะเคสแปลก (snapshot เวอร์ชันเก่า) → `KeyError` ทั้งหน้า | ✅ `_STATUS_META.get(...)` + ชิป fallback "ไม่ทราบสถานะ" |
| `or_rooms`/`room_settings` เริ่มต้นเป็นห้อง **11–17 (ตึกเก่า)** — state ค้าง และทำให้การ restore การตั้งค่าห้องจาก DB ตอนบูต**ถูกข้าม** (key ไม่ตรง 90s) | ✅ ใช้ `room_config.NEW_BUILDING_ROOMS` (90–98) เป็น single source — restore ตอนบูตทำงานแล้วโดยไม่ต้องเข้าหน้าตั้งค่าก่อน |
| โมเดลหลักล่มแล้ว fallback **เงียบ** (ธีมเดียวกับเหตุ pkl หายบน cloud) | ✅ log ทุกจุด: `main_or_core.predict_surgical_time`, `main_or_db._predict_for_case` (ทั้ง 2 ชั้น) → เห็นใน logs/orflow.log |

## 🧹 หมวด 4: คุณภาพโค้ด

| ประเด็นเดิม | การแก้ |
|---|---|
| ค่าคงที่ห้องซ้ำ 2 ชุดไม่ sync — utilization ตกหล่น **OR9 (ห้อง 98)** หายจากกราฟทุกตัว | ✅ `main_or_utilization` import จาก `room_config` (ห้องครบ 9 + วันที่ย้ายตึกตัวเดียวกัน) |
| แท็บ Utilization อ่านไฟล์ xls local (gitignore) → **บน cloud ตายทั้งแท็บ** | ✅ เพิ่ม `_load_from_db()` — ไม่มีไฟล์ → ดึงจากตาราง cases (เวลาเข้า-ออกห้องจริง) ทำงานได้ทั้ง local/cloud |
| import หน้า dead ตอนบูต (`page_statistics`, `page_tracking` ไม่ถูก route) | ✅ ตัด import ออกจาก `main_or_app` (ไฟล์หน้ายังอยู่ เผื่อเรียกคืน) |
| `prediction_log.model_version` = 'unknown' ตลอด (อ่าน key ที่ไม่มีจริง) | ✅ บันทึก `honest_v1` / `vN-fallback` ตามจริง — ตามรอยโมเดลในข้อมูลวิจัยได้ |
| `add_walkin_case` คืน id = None บน Postgres (landmine) | ✅ ใช้ `RETURNING case_id` เมื่อเป็น Postgres |
| `backup_db` จะ crash แปลกๆ ถ้าเรียกบน cloud | ✅ guard: ขึ้นข้อความ "ใช้ได้เฉพาะ SQLite local" |

## ไฟล์ขยะ (ลบเองบน Windows — sandbox ลบผ่าน mount ไม่ได้)

```powershell
cd C:\Dev\main_OR_app
Remove-Item main_or_utilization.py.bak, _wtest_5
Remove-Item supabase\anonymize_for_cloud.py, supabase\inspect_db.py   # อ้าง schema เก่า (name/hn) — ล้าสมัย
git add -A
git commit -m "fix(security/robustness/quality): PIN->secrets fail-closed, snapshot PII opt-in, friendly DB errors, room_config single-source (OR9), utilization DB fallback, real model version in prediction_log"
```

## ตั้งค่าบน Streamlit Cloud (App settings → Secrets)

```toml
db_mode = "supabase"
db_schema = "orsurg"
database_url = "...?sslmode=require"   # ลงท้าย sslmode=require
app_password = "รหัสเข้าแอป"
admin_pin = "รหัสปลดล็อกของหัวหน้า"     # อย่าใช้ 'muke' เดิม — ถือว่าหลุดแล้ว (เคยอยู่ในซอร์ส)
# snapshot_keep_pii ไม่ต้องตั้ง (default = ไม่เก็บชื่อ → ถูกต้องสำหรับ cloud)
```

## ผลทดสอบ (รันจริงทั้งหมด)

1. ✅ compile ผ่านทั้ง 8 ไฟล์ที่แก้ · ไม่มีไฟล์เสียหาย (ตรวจ NUL/truncation แล้ว)
2. ✅ `get_admin_pin()` fail-closed เมื่อไม่ตั้งค่า / อ่านค่าได้เมื่อตั้ง
3. ✅ `init_session_state()` → ห้อง 90–98 ครบรวม OR9
4. ✅ สถานะแปลกไม่ทำให้บอร์ดพัง
5. ✅ snapshot ค่าเริ่มต้น: ชื่อ→"ไม่ระบุ" HN→ว่าง (ข้อมูลงานครบ) / ตั้ง flag แล้วเก็บชื่อได้
6. ✅ prediction_log ระบุ honest_v1 จริง
7. ✅ utilization มี OR9 + `_load_from_db`

**คงเหลือที่ไม่แก้ในรอบนี้ (จงใจ + เหตุผล):** สูตร utilization ที่ต่างกันข้ามหน้า (get_kpi
/ live_link / historical / utilization tab) — เป็นการตัดสินใจเชิง "นิยาม KPI ของงานวิจัย"
ควรเลือกนิยามเดียวก่อน (เหมาะกับส่วนที่ 2 ของการตรวจ) แล้วค่อยรวมเป็นฟังก์ชันกลาง ·
orroom feature เก่า/ใหม่ (11–17 vs 90–98) — เป็น limitation ระดับโมเดล เขียนในเล่มบทที่ 5
