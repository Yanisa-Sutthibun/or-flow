# รายงานตรวจสอบโค้ดและสถาปัตยกรรม (ส่วนที่ 1) — 10 มิ.ย. 2026

ผู้ตรวจ: คล็อดคุง (บทบาทผู้ตรวจวิทยานิพนธ์ ML + Software Engineering + บริบท OR)
ขอบเขต: แอพที่ deploy (main_or_app/pages/core/db/tracking_board/admin/utilization/db_connection/live_link/process_panel/command_center/room_config/staff_unmask) + ML pipeline (train_honest_model, build_validation_set, finetune_pipeline, retrain_model, or_time_model, main_or_predictor) — โมเดล v1 (honest_v1, เทรน 2564–2567) และ v2 (fine-tune 68–69)

---

## สรุปผู้บริหาร

| ระดับ | จำนวน |
|---|---|
| 🔴 Critical | 3 |
| 🟠 Major | 13 |
| 🟡 Minor | 11 |

ประเด็นใหญ่สุด: **ไฟล์โมเดล (.pkl) ไม่ถูก track ใน git → แอพบน Streamlit Cloud อาจไม่มีโมเดลจริงให้ใช้** และ **ระบบไม่มี Conformal Prediction ตามที่โจทย์วิจัยระบุ** — สองข้อนี้กระทบความถูกต้องของสิ่งที่เขียนในเล่มโดยตรง ควรเคลียร์ก่อนสอบ

---

## 🔴 CRITICAL

### C1 — โมเดล .pkl ทั้งหมดไม่อยู่ใน git → บน Streamlit Cloud ไม่มีโมเดล
- **ตำแหน่ง:** `.gitignore` (บรรทัด `*.pkl` และ `data/`) · `git ls-files models/` เหลือเพียง hier_*.json, meta.json, validation_room_use.csv, model_registry.json
- **ผลกระทบลูกโซ่:**
  1. `or_time_model._load()` (or_time_model.py:33–39) ต้องการ `models/honest_v1/resid_*.pkl` → FileNotFoundError
  2. `main_or_core.predict_surgical_time()` (main_or_core.py:99–119) จับ exception เงียบ → ตกไปใช้ `SurgicalTimePredictor.load_default()` ซึ่งต้องการ `main_or_model_v2.pkl` + `data/historical/main_or_history.csv` → ไม่มีทั้งคู่
  3. สุดท้ายตกไปที่ `predict_from_local_history()` (main_or_db.py:176) = **มัธยฐานจาก DB** หรือค่า default 60 นาที — โดยผู้ใช้ไม่รู้ (sidebar จะแสดงกล่องแดง "ไม่พบ Model" main_or_app.py:830–839)
  4. ค่าทำนายที่ backfill บน cloud ด้วย DB-median คำนวณจากเคส "ทุกช่วงเวลา" รวมเคสอนาคตของเคสที่ประเมิน → **temporal leakage เงียบๆ ในตัวเลข "ความแม่น AI" ฝั่ง DB**
- **วิธีตรวจยืนยัน:** เปิดแอพบน cloud ดู sidebar — ถ้าเห็น "🤖 AI Model: Active" แปลว่า deploy จากที่อื่นที่มี pkl / ถ้าเห็นกล่องแดง = ยืนยันปัญหา
- **วิธีแก้:** อนุญาตเฉพาะโมเดล honest_v1 เข้า git: เพิ่มใน .gitignore `!models/honest_v1/*.pkl` (ไฟล์ residual model เล็ก ไม่มี PII ของผู้ป่วย — แต่ดู M12 เรื่องชื่อแพทย์ใน JSON ก่อน) · **ห้าม** track main_or_history.csv (PDPA) · ออกแบบให้ or_time_model เป็นโมเดลหลักบน cloud (ไม่ต้องใช้ CSV อยู่แล้ว) · เพิ่มแถบเตือนใหญ่กลางจอเมื่อโมเดลโหลดไม่สำเร็จ ไม่ใช่แค่ sidebar

### C2 — `app_password` ใน secrets.toml ว่าง → password gate ถูก bypass
- **ตำแหน่ง:** `.streamlit/secrets.toml` (ตรวจแบบไม่เปิดเผยค่า: `app_password` มีอยู่แต่ค่าว่าง) · `_check_password()` main_or_app.py:701–707 — ไม่มีรหัส = ปล่อยผ่าน (ตั้งใจไว้สำหรับ local dev)
- **ผลกระทบ:** ถ้า Streamlit Cloud ตั้ง secrets แบบเดียวกัน แอพเปิดสาธารณะ ใครมี URL ก็เข้าได้ และเมื่อรวมกับ M1 (PIN อยู่ในซอร์สโค้ด) → คนนอกลบฐานข้อมูลทั้งก้อนได้
- **วิธีแก้:** ตั้ง `app_password` จริงใน Streamlit Cloud → Settings → Secrets · เปลี่ยน logic เป็น "ถ้า db_mode=supabase แล้วไม่มี password → st.stop() พร้อมข้อความเตือน" (ปลอดภัยโดย default บน cloud)

### C3 — ไม่มี Conformal Prediction ในระบบ — ช่วงเวลาที่มีอยู่เป็น heuristic
- **ตำแหน่ง:** grep ทั้ง repo ไม่พบ conformal/nonconformity/coverage/quantile-interval ใดๆ · ช่วงที่มีจริงคือ
  - `main_or_predictor.py:380–383` — `predicted_range` = IQR (Q1–Q3) ของเคสคล้าย หรือ pred±30 นาที (เส้นทาง v2 ที่แทบไม่ถูกใช้ ดู M2)
  - `main_or_core.py:115` — เส้นทางที่ใช้จริง (honest_v1): `predicted_range = (0.6×pred, 1.5×pred)` = ตัวคูณคงที่ ไม่มีหลักสถิติรองรับ และ **UI บอร์ดไม่แสดงช่วงนี้เลย** (แสดงค่าเดียว + ระดับความเชื่อมั่น)
- **ผลกระทบ:** ถ้าบทที่ 3 ของเล่มเขียนว่าใช้ Conformal Prediction → สิ่งที่ deploy ไม่ตรงกับที่เขียน (research integrity) · metric "coverage / interval width" ที่โจทย์ให้ตรวจ **ไม่มีอยู่ในระบบให้ตรวจ**
- **วิธีแก้ (เลือกทางใดทางหนึ่ง):**
  1. **ทำ Split Conformal จริง (แนะนำ — งานไม่มาก):** ใช้ residual จาก calibration set ปี 2567 (มีอยู่แล้วใน validation_room_use.csv): qhat = quantile ของ |error| ที่ 90% → ช่วง = pred ± qhat (หรือทำแบบ normalized ตามขนาด pred) → รายงาน empirical coverage บน test ใหม่ แล้วแสดงช่วงนี้ใน UI
  2. หรือแก้เล่มให้ตรงความจริง: เรียกว่า "empirical range จากเคสคล้าย (IQR)" และอธิบาย limitation ว่าไม่มี coverage guarantee

---

## 🟠 MAJOR

### M1 — PIN ผู้ดูแล hardcode ในซอร์ส ('muke') คุมถึงปุ่มล้างฐานข้อมูล
- **ตำแหน่ง:** main_or_pages.py:207 (`_BOARD_PIN`) · main_or_admin.py:1290 (`_NURSE_PIN`) — PIN เดียวกันปลดล็อก Maintenance ซึ่งมี Clean Wipe ทั้ง DB (main_or_admin.py:3838–3874 → `clear_all_data()`)
- **แก้:** ย้าย PIN ไป `st.secrets['admin_pin']` · เอาปุ่ม Clean Wipe ออกจากเวอร์ชัน cloud (ให้ทำผ่าน script local เท่านั้น) · ทำ rate-limit 