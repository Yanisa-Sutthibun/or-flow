# รายงานตรวจงาน Web Application (ส่วนที่ 2) — 11 มิ.ย. 2026

ผู้ตรวจ: คล็อดคุง (มุมมองพยาบาลนักวิจัยบริหารทางการพยาบาล + ครูวิศวกรรมคอมพิวเตอร์)
ขอบเขต: ทั้ง repo ~18,000 บรรทัด — ตรวจ 3 สายขนาน (ชั้นข้อมูล / ชั้น UI / ML pipeline) แล้ว verify ทุกประเด็นซ้ำด้วยการอ่านโค้ดจริง + รัน compile/ตรวจ artifact ก่อนลงรายงาน
ต่อเนื่องจาก: CODE_REVIEW_PART1 (10 มิ.ย.) · CRITICAL_FIX (10 มิ.ย.) · FIX_SEC_ROBUST_QUALITY + UX_UI_REVIEW + SHARED_BOARD (11 มิ.ย.)

---

## สรุปผู้บริหาร

| ระดับ | จำนวน | หัวข้อเด่น |
|---|---|---|
| 🔴 Critical | 3 | PII ผู้ป่วยขึ้น Supabase **เกิดจริงเช้านี้** · บอร์ดกลางเขียนทับกันข้ามเครื่อง · conformal คาลิเบรตคนละโมเดลกับที่ deploy |
| 🟠 Major | 13 | XSS จาก CSV · connection pool รั่ว · ฟีเจอร์ลบข้อมูลค้างครึ่งทาง · KPI 3 นิยาม · n ในเล่มเพี้ยนจากแถวซ้ำ |
| 🟡 Minor | 14 | รายการในส่วนที่ 6 |

ข่าวดีก่อน: **การแก้จากรีวิวเดิม 18 ข้อ ยืนยันว่าแก้จริง 15 ข้อ** (รวม pkl ขึ้น git แล้ว, PIN ออกจากซอร์สแล้ว, conformal มีจริง, ethics lock แน่นหนา) — ทำงานเก็บงานได้ดีมาก ที่เหลือคือของใหม่ที่โผล่จากฟีเจอร์บอร์ดกลางซึ่งเพิ่งเขียนเมื่อวาน และ 1 ประเด็นวิจัยที่ลึกกว่ารอบที่แล้ว

---

## 0) ⚡ ปลดชนวนวันนี้ — เหตุการณ์ PII ขึ้น cloud (เกิดแล้วจริง ไม่ใช่สมมุติ)

**Timeline ที่ตรวจพบ:**

- 10:35 น. วันนี้ — บอร์ดถูกเซฟขณะ `snapshot_keep_pii = true` และ `db_mode = "supabase"`
  → payload **ชื่อผู้ป่วยเต็ม + HN เต็ม + อายุ + diagnosis ของ 13 เคส** ถูกเขียนขึ้น Supabase
  ที่ตาราง `app_settings` key `board_state_2026-06-11` (หลักฐาน: `data/_board_snapshot.json`
  mtime 10:35 มี `pii_kept: true`, ชื่อเต็ม, hn 9 หลักเต็ม)
- 12:08 น. — secrets.toml ถูกแก้เป็น `snapshot_keep_pii = false` (ถูกต้องแล้ว) แต่**ข้อมูลที่ขึ้นไปก่อนหน้ายังอยู่บน Supabase** จนกว่าจะมีการเซฟทับ/ลบ

**ทำทันที (วันนี้):**

1. ตรวจว่า 13 เคสนั้นเป็นผู้ป่วยจริงหรือข้อมูลทดสอบ — โค้ดกันโหมด demo ไม่ให้เซฟ (`_or_demo`) ดังนั้นถ้าไม่ได้อัปโหลด CSV ทดสอบเอง = ข้อมูลจริง
2. เปิดบอร์ดอีกครั้ง (flag false แล้ว) ให้เซฟ payload แบบ mask ทับ key เดิม **หรือ** ลบตรงใน Supabase SQL Editor:
   `DELETE FROM orsurg.app_settings WHERE key LIKE 'board_state_%';`
3. ลบ/ล้างไฟล์ `data/_board_snapshot.json` ฝั่งเครื่อง (มีชื่อเต็มค้างอยู่)
4. ถ้าเป็นข้อมูลจริง: บันทึก incident ไว้ (วันที่ ขอบเขต การแก้) — เป็นหลักฐาน accountability ตามแนว PDPA และตอบกรรมการได้อย่างมืออาชีพถ้าถูกถาม

**ราก:** ดูข้อ CR-1 — flag นี้ออกแบบให้ "เครื่องใน รพ. เก็บชื่อในไฟล์ local" แต่โค้ดเอา flag เดียวกันไปคุม payload ที่ขึ้น **DB กลาง** ด้วย (`main_or_pages.py:83–105`)

---

## 1) ⚠️ เรื่องหลอกที่ต้องรู้ก่อน: "ไฟล์ถูกตัดท้าย" เป็นภาพลวงของ mount

ตรวจผ่าน WSL/sandbox mount พบ 5 ไฟล์ (`main_or_admin.py, main_or_db.py, main_or_pages.py, tracking_board.py, .gitignore`) **ดูเหมือน**ถูกตัดท้ายกลางบรรทัด และ `git status` ขึ้น M ทั้ง 5 ไฟล์ — แต่ตรวจไฟล์จริงฝั่ง Windows แล้ว **เนื้อหาครบ ตรงกับ HEAD ทุกจุดที่สอบทาน และ compile ผ่านทั้งหมด** สถานะ M เป็นภาพลวงจาก mount (อาการเดียวกับเหตุที่เคยทำไฟล์พังใน commit 6eda323)

**กติกาป้องกัน:** ห้าม `git add/commit/restore` จากสภาพแวดล้อมที่เห็นไฟล์ขาด · ก่อน commit ทุกครั้งรันบน Windows: `python -m py_compile main_or_*.py tracking_board.py` · ถ้า `git status` ขึ้น M ทั้งที่ไม่ได้แก้ ให้สงสัย mount ก่อน

---

## 2) สกอร์บอร์ดยืนยันการแก้จากรีวิวเดิม (18 ข้อ)

| กลุ่ม | ผล | หมายเหตุ |
|---|---|---|
| C1 pkl ขึ้น git | ✅ | `models/honest_v1/resid_*.pkl` tracked จริง + negation ใน .gitignore |
| C2 app_password | ⚠️ | ตั้งแล้ว + fail-closed บน Postgres (`main_or_app.py:713–727`) แต่รหัส**ยาว 3 ตัวอักษร** — สั้นเกินไปสำหรับแอป public URL ควร ≥ 10 ตัว |
| C3 conformal | ⚠️ | มีจริง สูตร finite-sample ถูกต้อง — แต่เจอปัญหาลึกกว่า (CR-3) |
| PIN → secrets fail-closed 4 จุด | ✅ | ไม่พบ 'muke' ในโค้ดแล้ว (เหลือใน comment 1 จุด) |
| add_walkin RETURNING / backup_db guard / model_version จริง / init_db ข้อความไทย / unknown status / room_config 90–98 / utilization DB fallback / autorefresh จริง / sidebar honest_v1 / ethics lock 3 จุด / mask ชื่อแพทย์ 76 คนใน artifact | ✅ ทั้งหมด | ตรวจ line-by-line แล้ว — งานเก็บประณีต |
| snapshot "ไม่เก็บ PII" | ⚠️ | ของจริงคือ **mask** (ชื่อต้นจริง + HN ท้าย 4 ตัว) ไม่ใช่ "ไม่ระบุ" ตามที่บันทึกเดิมอ้าง — ยอมรับได้ถ้าตั้งใจ แต่ต้องเขียนให้ตรงในเล่ม (มาตรา 3.6.4) |

---

## 3) 🔴 Critical (3 ข้อ)

### CR-1 — flag `snapshot_keep_pii` ของเครื่องเดียว ดันชื่อ–HN เต็มขึ้น DB กลางที่ทุกเครื่องใช้ร่วม
- **ตำแหน่ง:** `main_or_pages.py:83–105` — `_keep` คุมทั้งไฟล์ local และ payload ที่ส่ง `save_board_state()` ขึ้น Supabase
- **ผล:** เครื่องใดเครื่องหนึ่งใน รพ. ตั้ง true ตามคู่มือ → ชื่อเต็มผู้ป่วยทั้งวันโผล่บน DB กลางที่ deployment สาธารณะอ่านได้ (เกิดจริงแล้ว — ส่วนที่ 0)
- **แก้:** บังคับ mask เสมอใน payload ที่ขึ้น DB (`save_board_state` รับเฉพาะข้อมูล mask) — flag มีผลแค่ไฟล์ local · เสริม: docstring บรรทัด 89 เขียนไว้เองว่า "ชื่อเต็มไม่ขึ้นเซิร์ฟเวอร์" — ทำโค้ดให้ตรงกับ docstring

### CR-2 — บอร์ดกลาง: lost-update race — เครื่องที่ไม่ได้กดอะไรเขียนทับงานของเครื่องอื่น
- **ตำแหน่ง:** `main_or_pages.py:691–692` (เซฟทั้งบอร์ด**ทุก rerun**) + `:415–433` (pull เฉพาะเปิดครั้งแรก / กด 🔄 / tick 30 วิ) — ไม่มี version check ใดๆ (`save_board_state` เขียนทับตรง)
- **สถานการณ์จริง:** พยาบาล A กด "เข้าห้อง" → ภายใน 30 วิ พยาบาล B แค่เปิด popover (เกิด rerun) → B เซฟ state เก่าทับ → บอร์ด A เด้งกลับเป็น "รอผ่าตัด" งานหายเงียบ ๆ — แบบนี้พยาบาลหน้างานจะ**เลิกเชื่อบอร์ด**เร็วมาก และถ้า `streamlit_autorefresh` import ไม่ผ่าน (try/except เงียบ) จะไม่มี pull เลย ยิ่งทับกันหนัก
- **แก้:** (1) เซฟเฉพาะเมื่อเครื่องนี้เพิ่งเปลี่ยนสถานะจริง (dirty flag ใน `_do_arrive/_do_enter/_do_finish/_do_undo`) ไม่ใช่ทุก render (2) ใส่ `version`/`saved_at` ใน payload แล้วทำ optimistic concurrency: version ใน DB ใหม่กว่า → pull-merge ก่อน ห้ามเขียนทับ (3) ระยะยาวตามแผน v2 ใน SHARED_BOARD doc: เขียนราย-เคสลงตาราง `cases` (ถูกทางแล้ว — เร่งให้เป็นจริง)

### CR-3 — ช่วง conformal ใช้กับ "คนละโมเดล" กับที่คาลิเบรต และปีคาลิเบรตปนอยู่ในชุดเทรนของตัว deploy (research integrity)
- **หลักฐาน:** artifact ที่ deploy เทรนจาก**ข้อมูลทุกปี** (`train_honest_model.py` · `meta.json` n_train=7,654 = ทั้ง CSV รวมปี 2567, XGB 800 ต้น) ขณะที่ q̂ ใน `conformal.json` มาจาก residual ของโมเดล**อีกสเปค**ใน `build_validation_set.py` (เทรน ≤2566, 3,000 ต้น + early stopping) — ขัดกับที่ CRITICAL_FIX doc บันทึกว่า "out-of-sample ไม่ leak"
- **ผล:** (1) coverage guarantee ของ split conformal ใช้ไม่ได้อย่างเป็นทางการ (score มาจากคนละ predictor) (2) ชุดคาลิเบรต 2567 **ไม่ disjoint** กับชุดเทรนของตัว deploy (3) MAE 42.4 ที่โชว์ในแอป/เล่ม เป็นของโมเดลที่**ไม่ใช่**ตัวที่ทำนายบนบอร์ด — กรรมการสอบเจาะตรงนี้ได้
- **แก้ (เลือก 1):** ทางสะอาด = deploy โมเดลสเปคเดียวกับที่ประเมิน (freeze เทรน ≤2566) → q̂ จาก 2567 เป็น conformal แท้ · หรือเขียนในเล่ม/แอปตรง ๆ ว่าเป็น "transferred calibration (approximation)" ไม่เคลม guarantee

---

## 4) 🟠 Major (13 ข้อ)

| # | ประเด็น | ตำแหน่ง | ผล + วิธีแก้ |
|---|---|---|---|
| M-01 | **XSS/HTML injection จาก CSV** — ชื่อผู้ป่วย/หัตถการ/แพทย์ฝังดิบใน `components.html` + `unsafe_allow_html` | `tracking_board.py:232–235, 273–276, 352–356` · `main_or_admin.py:3604–3632` · `main_or_tracking.py` | CSV จาก HIS = input ที่ไม่ trust — อักขระ HTML ทำการ์ดพัง/รัน script ใน iframe ได้ → ทำ helper `esc()` (html.escape) ครอบทุกค่าก่อนฝัง |
| M-02 | **Connection leak บน exception → pool 12 เส้นหมด → แอปล่มทั้งเครื่อง** | `db_connection.py:483, 510–515` + ฟังก์ชัน read จำนวนมากใน `main_or_db.py` (get_summary, get_kpi, get_room_status, get_workload, import_schedule ฯลฯ) ใช้ `conn = get_conn()` โดยไม่มี try/finally | query พังหนึ่งครั้ง = connection ไม่คืน pool → สะสมจนเต็ม · แก้: ใช้ `with db_session() as conn:` (มีอยู่แล้ว :627–641) ทุกจุด + ตอน rebuild pool เรียก `closeall()` ของ pool เก่า |
| M-03 | **เครื่องมือลบข้อมูล 3 จุดอ่อนรวมกัน**: (ก) `clear_all_data` บน PG — statement พังแล้ว `except: result=0` โดยไม่ rollback → ที่เหลือ fail เงียบ ผู้ใช้คิดว่าลบสำเร็จ (ข) "ลบเฉพาะวันที่" **ค้างครึ่งทาง** — มี date picker แล้วจบที่ `import _gc_count` เฉย ๆ ไม่มีปุ่ม/นับ/ลบ (UI ตัน) (ค) ลบทั้ง DB ใช้แค่ checkbox เดียว ไม่มี type-to-confirm | `main_or_db.py:303–327` · `main_or_admin.py:3969–3985` | (ก) rollback ใน except ราย table + รายงาน error จริง (ข) เขียน branch ให้จบ หรือคอมเมนต์ทิ้งทั้ง block ก่อน (อย่าปล่อย UI ตัน) (ค) ให้พิมพ์คำยืนยัน เช่น "DELETE" + backup อัตโนมัติก่อนลบ |
| M-04 | `rebackfill_ai_predictions` ประทับ `ai_model_ver='honest_v1'` ทุกแถวแม้ค่าจริงมาจาก fallback (median/60 นาที) | `main_or_db.py:1271, 1281–1283` vs `_repredict_case_row:1299–1330` | ที่มาของตัวเลขวิจัยผิด → ให้เก็บ `result['source']` จริงลง `ai_model_ver` |
| M-05 | Temporal leakage เส้น fallback ตอน backfill: `predict_from_local_history` ใช้ median จากเคส**ทุกยุค**รวมอนาคต | `main_or_db.py:203–209` (ไม่มีเงื่อนไขวันที่) | เพิ่ม `as_of_date` (`AND op_date < ?`) + ตัดแถว fallback ออกจาก ai_df หลังแก้ M-04 |
| M-06 | `override_log` เก็บ**ชื่อแพทย์จริง** — ไม่อยู่ในขอบเขต `mask_unmasked_staff` | `main_or_db.py:1501–1507` vs รายการ mask `:571–576` | เพิ่ม `("override_log","surgeon_name")` เข้า mask groups |
| M-07 | Excel export อ่าน key ที่ `get_summary` ไม่เคยคืน (`total_treatment`, `total_revenue`, `ai_accuracy` — มรดกแอป Minor OR) → รายงานโชว์ 0 บาท + ตาราง AI หาย | `main_or_export.py:91–94, 110–111` | ตัดแถวการเงิน + คำนวณ MAE จาก `summary['ai_df']` ที่มีจริง |
| M-08 | **KPI utilization 3 นิยาม 3 หน้า + turnover 4 ช่วง valid** — Dashboard (`get_kpi`: Σdur ÷ 480×ห้องที่มีเคสจบ) vs สถิติย้อนหลัง (mean รายวัน) vs หน้า Utilization (clip 8–16 น., median) · live_link ใช้ฐาน "ห้องที่มีเคสจบ" → เช้า ๆ util เกิน 100% หลอกผู้บริหาร | `main_or_db.py:2233–2241, 2575–2584` · `main_or_utilization.py:220–229,347` · `live_link.py:103–111` · turnover: `2258` (0–180) / `2735` (1–90) / util หน้า (5–180) / `2829` (1–90) | งานบริหาร: **เลือกนิยามเดียว** (แนะนำ clip 8–16 น. ราย ห้อง-วัน) → ฟังก์ชันกลางใน main_or_db + footnote นิยามทุกหน้า — ตัวเลขในเล่มต้องอ้างนิยามนี้ |
| M-09 | DB save บอร์ดกลางล้มเหลว**เงียบ** แต่ caption โชว์ "ซิงก์ทุกเครื่องอัตโนมัติ" เสมอ | `main_or_db.py:820–825` (กลืน exception คืน False) + `main_or_pages.py:104–107` (ไม่เช็ค return), `:435–436` | เช็ค return; fail ติดกัน >2 ครั้ง → st.warning "บอร์ดกลางออฟไลน์ — เครื่องนี้ยังไม่แชร์" |
| M-10 | เปิดจอข้ามเที่ยงคืน → เคสเมื่อวานถูกเซฟด้วย key **วันใหม่** → เช้ามาเห็นเคสเก่าปนบอร์ดวันนี้ | `main_or_pages.py:425–431, 691–692` (ไม่มีเช็ควันเปลี่ยน) | เก็บ `_board_last_date`; ถ้า ≠ วันนี้ → ล้าง cases + บังคับ pull |
| M-11 | **แถวซ้ำ 314 แถว (292 key)** ใน main_or_history.csv ไม่ถูก dedup ใน train/calibrate/compare (ปี 2567 ซ้ำ 65 แถว = 3.2% ของชุดคาลิเบรต) | `train_honest_model._load()` · `build_validation_set.main()` · `compare_models.load()` (ขณะที่ predictor v2 dedup แล้ว) | n=7,654/2,004 ในเล่มสูงเกินจริง ~4% → dedup ด้วย case_key แบบเดียวกับ `main_or_predictor.load_default` แล้วรันตัวเลขใหม่**ก่อน freeze เล่ม** |
| M-12 | `test_minimal.py` (git-tracked) โชว์ `app_password` เป็น plaintext บนจอถ้าถูกรัน + มีชื่อแพทย์จริง hardcode — และทดสอบเฉพาะ legacy v2 | `test_minimal.py:~74, 84–88` | ลบบล็อก secrets (เหลือ "set/ไม่ set") + เปลี่ยนชื่อเป็น SURG_xxx + เพิ่ม smoke test ของ or_time_model แทน |
| M-13 | `board_state_YYYY-MM-DD` สะสมบน cloud ตลอดกาล ไม่มี cleanup → ข้อมูลผู้ป่วย (แม้ mask) เก็บถาวร ขัดหลัก data retention ที่เขียนในเล่มเอง | `main_or_db.py:818–825` — ไม่มี DELETE ที่ไหนใน repo | ใน `save_board_state` ลบ key เก่ากว่า 7 วัน (parameterized) |

---

## 5) 🟡 Minor (สรุปย่อ)

| # | ประเด็น | ตำแหน่ง |
|---|---|---|
| m-01 | เซฟบอร์ดขึ้น Supabase ทุก render แม้ไม่มีอะไรเปลี่ยน (10–30KB/ครั้ง) → hash เทียบก่อนเซฟ | `main_or_pages.py:691–692` |
| m-02 | `DATE('now')` = UTC ไม่ใช่เวลาไทย → ช่วง 00:00–07:00 เคสรับเวรเมื่อวานหาย | `main_or_db.py:3232, 3263` |
| m-03 | `predict_from_local_history` scan ทั้งตาราง + regex ถูกเรียกซ้ำสูงสุด 9 ห้อง/render → หน้าบริหารช้า | `main_or_db.py:203–217` ← `get_room_status:2184–2200` |
| m-04 | except เงียบกลืนข้อมูลวิจัย human-vs-AI (`log_override` ฯลฯ) — ควร `_plog.exception` ก่อน return | `main_or_db.py:1511, 1530, 1549` |
| m-05 | `payload.get('pii_kept', True)` default ผิดด้าน (ควร False) | `main_or_pages.py:139` |
| m-06 | `SET search_path` ต่อสตริงจาก secrets — validate `^[A-Za-z_][A-Za-z0-9_]*$` เป็น hardening | `db_connection.py:466, 482` |
| m-07 | `supabase_schema.sql` (root) เป็น schema เก่าของ Minor OR ที่มีคอลัมน์ `hn` — เสี่ยงหยิบผิดไฟล์ไปรัน → ย้าย/ลบ | root |
| m-08 | `width='stretch'` (≥1.40) ปนกับ `use_container_width` (deprecated) 70+ จุด + requirements ระบุ ≥1.32 → pin version ให้ตรงกับ API ที่ใช้ | `tracking_board.py` vs `main_or_admin.py` |
| m-09 | restore ข้ามเครื่อง: `time_entered_or` ที่ deserialize ไม่เป็น datetime → นาฬิกาสด/overrun ไม่ทำงานเฉพาะเคสนั้น → normalize หลังโหลด snapshot | `tracking_board.py:334–336, 158–159` |
| m-10 | `new Date("YYYY-MM-DD HH:MM:SS")` ใน timer หน้า tracking เก่า — เพี้ยนข้าม browser/timezone (หน้าไม่ถูก route แล้ว) | `main_or_tracking.py:1497` |
| m-11 | `_do_finish` ยังเขียน `case_history.csv` (ephemeral บน cloud, ซ้ำซ้อนกับ DB) | `main_or_pages.py:623–624` |
| m-12 | `_norm_date` ใน import ไม่แปลง พ.ศ. (ขณะที่ `_parse_thai_date` ไฟล์เดียวกันแปลงถูก) → ปี 2569 หลุดเป็น ค.ศ. เงียบ ๆ + dedup key ยุบเคส cancelled ที่หน้าตาเหมือนกัน | `import_historical.py:68–75, 289–298` |
| m-13 | conformal ±103 นาทีค่าเดียวทุกเคส → เคสสั้นได้ช่วงกว้างเกินประโยชน์ — เขียนเป็น limitation + เสนอ normalized/CQR เป็น future work (มี clip ≥5 แล้ว ดี) | `or_time_model.py:112–115` |
| m-14 | serve ไม่ส่ง `dow`/`month` ใน `main_or_core` (แต่ `main_or_db` ส่ง) + นิยาม `planned_hour` ปัดต่างจากตอนเทรน → เคสเดียวกันสองหน้าจอเลขต่างได้ | `main_or_core.py:100–105` vs `train_honest_model.py:55` |

อื่น ๆ ที่ควรรู้: `app_password` ยาว 3 ตัวอักษร (สั้นมากสำหรับแอป public URL — ตั้ง ≥10) · `admin_pin` 4 หลัก (พอรับได้ถ้า fail-closed อยู่ แต่ยาวกว่านี้ก็ดี) · `backup_db` กลายเป็น dead code ไม่มี caller · `build_validation_set.py:108` ใส่ `op_type='elective'` ทุกแถว — ถ้าหน้า AI แยกตาม op_type เลขจะเพี้ยน

---

## 6) มุมมองพยาบาลนักวิจัยบริหารทางการพยาบาล

**ความเชื่อมั่นหน้างานคือทุกอย่าง** — CR-2 (ปุ่มที่กดแล้วเด้งกลับ) อันตรายกว่า bug ทั่วไป เพราะพยาบาลจะตัดสินระบบจากครั้งแรกที่งานตัวเองหาย ระบบที่ "ถูก 95%" แต่หายเงียบ 5% จะถูกทิ้งกลับไปใช้กระดาน whiteboard แก้ CR-2 ให้เสร็จก่อนเปิดใช้หลายเครื่องจริง

**Governance ข้อมูล:** เหตุการณ์ส่วนที่ 0 ชี้ว่าระบบต้องมี (1) หลัก "ข้อมูลที่ออกนอก รพ. = mask เสมอ ไม่มี flag ยกเว้น" (2) data retention จริงใน DB (M-13) ให้ตรงกับที่เขียนในมาตรา 3.6.4 (3) บันทึก incident สั้น ๆ เมื่อเกิดเหตุ — สามข้อนี้เขียนเป็น SOP หนึ่งหน้าแนบเล่มได้เลย และเป็นจุดที่กรรมการสาย admin ชอบ

**KPI ต้องนิยามเดียว (M-08):** ในฐานะผู้บริหาร ถ้า utilization หน้า Dashboard บอก 92% แต่หน้า Utilization บอก 71% ความเชื่อถือทั้งระบบพังในประชุมเดียว เลือกนิยาม (แนะนำ clip 8–16 น. ราย ห้อง-วัน — ตรงกับ literature เรื่อง OR utilization) แล้วใส่ footnote ทุกหน้า + ใช้เลขเดียวกันในเล่ม

**สำหรับเล่ม/สอบ:** CR-3 และ M-11 ต้องเคลียร์**ก่อน freeze ตัวเลข** เพราะกระทบ n, MAE และ coverage ที่จะพิมพ์ลงเล่ม — แก้ตอนนี้ราคาถูก แก้หลังส่งเล่มราคาแพง

---

## 7) มุมมองครูวิศวะคอม

**จุดแข็งที่เห็นชัด (ของจริง ไม่ใช่ปลอบ):** วินัยเอกสารใน docs/ ระดับมืออาชีพ — ตรวจย้อนได้ทุกการตัดสินใจ · ethics lock ทำถูกหลักและตรวจแล้วแน่น 3 จุด · temporal split + ภาคผนวกสาธิตโทษ random split ใน compare_models เป็นจุดที่กรรมการจะชม · การแก้ตามรีวิวเดิม 15/18 ข้อ ยืนยันได้จริงในโค้ด — อัตราเก็บงานแบบนี้หายาก

**คะแนน (เกณฑ์ production-readiness):**

| ด้าน | เกรด | เหตุผลสั้น |
|---|---|---|
| สถาปัตยกรรม/แยกโมดูล | B+ | แยกชั้นดี · admin 3,952 บรรทัดควรแตกไฟล์ |
| ความถูกต้อง ML/วิจัย | B | ระเบียบวิธีป้องกันได้ แต่ CR-3 + M-11 ต้องปิดก่อนสอบ |
| ความปลอดภัย/PDPA | C+ | เจตนาดี เครื่องมือครบ (mask/secrets/fail-closed) แต่ CR-1 หลุดจริง + M-01 ยังเปิด |
| ความทนทาน | B- | error handling ภาษาไทยดีมาก แต่ M-02 pool leak คือระเบิดเวลา |
| UX สำหรับพยาบาล | B+ | สไลซ์ฟอนต์/สีทำถูกทาง · เหลือความสม่ำเสมอ |

**การบ้าน 4 ข้อ (เรียงตามนิสัยที่อยากให้ติดตัว):**
1. ทุกครั้งที่จับ DB connection → `with db_session() as conn:` ไม่มีข้อยกเว้น
2. ทุกค่าที่มาจากภายนอก (CSV/ผู้ใช้) ก่อนเข้า HTML → ผ่าน `esc()` ตัวเดียวทั้งแอป
3. ฟีเจอร์ destructive เขียนให้จบใน commit เดียว — อย่าปล่อย UI ตันแบบ "ลบเฉพาะวันที่"
4. state ที่แชร์ข้ามเครื่อง ไม่มีคำว่า "เขียนทับเฉย ๆ" — ต้องมี version เสมอ

---

## 8) ลำดับการแก้ที่แนะนำ

**วันนี้:** ส่วนที่ 0 (ลบ/ทับ board_state บน Supabase + ล้างไฟล์ local) · CR-1 (บังคับ mask payload ขึ้น DB)
**สัปดาห์นี้ (ก่อนใช้บอร์ดกลางหลายเครื่องจริง):** CR-2 (dirty-flag + version) · M-09, M-10 (ความเชื่อถือบอร์ด) · M-03 (เครื่องมือลบ) · M-01 (esc) · M-02 (db_session)
**ก่อน freeze ตัวเลขลงเล่ม:** CR-3 (โมเดลเดียวตลอดสาย ประเมิน→คาลิเบรต→deploy) · M-11 (dedup + รันใหม่) · M-04/M-05 (label + leakage ใน backfill) · M-08 (นิยาม KPI เดียว)
**ก่อนสอบ:** M-12 (ไฟล์ test) · m-13/m-14 เขียนเป็น limitation · อัปเดตมาตรา 3.6.4 ให้ตรงกับพฤติกรรม mask จริง

---

*ตรวจโดย: คล็อดคุง · วิธีตรวจ: อ่านโค้ดทุกไฟล์หลัก + ยืนยัน line number ทุก finding + รัน py_compile + ตรวจ artifact/secrets/git จริง · ไม่มีการแก้ไขไฟล์ใด ๆ ในรอบนี้ (ตามที่ตกลง)*
