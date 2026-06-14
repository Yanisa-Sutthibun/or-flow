# บันทึกการแก้ Critical Issues — 10 มิ.ย. 2026

> แก้โดยผู้ตรวจสอบ (Part 1 review) ตามคำสั่ง "จัดการ critical ก่อน"
> หลักการที่ยึด: **จอแสดงชื่อจริง (เครื่องที่มี staff_mapping.csv) · Supabase/git เก็บเฉพาะรหัส masked · โมเดลในเล่มห้ามขยับ**

---

## C1 — ชื่อแพทย์จริง 76 คนใน hier_*.json (git-tracked)

**ทำอะไร:**
- `mask_model_artifacts.py` (ใหม่): เปลี่ยน key ของ `surg_med` / `surg_n` ใน
  `models/honest_v1/hier_room_use.json` + `hier_surg_time.json` จากชื่อจริง → รหัส `SURG_xxx`
  (ชุดเดียวกับ staff_mapping.csv ที่ใช้ mask บน Supabase) — **ค่า median/count ไม่แตะ**
- `or_time_model.py`: เพิ่ม `_surgeon_key()` แปลงตอน predict — รับได้ทั้ง
  ชื่อจริง (เครื่องที่มี mapping) / รหัส SURG_xxx (ข้อมูลจาก cloud DB) / artifact เก่า
  คนที่มีหลายรหัส (แถว legacy) → เลือกรหัสที่มีจริงในตารางโมเดล
- `train_honest_model.py`: เทรนครั้งหน้า mask key อัตโนมัติก่อนเขียนไฟล์ (กันหลุดซ้ำ)
- ไฟล์เดิม (มีชื่อจริง) สำรองที่ `data/_backup_model_names/20260610_133329/` (gitignored)

**พิสูจน์โมเดลไม่เปลี่ยน:** ทำนาย 11 เคสทดสอบ (แพทย์รู้จัก 9, ไม่รู้จัก 1, input เป็นรหัส 1)
ก่อน-หลัง mask → **เท่ากัน 11/11 ทั้ง room_use และ surg_time** ✅
และ input ชื่อจริง vs รหัส SURG ของคนเดียวกัน → ผลเท่ากัน ✅

**⚠️ ต้องทำต่อ (ฝั่งมุ้กกี้):** ไฟล์เวอร์ชันเก่า (มีชื่อจริง) ยังอยู่ใน **git history**
ถ้า repo ที่ deploy GitHub เป็น public หรือเคย push:
```bash
# บนเครื่องที่เป็น clone ของ GitHub repo (ทำหลัง commit งานชุดนี้แล้ว)
pip install git-filter-repo
git filter-repo --invert-paths \
  --path models/honest_v1/hier_room_use.json \
  --path models/honest_v1/hier_surg_time.json \
  --refs HEAD~0..HEAD --force   # หรือ purge ทั้ง history แล้ว force-push
git push --force
```
(ถ้า repo เป็น **private** และไม่เคยแชร์ ก็เพียง commit ไฟล์ใหม่ทับ — ความเสี่ยงต่ำ
แต่ purge ไว้ก็สะอาดกว่า — เขียนตอบกรรมการได้ว่า "ไม่มี PII ใน history")

---

## C2 — Conformal Prediction (ของจริง แทน heuristic ×0.6/×1.5)

**วิธีที่ใช้: Split Conformal Prediction (absolute residual score)**
- ชุดคาลิเบรต = `validation_room_use.csv` (ปี พ.ศ. 2567, n=2,004 — out-of-sample
  ของโมเดลเทรน ≤2566 → ไม่ leak)
- `build_conformal.py` (ใหม่) → `models/honest_v1/conformal.json`:

| ระดับ coverage | ครึ่งกว้างช่วง q̂ | temporal check (calibrate 60% แรก → วัด 40% หลัง) |
|---|---|---|
| 80% | ±63 นาที | coverage จริง 77.6% |
| 90% | ±103 นาที | coverage จริง 86.2% |
| 95% | ±149 นาที | coverage จริง 92.9% |

- `or_time_model.predict_detail()` คืน `interval80` / `interval90` ทุกคำทำนาย
- `main_or_core.predict_surgical_time()`: `predicted_range` = ช่วง conformal 90%
  (+ `range_method='conformal'`, `range_coverage=0.90`) — heuristic เดิมเหลือเป็น fallback
  ถ้าไม่มีไฟล์คาลิเบรตเท่านั้น และติดป้าย `heuristic` ให้รู้
- UI: กระดาน (✏️ popover + ฟอร์มเพิ่มเคส) แสดง "โอกาส 9 ใน 10 เคสจะใช้เวลา X–Y นาที"
- แท็บ AI Prediction: เพิ่มแถบ **ความครอบคลุมจริงของช่วง ±q̂ เทียบเป้า 90%**

**ประโยคที่ใช้เขียนในเล่ม/ตอบกรรมการ:**
"ช่วงทำนายใช้ split conformal prediction คาลิเบรตจาก hold-out ปี 2567 (n=2,004)
ที่ระดับความครอบคลุม 90% ได้ช่วง ±103 นาที; การตรวจสอบตามเวลา (calibrate 60% แรก
ของชุดคาลิเบรต → ทดสอบ 40% หลัง) ได้ความครอบคลุมจริง 86.2% สะท้อน distribution shift
เล็กน้อย ระบบจึงรายงาน prospective coverage บนข้อมูลปี 2568+ ควบคู่ในแอป"

> หมายเหตุ: ช่วงกว้าง (±103 นาที) คือความจริงของข้อมูล OR ที่ MAE≈42 + หางยาว —
> ห้ามบีบช่วงให้แคบเพื่อความสวย เพราะ coverage จะหลุดจากที่เคลม

---

## C3 — โมเดล 2 ระบบ (ตัวที่สอน ≠ ตัวที่ทำนาย)

**นโยบายที่เลือก (สอดคล้องกับการตรึงโมเดลในเล่ม):**
- **honest_v1 = ตัวทำนายบนบอร์ด** (ตรึงไว้ → ตัวเลขตรงกับวิทยานิพนธ์ + ethics approval)
- **v2 registry/fine-tune = แทร็กวิจัย (challenger)** เก็บผลเปรียบเทียบ — ไม่เปลี่ยนตัวทำนาย

**ทำอะไร:**
- Sidebar (`main_or_app.py`): แสดงข้อมูล **honest_v1 จริงจาก artifact** (n_train จาก meta.json,
  MAE/±15 จาก conformal.json, ช่วง 90%) — เลิก hardcode "MAE≈42" และเลิกโชว์สถิติ v2 ปนเป็นตัวหลัก
  + บรรทัดแยก "🧪 โมเดลวิจัย v2: ไม่ใช่ตัวทำนายบนบอร์ด"
- `process_panel.py`: ปุ่ม ③ ติดป้ายชัด "fine-tune = แทร็กทดลอง v2 challenger ยังไม่เปลี่ยนตัวทำนายจริง"
  (ข้อความผลลัพธ์ก็แก้แล้ว — ไม่หลอกผู้ใช้ว่า 'AI บนบอร์ดแม่นขึ้นแล้ว')
- **เปิดให้ Streamlit Cloud มีโมเดลจริง:** `.gitignore` ยกเว้น
  `models/honest_v1/resid_*.pkl` (ไฟล์ละ ~0.9MB, ไม่มี PII — เป็น tree ตัวเลขล้วน)
  เดิม `*.pkl` ถูก ignore ทั้งหมด → บน cloud ไม่มีโมเดล → ทำนายจาก median DB เงียบๆ

---

## ของแถมที่แก้พ่วง (เกี่ยวข้องโดยตรง)

1. **fail-closed password** (`main_or_app._check_password`): ต่อ Supabase แต่ไม่ตั้ง
   `app_password` → **ปิดการเข้าถึง** พร้อมข้อความบอกวิธีตั้ง (เดิม = เปิดโล่ง)
   ※ ตอนนี้ secrets.toml ฝั่ง local `app_password` ว่างอยู่ — local โหมด supabase ก็จะโดนล็อกด้วย
   → ตั้งรหัสใน `.streamlit/secrets.toml` ของเครื่องด้วย
2. **กันรหัส mask ชนกัน** (`mask_unmasked_staff` + `assign_codes(start_at=)`):
   เครื่องที่ไม่มี mapping ครบ (เช่น cloud) จะออกเลขรหัสต่อจาก max ที่มีใน DB
   — ไม่ทับเลขเดิม (ก่อนหน้านี้ ถ้ารัน ③ บน cloud จะเริ่ม SURG_001 ใหม่ → ชนกับ local)
3. **เคส Demo ไม่ปนสถิติ**: `_do_finish` ข้ามการเขียน `case_history.csv` เมื่อเป็นเคส demo
4. แท็บ AI Prediction: **เลือกแหล่งข้อมูลชัดเจน** (ชุดทดสอบปี 2567 ↔ ข้อมูลสดปี 2568+)
   เลิกสลับเป็น validation CSV เงียบๆ ทั้งที่ caption เขียนว่า "ปี 2568+" (เดิมคือ misleading)

---

## ผลทดสอบ (รันจริงทั้งหมด)

- ✅ คอมไพล์ผ่าน 12 ไฟล์ที่แตะ
- ✅ baseline equivalence 11/11 — mask ไม่เปลี่ยนคำทำนายแม้แต่นาทีเดียว
- ✅ เส้นทางจริงของแอพ `predict_surgical_time` → `source=honest_v1`,
  `predicted_range=(58,264)@90%`, `range_method=conformal`
- ✅ input รหัส SURG_xxx (แบบข้อมูลจาก Supabase) ให้ผลเท่า input ชื่อจริง
- ✅ ไม่มี key ภาษาไทยเหลือใน hier json ทั้ง 2 ไฟล์
- ✅ staff_mapping.csv ไม่อยู่ใน git index

## ขั้นตอนที่มุ้กกี้ต้องทำเอง (บนเครื่อง Windows)

```bash
cd C:\Dev\main_OR_app
git add -A
git commit -m "fix(critical): mask ชื่อแพทย์ใน model artifacts + split conformal interval + แยก honest_v1/v2 ให้ตรงจริง + fail-closed password"
# (sandbox commit ไม่ได้เพราะ fuse — index ซ่อมแล้ว ใช้งานปกติ)
```
1. มีไฟล์ขยะ `.git/objects/**/tmp_obj_*` ค้าง 23 ไฟล์จากเหตุ fuse — รัน `git gc` หนึ่งครั้งจะสะอาด
2. ตั้ง `app_password` ใน `.streamlit/secrets.toml` (local) และใน Streamlit Cloud → Secrets
3. push ขึ้น GitHub → Streamlit Cloud จะได้ resid_*.pkl + conformal.json → sidebar ต้องขึ้น
   "🤖 AI Model: honest_v1" สีเขียว (ถ้าขึ้นแดง = ไฟล์ไม่ครบ)
4. ตัดสินใจเรื่อง purge git history (หัวข้อ C1 ด้านบน)
5. แนะนำเพิ่ม `?sslmode=require` ต่อท้าย `database_url` ใน secrets
