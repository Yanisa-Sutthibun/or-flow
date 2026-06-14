-- ═══════════════════════════════════════════════════════════════════
-- 🏥 Main OR Dashboard — PostgreSQL Schema (Supabase)
-- ═══════════════════════════════════════════════════════════════════
-- อัปเดต 2026-06 — ตรงกับ main_or.db ปัจจุบัน:
--   + cases: เพิ่ม age, ai_predicted_min_legacy, ai_model_ver
--   + ตารางใหม่ override_log (เก็บการแก้เวลา AI โดยคน — งานวิจัย human-AI)
--   + ส่วน Row Level Security (RLS) ปิดการเข้าถึงด้วย anon key
--
-- วิธีใช้:
--   1. เปิด Supabase Dashboard → SQL Editor → New query
--   2. Paste ไฟล์นี้ทั้งหมด → Run (Ctrl+Enter)
--   3. ตรวจที่ Table Editor ว่ามี 7 tables: cases, audit_log,
--      prediction_log, backup_log, room_settings, app_settings, override_log
--   4. แอพเชื่อมผ่าน service key เท่านั้น (เก็บใน .streamlit/secrets.toml)
-- ═══════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════
-- 🗂️ SCHEMA แยกแอพ — main OR ใช้ "orsurg" (minor OR อยู่ public/minor)
-- ใช้ Supabase project เดียวกันได้โดยข้อมูล 2 แอพไม่ชนกัน
-- ทุก CREATE TABLE ด้านล่างจะสร้างใน orsurg เพราะ SET search_path ไว้แล้ว
-- ═══════════════════════════════════════════════════════════════════
CREATE SCHEMA IF NOT EXISTS orsurg;
SET search_path TO orsurg, public;

-- ─── Drop ทั้งหมดก่อน (ถ้าต้องการ rerun) ─────────────────────────
-- ⚠️ เปิด comment เฉพาะตอน reset เท่านั้น — ระวังลบ data จริง!
-- DROP TABLE IF EXISTS override_log CASCADE;
-- DROP TABLE IF EXISTS audit_log CASCADE;
-- DROP TABLE IF EXISTS prediction_log CASCADE;
-- DROP TABLE IF EXISTS backup_log CASCADE;
-- DROP TABLE IF EXISTS room_settings CASCADE;
-- DROP TABLE IF EXISTS app_settings CASCADE;
-- DROP TABLE IF EXISTS cases CASCADE;

-- ═══════════════════════════════════════════════════════════════════
-- TABLE 1: cases — ตารางหลักเก็บเคสผ่าตัด (ไม่มี name/hn — privacy by design)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS cases (
    case_id             SERIAL PRIMARY KEY,
    op_date             TEXT NOT NULL,         -- 'YYYY-MM-DD'
    -- 🔒 ไม่เก็บ name/hn/an ผู้ป่วยลง DB (privacy by design / PDPA — ทุกตัวระบุตัวคนไข้ได้)
    --    ชื่อผู้ป่วยขึ้นกระดานจาก session เท่านั้น (transient)
    --    is_ipd: 1=IPD (ตอน import มี AN), 0=OPD — เก็บไว้ทำสถิติ ไม่เก็บเลข AN
    is_ipd              INTEGER DEFAULT 0,
    diagnosis           TEXT,
    procedure_name      TEXT NOT NULL,
    surgeon_name        TEXT,                  -- intra-op surgeon (จริงที่ทำ)
    division_code       TEXT,                  -- รหัสแผนก (1-10, 41, 71)
    case_category       TEXT,                  -- 'เคสนัดหมาย' / 'Walk-in'
    patient_type        TEXT,                  -- 'IPD' / 'OPD' / 'นอกเวลา'
    op_type             TEXT,                  -- 'elective' / 'emergency'
    estimated_time      TEXT,
    procnote            TEXT,

    -- Status
    status              TEXT DEFAULT 'scheduled',  -- scheduled/arrived/in_or/post_op/discharged/cancelled
    cancel_reason       TEXT,

    -- Timing & AI
    ai_predicted_min    INTEGER,
    user_override_min   INTEGER,               -- เวลาที่คนแก้ (ชนะ AI ในการวางแผน)
    actual_duration_min INTEGER,
    scrub_nurse         TEXT,
    circ_nurse          TEXT,
    anesthesia_type     TEXT,
    wait_min            INTEGER DEFAULT 0,
    room_no             INTEGER DEFAULT 1,     -- ตึกใหม่ 90-98 / ตึกเก่า 11-17

    -- Workflow timestamps (v2)
    arrived_at          TEXT,
    in_or_at            TEXT,
    op_end_at           TEXT,
    discharged_at       TEXT,
    post_op_dest        TEXT DEFAULT 'transfer',

    -- Scheduled surgeon (จาก schedule.csv — ไม่ overwrite ตอน intraop import)
    scheduled_surgeon   TEXT,

    -- 🆕 2026-06: feature อายุ + audit คำทำนายข้ามรุ่นโมเดล
    age                     REAL,              -- อายุผู้ป่วย (feature โมเดล)
    ai_predicted_min_legacy INTEGER,           -- คำทำนายเดิมก่อน re-backfill (เทียบ before/after)
    ai_model_ver            TEXT,              -- รุ่นโมเดลที่ทำนายแถวนี้ (เช่น 'v2', 'v2 (in-sample 64-67)')

    -- Meta
    created_at          TEXT DEFAULT (to_char((NOW() AT TIME ZONE 'Asia/Bangkok'), 'YYYY-MM-DD HH24:MI:SS')),
    updated_at          TEXT DEFAULT (to_char((NOW() AT TIME ZONE 'Asia/Bangkok'), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE INDEX IF NOT EXISTS idx_cases_op_date      ON cases(op_date);
CREATE INDEX IF NOT EXISTS idx_cases_status       ON cases(status);
-- 🔒 กันซ้ำตอน import ด้วยชุดข้อมูลที่ไม่ใช่ตัวระบุตัวบุคคล (วันที่,ห้อง,หัตถการ,เวลาเข้าห้อง)
CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_unique_import
    ON cases(op_date, room_no, procedure_name, in_or_at);
CREATE INDEX IF NOT EXISTS idx_cases_date_status  ON cases(op_date, status);
CREATE INDEX IF NOT EXISTS idx_cases_surgeon      ON cases(surgeon_name);
CREATE INDEX IF NOT EXISTS idx_cases_procedure    ON cases(procedure_name);

-- 🔁 ถ้า table cases มีอยู่แล้ว (migrate จาก schema เดิม) — เพิ่ม 3 คอลัมน์ใหม่
ALTER TABLE cases ADD COLUMN IF NOT EXISTS age                     REAL;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS ai_predicted_min_legacy INTEGER;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS ai_model_ver            TEXT;


-- ═══════════════════════════════════════════════════════════════════
-- TABLE 2: audit_log — ประวัติการแก้ไข
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_log (
    log_id      SERIAL PRIMARY KEY,
    case_id     INTEGER,
    action      TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    detail      TEXT,
    created_at  TEXT DEFAULT (to_char((NOW() AT TIME ZONE 'Asia/Bangkok'), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_log(case_id);


-- ═══════════════════════════════════════════════════════════════════
-- TABLE 3: prediction_log — เก็บ ML predictions สำหรับ retrain + วิจัย
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS prediction_log (
    pred_id          SERIAL PRIMARY KEY,
    case_id          INTEGER,
    model_version    TEXT,
    procedure_name   TEXT,
    surgeon_name     TEXT,
    predicted_min    INTEGER,
    actual_min       INTEGER,
    abs_error        INTEGER,
    confidence       TEXT,
    created_at       TEXT DEFAULT (to_char((NOW() AT TIME ZONE 'Asia/Bangkok'), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE INDEX IF NOT EXISTS idx_pred_case ON prediction_log(case_id);


-- ═══════════════════════════════════════════════════════════════════
-- TABLE 4: backup_log — ประวัติการ backup
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS backup_log (
    backup_id   SERIAL PRIMARY KEY,
    backup_path TEXT,
    row_count   INTEGER,
    created_at  TEXT DEFAULT (to_char((NOW() AT TIME ZONE 'Asia/Bangkok'), 'YYYY-MM-DD HH24:MI:SS'))
);


-- ═══════════════════════════════════════════════════════════════════
-- TABLE 5: room_settings — การตั้งค่าห้องผ่าตัด + nurse assignment
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS room_settings (
    room_no     INTEGER PRIMARY KEY,
    enabled     INTEGER DEFAULT 1,
    scrub_json  TEXT DEFAULT '["",""]',
    circ_json   TEXT DEFAULT '["","","",""]',
    updated_at  TEXT DEFAULT (to_char((NOW() AT TIME ZONE 'Asia/Bangkok'), 'YYYY-MM-DD HH24:MI:SS'))
);


-- ═══════════════════════════════════════════════════════════════════
-- TABLE 6: app_settings — key/value store (flags, configs)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS app_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);


-- ═══════════════════════════════════════════════════════════════════
-- TABLE 7: override_log — 🆕 บันทึกการแก้เวลา AI โดยคน (human-AI研究)
-- เก็บ 2 จังหวะ: ตอนกด 💾 บนกระดาน + ตอนผ่าเสร็จเติมเวลาจริง
-- ใช้เทียบ |AI − จริง| กับ |คน − จริง| → ตอบว่า override มีคุณค่าไหม
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS override_log (
    id                   SERIAL PRIMARY KEY,
    logged_at            TEXT NOT NULL,
    case_ref             TEXT,                 -- id เคสบนกระดาน (เช่น 'CSV_xxxx')
    -- 🔒 ไม่เก็บ name/hn ผู้ป่วย (privacy by design)
    procedure_name       TEXT,
    surgeon_name         TEXT,
    room_no              INTEGER,
    ai_predicted_min     INTEGER,              -- ค่า AI เดิม (แช่แข็งไว้)
    override_min         INTEGER,              -- ค่าที่คนแก้
    actual_duration_min  INTEGER,              -- เติมตอนผ่าเสร็จ
    source               TEXT DEFAULT 'board'
);

CREATE INDEX IF NOT EXISTS idx_override_ref ON override_log(case_ref);


-- ═══════════════════════════════════════════════════════════════════
-- TRIGGER: auto-update updated_at เมื่อมีการแก้ไข cases
-- ═══════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION update_cases_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = to_char((NOW() AT TIME ZONE 'Asia/Bangkok'), 'YYYY-MM-DD HH24:MI:SS');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cases_updated_at ON cases;
CREATE TRIGGER trg_cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW
    EXECUTE FUNCTION update_cases_updated_at();


-- ═══════════════════════════════════════════════════════════════════
-- 🔒 ROW LEVEL SECURITY — กันข้อมูลผู้ป่วยรั่วผ่าน anon key
-- ───────────────────────────────────────────────────────────────────
-- เปิด RLS ทุกตาราง + ไม่สร้าง policy ให้ anon → anon อ่าน/เขียนไม่ได้
-- แอพเชื่อมผ่าน "service_role key" ซึ่ง bypass RLS โดยอัตโนมัติ
-- ⚠️ service key = ความลับสูงสุด เก็บใน .streamlit/secrets.toml เท่านั้น
--    ห้าม commit ขึ้น git / ห้ามใส่ในโค้ดฝั่ง client
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE cases          ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE prediction_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE backup_log     ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_settings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings   ENABLE ROW LEVEL SECURITY;
ALTER TABLE override_log   ENABLE ROW LEVEL SECURITY;
-- (ไม่สร้าง policy = ปิดทุก role ยกเว้น service_role ที่ bypass อยู่แล้ว)


-- ═══════════════════════════════════════════════════════════════════
-- VERIFY: ตรวจสอบว่า tables สร้างครบ
-- ═══════════════════════════════════════════════════════════════════
SELECT
    table_name,
    count(*) AS column_count
FROM information_schema.columns
WHERE table_schema = 'orsurg'
  AND table_name IN ('cases', 'audit_log', 'prediction_log', 'backup_log',
                     'room_settings', 'app_settings', 'override_log')
GROUP BY table_name
ORDER BY table_name;

-- คาดหวัง:
-- app_settings    | 2
-- audit_log       | 7
-- backup_log      | 4
-- cases           | 42
-- override_log    | 12
-- prediction_log  | 10
-- room_settings   | 5
