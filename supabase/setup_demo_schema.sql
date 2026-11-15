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

-- 2) สำเนาข้อมูลตั้งต้น (ครั้งเดียว/รีเซ็ตได้): สถิติไม่ระบุตัวตนเท่านั้น
TRUNCATE demo.cases;
INSERT INTO demo.cases SELECT * FROM orsurg.cases;
-- 🔐 PDPA (มุกกี้สั่ง 15 พ.ย. 2026): เลิกก็อปรายชื่อบุคลากรจริงเข้า demo
--    แอป demo ไม่ได้อ่านตารางนี้อยู่แล้ว (staff_map_sync คืน 'demo-skip')
--    เก็บไว้มีแต่ความเสี่ยง → ล้างให้ว่างทุกครั้งที่รันไฟล์นี้
TRUNCATE demo.staff_map;

-- 🧪 เคสสมมติ ก.ค. ถึง พ.ย. 2026 ของ demo ถูกล้างไปกับ TRUNCATE ข้างบนด้วย
--    ถ้าต้องการคืน ให้รัน seed_demo_synthetic_cases.sql ตามหลังไฟล์นี้

-- 3) ✅ ตรวจผล: cases ต้องเท่ากัน · demo.staff_map ต้องเป็น 0
SELECT 'demo.cases' AS t, COUNT(*) FROM demo.cases
UNION ALL SELECT 'orsurg.cases', COUNT(*) FROM orsurg.cases
UNION ALL SELECT 'demo.staff_map (ต้องเป็น 0)', COUNT(*) FROM demo.staff_map;
