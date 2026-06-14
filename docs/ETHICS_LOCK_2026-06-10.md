# 🔒 ETHICS LOCK — ปิดระบบ fine-tune (10 มิ.ย. 2026)

## เหตุผล

ethics approval ของวิทยานิพนธ์ครอบคลุม **ข้อมูลเทรน พ.ศ. 2564–2567 (ค.ศ. 2021–2024) เท่านั้น**
แต่ระบบเคยรัน fine-tune ด้วยข้อมูลปี 2568–2569 ไปแล้ว (registry v2–v7, v2 เคยถูก promote)
→ จึงกักกัน artifact + ปิดทางรันซ้ำ จนกว่าจะได้รับ amendment จากคณะกรรมการจริยธรรม

## สิ่งที่ทำ

| รายการ | การจัดการ |
|---|---|
| `models/main_or_{model,pipeline,clusters}_v2..v7.pkl` (เทรนด้วยข้อมูล 68–69) | 🗄 ย้ายไป `data/_quarantine_models_6869/20260610/` (local เท่านั้น — `data/` ไม่ขึ้น git) |
| `models/model_registry.json` | เขียนใหม่: `active_version=1` + บันทึก `ethics_lock` (ของเดิมสำรองใน quarantine: `model_registry_BEFORE_LOCK.json`) |
| `retrain_experiment_panel.py` (ปุ่มสอนเอง — ไม่ถูก route) | ย้ายเข้า quarantine |
| `finetune_pipeline.py` | ถอด `auto_finetune` / `prepare_finetune_data` ออก — เหลือเฉพาะ **parser ไฟล์ HIS** ที่ปุ่ม ③ ใช้ (รวมส่วนดึงชื่อพยาบาล scrub/circ) |
| `process_panel.py` (ปุ่ม ③) | ตัดขั้น "สอนโมเดล" ทิ้ง — เหลือ นำเข้า schedule + intraop + mark เสร็จ + mask ชื่อ · ขึ้นกล่อง info อธิบายว่าปิดเพราะ ethics |
| `retrain_model.py` (engine) | คงไว้แต่ใส่ `_ethics_guard()` — เรียก `retrain()` / `run_experiment()` / `_finetune_model()` จะ `RuntimeError` ทันที จนกว่าจะตั้ง env `OR_ETHICS_AMENDMENT_OK=1` |
| Sidebar | "🔒 แทร็ก fine-tune: ปิดใช้งาน (รอ amendment จริยธรรม) — โมเดลทุกตัวใช้เฉพาะข้อมูล พ.ศ. 2564–2567" |

**สิ่งที่ไม่กระทบ:** ตัวทำนายบนบอร์ด (honest_v1 — เทรน 2564–2567 ✓) · conformal interval
(คาลิเบรตจาก hold-out 2567 ✓) · ปุ่ม ③ นำเข้าข้อมูลเข้า dashboard ใช้ได้ตามเดิม ·
fallback predictor = v1 (ethics-approved)

## ความสอดคล้องหลัง lock

- โมเดลที่ "มีอยู่ในระบบ" ทุกตัว = เทรนจากข้อมูล 2564–2567 เท่านั้น ✓
- การ **นำเข้าข้อมูลปี 68–69 เข้า dashboard** = งานบริการ/บริหารหน่วยงาน (ไม่ใช่การเทรนโมเดล) —
  คนละประเด็นกับขอบเขตข้อมูลเทรน
- ⚠️ **ประเด็นที่ควรถามอาจารย์ที่ปรึกษา/IRB ให้ชัด:** การ "ประเมินความแม่นของโมเดลบนข้อมูล
  ปี 2568+" (แท็บ AI Prediction → แหล่งข้อมูลสด, prospective coverage) ถือเป็นการใช้ข้อมูล
  เพื่อการวิจัยหรือไม่ — ถ้าจะรายงานตัวเลขนี้ "ในเล่ม" ควรมี amendment ครอบ /
  ถ้าใช้เป็น monitoring ภายในหน่วยงานเฉยๆ มักไม่ต้อง (ยืนยันกับ IRB ของสถาบัน)
- ตัวเลขที่ปลอดภัยสำหรับเล่ม ณ ตอนนี้ = ชุดทดสอบปี 2567 (hold-out) ทั้ง MAE และ conformal

## ประโยคสำหรับเล่ม/ตอบกรรมการ

"ระบบออกแบบกลไก continuous learning (champion–challenger พร้อม locked test set) ไว้แล้ว
แต่**ปิดการใช้งานโดยเจตนา** เนื่องจากข้อมูลหลังปี 2567 อยู่นอกขอบเขตการรับรองจริยธรรม
ปัจจุบันโมเดลที่ให้บริการคงที่ (frozen) ตามชุดข้อมูลที่ได้รับอนุมัติ และเสนอการขยายขอบเขต
ข้อมูล (amendment) เป็นงานต่อยอด" — เปลี่ยนจุดเสี่ยงให้เป็นหลักฐาน ethics awareness

## วิธีคืนระบบ (หลังได้ amendment เป็นลายลักษณ์อักษร)

```bash
# 1. ย้าย artifact กลับ
move data\_quarantine_models_6869\20260610\*.pkl models\
# 2. กู้ registry
copy data\_quarantine_models_6869\20260610\model_registry_BEFORE_LOCK.json models\model_registry.json
# 3. ปลดกุญแจ engine (ตั้งทุกครั้งที่จะเทรน — ไม่ตั้งถาวร)
set OR_ETHICS_AMENDMENT_OK=1
# 4. กู้โค้ด UI จาก git history (commit ก่อน ethics lock)
git log --oneline -- process_panel.py finetune_pipeline.py
# 5. สำคัญ: เลื่อน AI_EVAL_FROM (main_or_db.py) ให้พ้นช่วงข้อมูลที่ใช้เทรนใหม่
```
