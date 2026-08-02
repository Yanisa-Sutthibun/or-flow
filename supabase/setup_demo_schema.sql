-- ═══════════════════════════════════════════════════════════════════
-- 🧪 setup_demo_schema.sql — สร้างระบบ DEMO (schema "demo") ฉบับโคลนอัตโนมัติ
-- ═══════════════════════════════════════════════════════════════════
-- วิธีใช้: Supabase → SQL Editor → วางทั้งไฟล์ → Run · รันซ้ำได้ปลอดภัย
--
-- 📖 บทเรียน (2 ส.ค. 2026): เดิมสร้าง demo จากไฟล์ DDL แล้วพัง เพราะ orsurg
--    มีตารางที่เกิดนอกไฟล์ schema (staff_map, shadow_v2_log, research_case_log)
--    → เปลี่ยนเป็น "โคลนจากตารางจริงทุกตัว" ด้วย information_schema แทน
--    ไม่ว่าอนาคต orsurg จะมีตารางเพิ่มกี่ตัว รันไฟล์นี้ซ้ำ = demo ตามทันเสมอ
--
-- หมายเหตุ: LIKE ... INCLUDING ALL ทำให้คอลัมน์ id ใช้ sequence ร่วมกับ orsurg
-- (เลขรันต่อกัน) — ไม่กระทบข้อมูล เป็นแค่เรื่องเลขลำดับ
-- ═══════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS demo;

-- 1) โคลนโครงสร้างทุกตารางของ orsurg → demo (เฉพาะที่ยังไม่มี) + เปิด RLS
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT table_name FROM information_schema.tables
           WHERE table_schema = 'orsurg' AND table_type = 'BASE TABLE'
  LOOP
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS demo.%I (LIKE orsurg.%I INCLUDING ALL)',
      t.table_name, t.table_name);
    EXECUTE format(
      'ALTER TABLE demo.%I ENABLE ROW LEVEL SECURITY', t.table_name);
  END LOOP;
END $$;

-- 2) สำเนาข้อมูลตั้งต้น (ครั้งเดียว/รีเซ็ตได้): สถิติไม่ระบุตัวตน + รายชื่อบุคลากร
TRUNCATE demo.cases;
INSERT INTO demo.cases SELECT * FROM orsurg.cases;
TRUNCATE demo.staff_map;
INSERT INTO demo.staff_map SELECT * FROM orsurg.staff_map;

-- 3) ✅ ตรวจผล: จำนวนต้องเท่ากันเป็นคู่ ๆ
SELECT 'demo.cases' AS t, COUNT(*) FROM demo.cases
UNION ALL SELECT 'orsurg.cases', COUNT(*) FROM orsurg.cases
UNION ALL SELECT 'demo.staff_map', COUNT(*) FROM demo.staff_map
UNION ALL SELECT 'orsurg.staff_map', COUNT(*) FROM orsurg.staff_map;
