# thesis_ML_v2 — วิธีใช้ในแอป OR Flow

## ใช้ในแอป (shadow mode ก่อน)
```python
from predictor import ModelV2            # วางโฟลเดอร์นี้ที่ main_OR_app/models/thesis_ML_v2/
mv2 = ModelV2()                          # โหลดครั้งเดียว (ในแอปครอบด้วย st.cache_resource)
r = mv2.predict_case({
    'procedure': 'LC', 'diagnosis': 'GALLSTONE', 'surgeon': 'ชื่อแพทย์',
    'division': '75', 'or_room': 93, 'age': 55, 'sex': 'หญิง',
    'ASA': '2', 'is_inpatient': 1, 'planicu': 0, 'blood': 0, 'BMI': 24.5,
})
# → {'predicted_min': .., 'range90': (lo, hi), 'proc_n': .., 'confidence': .., ...}
```
ช่องไหนไม่มีข้อมูล → ไม่ต้องส่ง (ระบบเติม median/Unknown ให้แบบเดียวกับตอนเทรน)

## ⚠️ ก่อนขึ้น cloud/repo สาธารณะ
- `model.pkl` + `ohe_categories.json` มี **ชื่อแพทย์จริง** → sanitize แบบเดียวกับ honest_v1
- ห้อง 90-97 (ตึกใหม่) ไม่อยู่ในชุดเทรน (11-17) — โมเดล ignore ห้องอัตโนมัติ ไม่ error

## Shadow mode ที่แนะนำ
บอร์ดยังแสดง honest_v1 ตามเดิม · เรียก thesis_ML_v2 คู่กันแล้วบันทึกลง log
(case_id, pred_v1, pred_v2, actual) → ได้ตารางเทียบ head-to-head บนเคสจริง
โดยไม่กระทบหน้างาน และไม่ขัด ethics lock
