# Major กลุ่ม B — ความปลอดภัย/ความเป็นส่วนตัว (M-01 / M-06 / M-12 / M-13)

วันที่: 11 มิ.ย. 2026

## M-01 — XSS/HTML injection จากค่า CSV ที่ฝังดิบใน HTML
ค่าจาก HIS (ชื่อผู้ป่วย/หัตถการ/แพทย์/HN) ถูกฝังตรงใน `unsafe_allow_html` / `components.html`
→ อักขระ HTML (`<script>`, `<`, `>`) ทำการ์ดพังหรือรันสคริปต์ใน iframe ได้

**แก้:** เพิ่ม helper `_esc()` = `html.escape()` แล้วครอบทุกค่าก่อนฝัง
- `tracking_board.py` — `_pt_name`, `_pt_meta` (ชื่อ/HN) + `{procedure}·{surgeon}` ทั้ง 3 row builder
- `main_or_admin.py` — surgeon (room card), procedure + `proc_safe` (เดิม escape แค่ `"`), `_name`/`_proc` (คิวรอเข้าห้อง)
- `main_or_tracking.py` — การ์ดผู้ป่วย (name/HN/proc/surgeon)
- ทดสอบ: `html.escape('<script>...')` → `&lt;script&gt;...` คงภาษาไทยปกติ

## M-06 — override_log เก็บชื่อแพทย์จริง ไม่อยู่ในขอบเขต mask
**แก้:** เพิ่ม `("override_log","surgeon_name")` เข้า SURG group ใน `mask_unmasked_staff`
→ กดปุ่ม mask แล้วชื่อแพทย์ใน override_log กลายเป็น `SURG_xxx` พร้อม cases/prediction_log

## M-12 — test_minimal.py โชว์รหัสผ่าน plaintext + ชื่อแพทย์จริง hardcode
**แก้:**
- Test 4: เลิกพิมพ์ `repr(app_password)` → แสดงแค่ "✅ ตั้งค่าแล้ว / ❌ ยังไม่ตั้ง"
- ชื่อแพทย์จริงในโค้ดทดสอบ → `SURG_001`
- เพิ่ม **Test 5**: smoke test ของโมเดลที่ deploy จริง (`or_time_model.predict_detail`) — เดิมทดสอบแต่ predictor v2 (legacy)

## M-13 — board_state สะสมบน cloud ตลอดกาล (ขัดหลัก data retention)
**แก้:** `save_board_state` ลบคีย์ `board_state_*` ที่เก่ากว่า 7 วันทุกครั้ง (parameterized)
→ ไม่เก็บข้อมูลผู้ป่วย (แม้ mask) ถาวรบน cloud

## ไฟล์ที่แก้ (compile ผ่านทั้งหมด)
`tracking_board.py` · `main_or_admin.py` · `main_or_tracking.py` · `main_or_db.py` · `test_minimal.py`

## ก่อน commit (บน Windows)
```powershell
python -m py_compile tracking_board.py main_or_admin.py main_or_tracking.py main_or_db.py test_minimal.py
git add tracking_board.py main_or_admin.py main_or_tracking.py main_or_db.py test_minimal.py docs/GROUP_B_SECURITY_2026-06-11.md
git commit -m "fix(security): กลุ่ม B — M-01 XSS escape + M-06 mask override_log + M-12 test secrets/SURG + M-13 board_state retention 7 วัน"
```
