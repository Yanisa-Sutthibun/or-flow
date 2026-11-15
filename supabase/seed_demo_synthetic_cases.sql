-- ═══════════════════════════════════════════════════════════════════
-- 🧪 seed_demo_synthetic_cases.sql : เติมเคสสมมติใน demo ช่วง 1 ก.ค. ถึง 14 พ.ย. 2026
-- ═══════════════════════════════════════════════════════════════════
-- ที่มา (มุกกี้สั่ง 15 พ.ย. 2026): ข้อมูลตั้งต้นของ demo จบที่ 30 มิ.ย. 2026
--   หน้าสถิติย้อนหลังของระบบสาธิตจึงว่างตั้งแต่ ก.ค. เป็นต้นมา
--
-- วิธีสร้าง: หยิบเคสของ demo ช่วง มี.ค. ถึง มิ.ย. 2026 (ตึกใหม่ ห้อง 90-98) มาเลื่อนวันที่
--   ไปข้างหน้าเป็นจำนวนสัปดาห์เต็ม วันในสัปดาห์จึงตรงเดิม (จันทร์ยังเป็นจันทร์)
--     1-4 ก.ค.        = 4-7 มี.ค.          เลื่อน 17 สัปดาห์ (119 วัน)
--     5 ก.ค.-3 พ.ย.   = 1 มี.ค.-30 มิ.ย.   เลื่อน 18 สัปดาห์ (126 วัน)
--     4-14 พ.ย.       = 11-21 มี.ค.        เลื่อน 34 สัปดาห์ (238 วัน)
--   procnote ไม่ก็อปตาม (เว้นว่าง) · created_at/updated_at = 2026-11-15 12:00:00
--
-- ⚠️ เป็นข้อมูลสมมติของ demo เท่านั้น ห้ามรันกับ orsurg และห้ามใช้เป็นข้อมูลวิจัย
--    วิธีแยก: แถวใน demo.cases ที่ op_date >= '2026-07-01' คือเคสสมมติทั้งหมด
-- ⚠️ วันหยุดราชการช่วง ก.ค. ถึง พ.ย. ไม่ได้ตัดออก · ช่องว่างสงกรานต์จะไปโผล่กลาง ส.ค.
--
-- รันซ้ำได้ปลอดภัย: ถ้ามีเคสตั้งแต่ 1 ก.ค. 2026 อยู่แล้วจะไม่เติมซ้ำ
-- ถ้ารัน setup_demo_schema.sql ใหม่ (ล้าง demo.cases) ต้องรันไฟล์นี้ตามอีกครั้ง
-- ═══════════════════════════════════════════════════════════════════

INSERT INTO demo.cases (
  op_date, is_ipd, diagnosis, procedure_name, surgeon_name, division_code,
  case_category, patient_type, op_type, estimated_time, status, cancel_reason,
  ai_predicted_min, user_override_min, actual_duration_min, scrub_nurse, circ_nurse,
  anesthesia_type, wait_min, room_no, arrived_at, in_or_at, op_end_at, discharged_at,
  post_op_dest, scheduled_surgeon, age, ai_predicted_min_legacy, ai_model_ver,
  created_at, updated_at)
SELECT
  (c.op_date::date + m.shift)::text, c.is_ipd, c.diagnosis, c.procedure_name,
  c.surgeon_name, c.division_code, c.case_category, c.patient_type, c.op_type,
  c.estimated_time, c.status, c.cancel_reason, c.ai_predicted_min,
  c.user_override_min, c.actual_duration_min, c.scrub_nurse, c.circ_nurse,
  c.anesthesia_type, c.wait_min, c.room_no,
  CASE WHEN length(c.arrived_at) = 19 THEN to_char(c.arrived_at::timestamp + m.shift * interval '1 day', 'YYYY-MM-DD HH24:MI:SS') END,
  CASE WHEN length(c.in_or_at) = 19 THEN to_char(c.in_or_at::timestamp + m.shift * interval '1 day', 'YYYY-MM-DD HH24:MI:SS') END,
  CASE WHEN length(c.op_end_at) = 19 THEN to_char(c.op_end_at::timestamp + m.shift * interval '1 day', 'YYYY-MM-DD HH24:MI:SS') END,
  CASE WHEN length(c.discharged_at) = 19 THEN to_char(c.discharged_at::timestamp + m.shift * interval '1 day', 'YYYY-MM-DD HH24:MI:SS') END,
  c.post_op_dest, c.scheduled_surgeon, c.age, c.ai_predicted_min_legacy, c.ai_model_ver,
  '2026-11-15 12:00:00', '2026-11-15 12:00:00'
FROM demo.cases c
JOIN (VALUES ('2026-03-04', '2026-03-07', 119),
             ('2026-03-01', '2026-06-30', 126),
             ('2026-03-11', '2026-03-21', 238)) AS m(lo, hi, shift)
  ON c.op_date BETWEEN m.lo AND m.hi
WHERE NOT EXISTS (SELECT 1 FROM demo.cases WHERE op_date >= '2026-07-01');

-- ✅ ตรวจผล: จำนวนเคสรายเดือนของปี 2026
SELECT left(op_date, 7) AS ym, COUNT(*) FROM demo.cases
WHERE op_date >= '2026-01-01' GROUP BY 1 ORDER BY 1;
