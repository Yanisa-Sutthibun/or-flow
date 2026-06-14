# CR-3 — แก้ conformal ให้ตรงโมเดลที่ใช้จริง + กันปี 2567 leak

วันที่: 11 มิ.ย. 2026 · ไฟล์: `train_honest_model.py`, `build_conformal.py`, `build_validation_set.py` (deprecated), `or_time_model.py`

## ปัญหาเดิม (research integrity)
1. โมเดลที่ deploy (`honest_v1`) เทรน **ทุกปี รวม 2567** (n_train=7,654) ทั้งที่ docstring เขียนว่า "≤2566 ไม่ leak"
2. ค่า q̂ (ช่วง ±นาที) + MAE 42.4 มาจาก **โมเดลคนละตัว** (`build_validation_set.py`: ≤2566, 3,000 ต้น + early stopping)
3. ผล: (ก) coverage guarantee ของ split conformal ใช้ไม่ได้ (คนละ predictor) (ข) 2567 ไม่ disjoint กับชุดเทรนของตัว deploy (ค) MAE ที่โชว์ไม่ใช่ของโมเดลบนบอร์ดจริง

## ทางแก้ (เลือก "ทางสะอาด")
โมเดลที่ deploy = โมเดลที่ประเมิน = โมเดลที่คาลิเบรต **ตัวเดียวกัน**

- `train_honest_model.py`: เทรน **เฉพาะ ค.ศ.≤2023 (พ.ศ.2564–2566)** กัน 2567 ไว้ hold-out
  แล้วทำนาย hold-out 2567 ด้วย **โมเดลตัวนี้เอง** → เขียน `validation_{target}.csv` + บันทึก
  ผลทดสอบลง `meta.json` (`test_2567`)
- `build_conformal.py`: คำนวณ q̂ จาก `validation_room_use.csv` (ที่มาจากโมเดล deploy) → split conformal แท้
- `build_validation_set.py`: **DEPRECATED** — ใส่ guard กันรันทับ (สเปคต่าง 3,000 ต้น) เว้นแต่ตั้ง `ALLOW_LEGACY_VALIDATION=1`
- `or_time_model.py`: แก้ตัวเลข docstring ให้ตรงโมเดลจริง

## ผลหลังแก้ (regenerate แล้ว)

| | room_use (ครองห้อง) | surg_time (ผ่าตัด) |
|---|---|---|
| เทรน (≤2566) | 5,650 เคส | 5,583 เคส |
| ทดสอบ hold-out 2567 | n=2,004 | n=1,992 |
| **MAE** | **42.1 นาที** (เดิมโชว์ 42.4) | **37.9 นาที** (เดิม 38.1) |
| median AE | 24.6 | 21.8 |

conformal q̂ (ครึ่งกว้างช่วง, room_use) จากโมเดล deploy:

| coverage | q̂ (นาที) | empirical coverage (temporal check) |
|---|---|---|
| 80% | 63.0 | 0.776 |
| 90% | 102.4 (เดิม 103) | 0.865 |
| 95% | 149.1 (เดิม 149) | 0.933 |

➡️ **ค่าแทบไม่เปลี่ยน** — ตัวเลขในเล่มไม่ต้องรื้อ แต่ตอนนี้**ป้องกันสอบได้เต็มปาก**:
โมเดล/ค่า MAE/ช่วง ±นาที มาจากโมเดลตัวเดียวกัน และ 2567 เป็น hold-out จริง

## ความปลอดภัยข้อมูล
- artifact ใหม่ทุกไฟล์ mask ชื่อแพทย์เป็น `SURG_xxx` (surg_keys_masked=True)
- `validation_*.csv` มีแค่ op_date / predicted / actual — ไม่มีชื่อ/HN (PDPA-safe)

## ค้างไว้ให้ตัดสินใจ (ไม่บังคับ)
- `compare_models.py` + ตารางเปรียบเทียบโมเดลในเล่ม ใช้สเปค early-stopping (MAE 42.4) — ต่างจากโมเดล deploy เล็กน้อย (42.1)
  ถ้าต้องการให้ "ตารางเปรียบเทียบ" ใช้สเปคเดียวกับ deploy เป๊ะ ๆ ต้อง re-run compare_models + อัปเดต Word doc (ค่าจะขยับ ~0.3 นาที)

## ต้องทำก่อน commit (บน Windows — authoritative)
```powershell
python -m py_compile train_honest_model.py build_conformal.py build_validation_set.py or_time_model.py
git add train_honest_model.py build_conformal.py build_validation_set.py or_time_model.py models/honest_v1/ docs/CR3_HONEST_MODEL_FIX_2026-06-11.md
git commit -m "fix(model): CR-3 เทรน deploy ≤พ.ศ.2566 + conformal จากโมเดลตัวเดียวกัน (กัน 2567 leak)"
```
