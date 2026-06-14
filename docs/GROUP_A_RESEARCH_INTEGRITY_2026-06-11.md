# Major กลุ่ม A — ความถูกต้องงานวิจัย (M-11 / M-04 / M-05)

วันที่: 11 มิ.ย. 2026

## M-11 — แถวซ้ำใน main_or_history.csv ไม่ถูก dedup
- พบซ้ำ 314 แถว (case_key ซ้ำ) · 2567 ซ้ำ 65 แถว (3.2% ของชุดคาลิเบรต)
- แก้: `train_honest_model._load()` + `compare_models.load()` dedup ด้วย `case_key`
  (เก็บแถวข้อมูลครบสุด แบบเดียวกับ `main_or_predictor.load_default`)
- รันใหม่ทั้ง train + conformal + compare แล้ว

## M-04 — ai_model_ver ปั๊ม 'honest_v1' ทุกแถวแม้มาจาก fallback
- แก้: `_repredict_case_row` คืน `source` จริง (honest_v1/local_history/default/...)
  → `rebackfill_ai_predictions` เก็บ source จริงลง `ai_model_ver`

## M-05 — temporal leakage เส้น fallback + นับ fallback เป็นความแม่น AI
- `predict_from_local_history(..., as_of_date=None)` + SQL `AND op_date < ?`
  (`predict_surgical_time` ส่งวันผ่าตัดให้อัตโนมัติ → backfill ไม่ใช้เคสอนาคต)
- `get_summary`: ดึง `ai_model_ver` + ตัดแถว fallback (default/error/local_history)
  ออกจาก `ai_df` → หน้า "ความแม่น AI" นับเฉพาะผลของโมเดลจริง

## ผลตัวเลขหลัง dedup (ตัวเลขใหม่ที่ต้องใช้ใน "เล่ม")

ข้อมูล: 7,654 แถวดิบ → dedup 7,340 · matched cohort **train 5,336 / test 1,927** (7,263 = 98.95%, คัดออก 77 = 1.05%)

**โมเดล deploy (honest_v1, room_use-valid):** train 5,401 / test 1,939 · **MAE 41.8** (medAE 24.3)
**conformal q̂** (จากโมเดล deploy ทำนาย hold-out 2567): 80%=62.1 · **90%=102.6** · 95%=149.6 · coverage จริง 0.781/0.865/0.937

**ตารางเปรียบเทียบ (matched cohort 5,336/1,927, สเปค 800 ต้น):**

| | ครองห้อง #7 (เลือก) | ครองห้อง RF | ผ่าตัด #7 (เลือก) | ผ่าตัด RF |
|---|---|---|---|---|
| MAE | 41.9 | **41.1** | 37.5 | **37.3** |
| ΔMAE (RF−#7) | −0.80 (CI [−1.73, 0.16] คร่อม 0) | | −0.13 (CI [−1.03, 0.76]) | |

→ RF ต่ำกว่าเล็กน้อยแต่ **ไม่มีนัยสำคัญ** · เลือก #7 ด้วยเหตุผลทางคลินิก (≤15/≤30 สูงกว่า) + อธิบายได้ + มี fallback

## เอกสารที่อัปเดต
- `สรุปความแม่น_อาจารย์วาสินี.docx` (ไฟล์ `_dedup` — ต้นฉบับเปิดค้างใน Word เลยเขียนทับไม่ได้)
  Table 1 (จำนวนเคส) + ตาราง 2/3 ทุกแถว + ΔMAE/CI + random split (ลดลง 2.2 นาที เหลือ 39.7)

## ก่อน commit (บน Windows)
```powershell
python -m py_compile train_honest_model.py compare_models.py build_conformal.py main_or_db.py main_or_core.py
git add train_honest_model.py compare_models.py main_or_db.py main_or_core.py models/honest_v1/ docs/
git commit -m "fix(research): กลุ่ม A — M-11 dedup case_key + M-04 ai_model_ver source จริง + M-05 temporal leakage fallback; re-run train/conformal/compare"
```

## หมายเหตุ
- ตารางเปรียบเทียบใช้ matched cohort (n เท่ากัน 2 ตาราง) → #7 ครองห้อง MAE 41.9 · ส่วนแอป/conformal ใช้ชุด room_use เต็ม → 41.8 (ต่างกัน 0.1 ด้วยเหตุผลเชิงวิธี)
