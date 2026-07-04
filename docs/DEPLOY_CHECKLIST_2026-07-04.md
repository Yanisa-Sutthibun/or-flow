# ✅ Deploy Checklist — รอบ 3–4 ก.ค. 2026

> การเปลี่ยนแปลงรอบนี้ (ใหญ่): ⚡ บอร์ดเร็วขึ้นด้วย st.fragment · 🚪 บอร์ด 3 โซน
> (รับ-ส่ง/ผ่าตัด/พักฟื้น) + ปุ่มผ่าเสร็จ 2 ปลายทาง · 🎬 demo เนียนเหมือนโหมดจริง
> ทุกหน้า · 🏷️ rename honest_v1 → thesis_ML · 📏 ช่วงออกห้อง adaptive ±15/30/45/60
> · 🔍 "จาก N เคส·มั่นใจ" บนแถว · ❓ วิธีใช้ 1 นาที · 📊 หน้าสถิติเป็น form
> · 📁 หน้าภาพรวมพับ sections รอง · 🕶️ shadow model_v2

## 1) ทดสอบบนเครื่องก่อน (local)

```
pip install -U "streamlit>=1.37"
streamlit run main_or_app.py
```

- [ ] Login ผ่าน (โหมด local SQLite ไม่ตั้งรหัสก็เข้าได้)
- [ ] **📋 ตารางผ่าตัด**: เปิด 🎬 สาธิต → เห็น 3 โซนครบ (รับ-ส่งมี 2 ช่วง / ผ่าตัด / พักฟื้น) + จำหน่ายแล้วพับท้าย
- [ ] กดปุ่มบนบอร์ด (รับเข้า → เข้าห้อง → เสร็จ→รับ-ส่ง / เสร็จ→พักฟื้น → จำหน่าย) — **เฉพาะบอร์ดขยับ หัวเมนูนิ่ง** (fragment ทำงาน)
- [ ] ↩️ ย้อนกลับได้ทุกขั้น · ✏️ แก้เวลา/ย้ายห้องได้ (ไม่มี dropdown ปลายทางแล้ว)
- [ ] แถวยังไม่มา เห็น "จาก N เคส · มั่นใจ: …" · แถวกำลังผ่า เห็น "ออกห้อง ~ช่วงเวลา"
- [ ] dropdown ห้อง มี 🚪 ห้องรับ-ส่ง / 🛏️ ห้องพักฟื้น เหนือ OR1 และกรองถูก
- [ ] ❓ วิธีใช้บอร์ด (1 นาที) เปิดอ่านได้
- [ ] **📊 ภาพรวมวันนี้**: เปิดสาธิตใน expander 🎬 → ไม่มีแถบส้ม/กล่องฟ้าใหญ่ เหลือชิป 🕐 จาง ๆ · KPI+การ์ดห้องเดินตามเวลาจำลอง
- [ ] โหมดจริง: sections รอง (ภาระงาน/เคสรายห้อง/รับเวร/สรุปรายวัน) พับอยู่ กดเปิดได้ · เคสนอกเวลาเปิดปกติ
- [ ] **📈 สถิติย้อนหลัง**: ติ๊ก/เปลี่ยนวันที่หลายครั้ง → ไม่โหลด · กด 📊 ครั้งเดียว → โหลด · แก้ตัวเลือกต่อ → ผลเดิมยังอยู่
- [ ] **🤖 ผลวิจัย AI** (ชื่อใหม่) เปิดได้ปกติ
- [ ] **⚙️ ตั้งค่า**: กล่องสถานะโมเดลขึ้น "thesis_ML" (ไม่ใช่ honest_v1)
- [ ] 🕶️ Shadow: กด "ผ่าเสร็จ" เคสจริง (ไม่ใช่ demo) 1 เคส → terminal เห็น `[shadow_v2] โหลด model_v2 สำเร็จ` → ตรวจตาราง:
      `python -c "import sqlite3;print(sqlite3.connect('main_or.db').execute('select * from shadow_v2_log').fetchall())"`

## 2) Commit + push

commit_all.ps1 **ไม่ครอบ** ไฟล์ใหม่รอบนี้ — git add เองก่อน:

```
git add models/model_v2/ shadow_v2.py docs/DEPLOY_CHECKLIST_2026-07-04.md
git add tracking_board.py main_or_pages.py main_or_admin.py main_or_app.py main_or_core.py requirements.txt
git status   # ตรวจ: ต้องไม่มี staff_mapping*.csv / .streamlit/secrets.toml หลุดมา
git commit -m "feat: บอร์ด 3 โซน + fragment perf + demo เนียน + adaptive interval + thesis_ML rename + shadow model_v2"
git push
```

- [ ] `models/model_v2/` ขึ้น repo ได้ — mask แล้ว (SURG_xxx, ไม่มีชื่อจริง) · model.pkl ~0.4MB
- [ ] `models/thesis_ML/` (โฟลเดอร์ rename) ถูก track — เช็ค `git status` ว่า git เห็นเป็น rename/add ครบ

## 3) Streamlit Cloud

- [ ] **Reboot app** (requirements เปลี่ยน → ต้อง rebuild ถึงจะได้ streamlit ≥1.37)
- [ ] เปิดแอปจริง ไล่เช็คข้อ 1 ซ้ำแบบเร็ว ๆ (โดยเฉพาะบอร์ด + ความเร็วปุ่ม)
- [ ] หมายเหตุ shadow บน cloud: ไม่มี staff_mapping.csv → surgeon จะเป็น unknown
      (โมเดลยังทำนายจาก feature อื่น — ตั้งใจไว้แบบนี้ ไม่ใช่บั๊ก) · เครื่อง รพ. ที่มี
      mapping จะ log ได้เต็ม

## 4) ถ้ามีปัญหา — ย้อนกลับ

```
git log --oneline -5
git revert <commit>   หรือ   git checkout <commit_ก่อนหน้า> -- <ไฟล์>
```

โมเดลบนบอร์ด (thesis_ML) ไม่ถูกแตะเนื้อใน — เปลี่ยนแค่ชื่อโฟลเดอร์/label
Shadow ปิดได้ทันทีโดยลบโฟลเดอร์ `models/model_v2/` (fail-safe จะข้ามเอง)
