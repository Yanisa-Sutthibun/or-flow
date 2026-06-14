# Hardening รอบ 3 — PII + รองรับ 10+ ผู้ใช้พร้อมกัน (12 มิ.ย. 2026)

ผู้ตรวจ/ผู้แก้: คล็อดคุง · ต่อจาก CODE_REVIEW_PART2 + 5 commits การแก้เมื่อคืน (กลุ่ม A–D + CR-1/2/3)
วิธีตรวจ: ตรวจรับ commit เมื่อคืนทีละข้อ + กวาด PII ทุกทางออก + คำนวณภาระ DB ต่อ 10 ผู้ใช้
ทุกการแก้รอบนี้ verify ด้วย reconstruct-compile (HEAD + edits) และ **unit test จำลอง merge บอร์ดกลาง 5 สถานการณ์ — ผ่าน 10/10**

---

## 1) ผลตรวจรับการแก้เมื่อคืน

แก้จริงยืนยันได้ ✅: M-03, M-04, M-05, M-07, M-09, M-10, M-12, M-13, CR-1, CR-3 (โครงสร้าง), conn-leak 5 จุดหลัก, dedup 2/3 ไฟล์ + รันเลขใหม่จริง (n_train 7,654→5,401 · n_calib 1,939)
ทำบางส่วน ⚠️: M-01 (esc หลุด 5 จุด), M-02 (เหลือ leak ~23 จุด cold-path), M-08 (หน้า Utilization ยังนิยามเก่า), CR-2 (โครงถูกแต่ mutation หลุด dirty 3 จุด)
**บั๊กใหม่จากการแก้เมื่อคืน 10 ตัว — ตัวระดับสูง 3 ตัวแก้แล้ววันนี้ทั้งหมด** (ดูส่วนที่ 2)

## 2) แก้วันนี้ (7 ไฟล์ · compile ผ่านทุกไฟล์)

### กันงานพยาบาลหายบนบอร์ดกลาง (หัวใจ 10 ผู้ใช้)
| แก้ | ไฟล์ |
|---|---|
| ✏️ แก้เวลา/ย้ายห้อง + ปุ่ม "จำหน่าย" ไม่เคย mark dirty → ไม่เซฟขึ้นบอร์ดกลาง แล้วโดน pull ทับใน 30 วิ (งานหายเงียบ) → เพิ่มพารามิเตอร์ `mark_dirty` เรียกครบทุกจุด | tracking_board.py + main_or_pages.py |
| 📤 ส่งเข้า OR Board + การถอนเคส not_arrived ตอนอัปโหลดซ้ำ ไม่ mark dirty → ตั้ง dirty (แบบ bulk) | main_or_app.py |
| เซฟขึ้น DB **ล้ม** แต่ dirty ถูกเคลียร์ → tick ถัดไป pull ทับงานที่ยังไม่ขึ้น DB → `_save_board_snapshot` คืนผลจริง, ล้มแล้ว**คง dirty** (กัน pull + retry อัตโนมัติ + เตือนเมื่อล้ม >2 ครั้ง) | main_or_pages.py |
| "ล้างกระดาน" ไม่ติดข้ามเครื่อง (ลบ key → เครื่องอื่น fallback ไฟล์ local → เคสผีคืนชีพ) → เขียน **payload ว่าง + version+1** แทนการลบ key | main_or_pages.py |
| เคสซ้ำ 2 แถวเมื่อสองเครื่องอัปโหลดตารางเดียวกัน (id = uuid สุ่มต่อเครื่อง) → **id deterministic** จาก hash(hn·ชื่อ·วันที่·หัตถการ·เวลา·ลำดับ) ทั้ง 2 parser | main_or_app.py |

### Connection pool (จุดล่มทั้งระบบ)
| แก้ | ไฟล์ |
|---|---|
| 🔴 pool เต็มชั่วคราว → โค้ดเดิม `closeall()` = ตัด connection ที่ session อื่นกำลังใช้ → ทุกคน error พร้อมกัน ("pool เต็มแป๊บเดียวกลายเป็น outage") → แยก `PoolError` ออกมา **retry + backoff (0.3/0.7/1.5 วิ) ห้าม closeall** · rebuild เฉพาะ pool พังจริง | db_connection.py |
| pool 12 → **20 (ตั้งได้ผ่าน secrets `db_pool_max`)** + TCP keepalives (กัน connection เน่าหลัง idle ข้ามคืน — ผู้ใช้คนแรกตอนเช้าไม่เจอ error) + sslmode=require อัตโนมัติถ้า URL ไม่ระบุ (override ได้ด้วย `db_sslmode`) | db_connection.py |
| log_override / complete_override / reset_override_actual (ถูกเรียกทุกการกดปุ่มบนบอร์ด) leak connection เมื่อ exception → try/finally + log สาเหตุ (เดิมกลืนเงียบ — แถวงานวิจัย human-vs-AI หายไร้ร่องรอย) | main_or_db.py |
| init_db รันทุก rerun (ยืม connection ฟรีทุก 30 วิ × ทุกเครื่อง) → รันครั้งเดียวต่อ session | main_or_app.py |

### PII
| แก้ | ไฟล์ |
|---|---|
| 🔴 แผงแจ้งเตือนหน้าบริหารโชว์**ชื่อเต็มผู้ป่วย** (จากบอร์ดสด) → mask ที่ต้นทาง | live_link.py |
| XSS ที่เหลือ 5 จุด: แจ้งเตือน, แพทย์วันนี้, การ์ดแพทย์, เคสรับเวร (mask ด้วย), preview อัปโหลด → `_esc()` ครบ | main_or_admin.py + main_or_app.py |
| `procnote` (free text จาก HIS) ติดขึ้น cloud โดยบอร์ดไม่ได้ใช้ → ตัดออกจาก payload | main_or_pages.py |
| หน้า "ความแม่น AI" พังทั้งหน้า (KeyError — validation CSV รุ่นใหม่ไม่มี procedure_name) → guard | main_or_admin.py |

## 3) คำตัดสิน 10+ ผู้ใช้ (จากการคำนวณจริง)

ใช้งานปกติ: 12 sessions × ~5-8 DB round-trip ต่อรอบ 30 วิ ≈ **0.6 connection พร้อมกันโดยเฉลี่ย** จาก 20 — สบาย · จุดที่เคยทำให้ burst เช้ากลายเป็นล่มทั้งระบบ (closeall + ไม่มี retry) ปิดแล้ว · บอร์ดกลางเขียนเฉพาะตอนมี action จริง (~120 ครั้ง/วันรวมทุกเครื่อง) — ไม่มีปัญหา lock

**ความเสี่ยงคงเหลือ (ยอมรับได้ / เขียนเป็น limitation):**
1. merge ไม่มี CAS แท้ — สองเครื่องเซฟห่างกัน <300ms ยังทับกันได้ (โอกาสต่ำมาก + ผลจำกัดราย-เคส) → เขียนใน limitation บทที่ 5
2. ทุกเครื่องอ่าน payload เต็ม (~30-60KB) ทุก 30 วิ → egress Supabase ~GB/วัน ถ้า quota ตึงค่อยทำ version-check ก่อนดึงเต็ม
3. M-02 cold-path อีก ~20 ฟังก์ชัน (รายงาน/สถิติ — เรียกน้อย) ยังเป็น `conn = get_conn()` แบบเก่า
4. search_path บน transaction pooler (port 6543) — ทำงานได้แต่ตามทฤษฎีไม่การันตี 100% · สคริปต์ CLI ควรชี้ port 5432
5. หน้า Utilization ยังนิยามต่างจาก get_kpi (footnote ระบุเกินจริง) + ตัวเลข MAE ใน or_time_model docstring อ้างผิดแถว — **2 จุดนี้ต้องเคลียร์ก่อน freeze เล่ม**
6. เลข AI accuracy สะอาดจริงต้องกด **rebackfill 1 รอบ** (แถว ai_model_ver=NULL/ml_v7 เก่า)

## 4) เช็กลิสต์ฝั่งมุ้กก

1. **รีสตาร์ทแอป** ทุกเครื่องที่เปิดค้าง (โหลดโค้ดใหม่)
2. ทดสอบ 2 เครื่อง: เครื่อง A กด "เข้าห้อง" → B เห็นภายใน 30 วิ · B กด ✏️ แก้เวลา → A เห็น · A ล้างกระดาน → B ว่างภายใน 30 วิ
3. commit **จากเครื่อง Windows เท่านั้น** หลังรัน `python -m py_compile` 7 ไฟล์: tracking_board, main_or_pages, main_or_app, main_or_db, db_connection, live_link, main_or_admin
   ```
   git add -A
   git commit -m "hardening: 10+ users (pool retry/keepalives/dirty-fix/clear-board/deterministic-id) + PII (alerts mask, esc ครบ, procnote ตัด) + AI page guard"
   ```
4. (ถ้ายังไม่ได้ทำ) `python purge_board_state.py` ล้าง snapshot เก่าบน Supabase
5. ลบบรรทัด `snapshot_keep_pii` ใน secrets.toml ได้ (ตายแล้ว) · เพิ่ม `db_pool_max = 20` เฉพาะถ้าอยากปรับ
6. กด rebackfill ในหน้า Maintenance 1 รอบ (ข้อ 3.6)
