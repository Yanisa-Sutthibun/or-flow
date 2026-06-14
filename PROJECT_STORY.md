# Minor OR Dashboard — เรื่องเล่าทั้งโปรเจกต์

> เขียนโดย คล็อดคุง สำหรับมุ้กก · พฤษภาคม 2026

---

## 🎯 จุดเริ่มต้น: ปัญหาที่เห็นมาตลอด

มุ้กกเป็นพยาบาลห้องผ่าตัด ทำงานในห้อง minor OR ทุกวัน เลยเห็นปัญหา 3 อย่างซ้ำๆ:

1. **เคสล่าช้า บอกไม่ได้ว่ากี่โมงจะเสร็จ** — ทีมรอเก้อ คนไข้นอกห้องเครียด
2. **ห้องว่าง vs ห้องแน่น พร้อมๆ กัน** — ไม่มีใครเห็นภาพรวม จัดคิวไม่ได้
3. **ผู้บริหารตัดสินใจโดยไม่มีตัวเลข** — เคสนัดหมายเท่าไหร่ เคส walk-in เท่าไหร่ ห้องไหนใช้คุ้ม ไม่รู้

มุ้กกกำลังเรียน Master's ด้าน Nursing Administration อยู่ → เลยคิดทำ **dashboard ที่ใช้ Machine Learning ทำนายเวลาผ่าตัด** เป็นทั้ง thesis และเครื่องมือใช้งานจริง

---

## 🏗️ องค์ประกอบใหญ่ 7 ส่วน (เหมือนชั้นเค้ก)

```
┌────────────────────────────────────────────┐
│ 7. Deploy บน Streamlit Cloud + Password    │ ← ขั้นสุดท้าย
├────────────────────────────────────────────┤
│ 6. UI สวยๆ enterprise medical theme        │
├────────────────────────────────────────────┤
│ 5. PDPA: mask ชื่อ + ลบ PII ก่อน cloud    │ ← กฎหมายไทย
├────────────────────────────────────────────┤
│ 4. หน้า Admin — ผู้บริหารดูสถิติย้อนหลัง │
├────────────────────────────────────────────┤
│ 3. หน้า Tracking — พยาบาลใช้งาน realtime │
├────────────────────────────────────────────┤
│ 2. ML Model — ทำนายว่าผ่าตัดจะกี่นาที       │ ← หัวใจของ thesis
├────────────────────────────────────────────┤
│ 1. ฐานข้อมูล — รวมข้อมูล 3 แหล่ง          │ ← ฐานราก
└────────────────────────────────────────────┘
```

---

## 1️⃣ ฐานข้อมูล — รวบรวมจาก 3 แหล่ง

โรงพยาบาลมีไฟล์ 3 ตัวที่ออกมาคนละช่องทาง:

| ไฟล์ | มาจาก | บอกอะไร |
|------|--------|---------|
| **Scheduling.csv** | HIS booking | เคสนัดหมายล่วงหน้า + ICD + แพทย์ + division |
| **Intraop.csv** | record ระหว่างผ่าตัด | เวลาเข้าห้อง / ออกห้อง + พยาบาลที่ scrub/circ |
| **Cost.xlsx** | การเงิน | เคส walk-in ที่ไม่ได้อยู่ใน scheduling |

**ปัญหา**: 3 ไฟล์นี้ไม่ตรงกันตรงๆ — ต้อง match ด้วย `HN + วันที่ผ่าตัด`

**Logic เคสนัดหมาย vs Walk-in**:
- ถ้าวันจองล่วงหน้า < วันผ่าตัด → "เคสนัดหมาย"
- ถ้าวันจอง = วันผ่าตัด หรือไม่มีวันจอง → "Walk-in"

ไฟล์หลัก: `import_historical.py` รวมทั้งหมดเข้า `cases` table

---

## 2️⃣ Machine Learning — หัวใจของ thesis

### โมเดลที่เลือก: **Random Forest**
ไม่ใช่เพราะแม่นที่สุด — แต่เพราะ:
- อธิบายได้ ("ทำไมทำนาย 45 นาที?" — บอกได้ว่า feature ไหนสำคัญ)
- ไม่ต้อง GPU แรงๆ
- เหมาะกับข้อมูลผสม (categorical + numerical)
- robust ต่อ outlier (พอใจ surgeon ใหม่/หัตถการแปลก)

### Features ที่ใช้ทำนาย
1. **procedure_name** — ชื่อหัตถการ (normalize fuzzy แล้ว: "I&D" = "I and D" = "Incision and drainage")
2. **division_code** — สาขา (75 = ผิวหนัง, 78 = ทันตกรรม...)
3. **case_category** — นัดหมาย/walk-in/emergency
4. **patient_type** — OPD/IPD/นอกเวลา
5. **start_hour** — เริ่มกี่โมง (เช้า/บ่าย/ค่ำ)

### Pipeline
```
ข้อมูลย้อนหลัง 12 เดือน
    ↓
clean + fuzzy normalize procedure name
    ↓
train Random Forest (sklearn)
    ↓
save .pkl model
    ↓
ตอนใช้งาน: predict_surgical_time() → คืนค่านาที + confidence
```

ไฟล์หลัก: `train_minor_or_v3.py` (train), `minor_or_core.py` (predict)

**Fallback ที่สำคัญ**: ถ้า model ไม่มั่นใจ (เคสใหม่ ไม่เคยเจอ) → ใช้ค่าเฉลี่ยของหัตถการเดียวกันใน DB แทน — `predict_from_local_history()` ใน `minor_or_db.py`

---

## 3️⃣ หน้า Tracking — พยาบาลใช้ทุกวัน

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│  ห้อง 1    │  ห้อง 2    │  ห้อง 3    │  ห้อง 4    │
│ 🟢 ว่าง    │ 🔵 ผ่าตัด  │ 🟢 ว่าง    │ 🟡 รอ      │
│            │ [▓▓▓░░] 60% │            │             │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

### Features สำคัญ
- **AI progress bar** แสดง % เวลาที่ผ่านไป + คาดว่าจะเสร็จกี่โมง
- **User override** — ถ้าหมอบอกเคสนี้นาน → กดแก้เวลาทำนายได้
- **Upcoming queue** — เคสต่อไป 3 เคสล่าสุด
- **Hourly throughput** — กราฟ throughput รายชั่วโมง
- **Auto-refresh ทุก 1 นาที** (หยุดอัตโนมัติตอน demo paused)

### Demo Mode 🎬
มุ้กกอยากโชว์ผู้บริหารแต่ไม่อยากให้แตะ data จริง → สร้าง Demo Mode ที่:
- เก็บข้อมูลใน `session_state` ไม่เขียน DB
- มี 8 เคสสมมุติ (ชื่อเต็มเหมือนคนไข้จริง)
- ปุ่ม disabled (เห็นว่ามีปุ่มอะไร แต่กดไม่ได้)
- KPI summary 3 กลุ่ม: เคสรวม / ประเภท / เวลา

ไฟล์: `minor_or_tracking.py`

---

## 4️⃣ หน้า Admin — ผู้บริหารดูแล้วได้ insight

### Layout
```
┌─────── KPI Highlights (4 cards) ───────┐
│ เคสทั้งหมด · Peak day · Util Rate · สาขาเยอะสุด │
├────────────────────────────────────────┤
│ 📋 สรุปยอดสะสม (4 cards + breakdown)   │
├────────────────────────────────────────┤
│ 🚨 ระดับเร่งด่วน — Elective/Urgent/Emer │
├────────────────────────────────────────┤
│ 🏆 อันดับยอดนิยม (procedure + surgeon)  │
├────────────────────────────────────────┤
│ ⏱️  เวลาผ่าตัด (Turnover + Stage)       │
├────────────────────────────────────────┤
│ 📈 แนวโน้มเวลา (DoW + Workload heatmap) │
├────────────────────────────────────────┤
│ 🌙 เคสนอกเวลา (Mon-Fri analysis)        │
├────────────────────────────────────────┤
│ 👥 Progress รายบุคคล (PIN-protected)    │
├────────────────────────────────────────┤
│ 🔧 Maintenance (upload + wipe)          │
└────────────────────────────────────────┘
```

### Charts ที่ใช้
- **Line chart** — แนวโน้มรายวัน (มี 7-day rolling average + peak marker)
- **Bar chart** — DoW comparison, Top procedures
- **Heatmap** — Workload by hour × weekday
- **Horizontal bar** — Top surgeons (ตัดยศ "นพ./พญ." ออกอัตโนมัติ)

### Sidebar TOC แบบ Notion
- Sticky ขวามือ, scroll ตามได้
- collapse/expand ได้
- ปุ่ม "กลับด้านบน"

ไฟล์: `minor_or_admin.py` (191KB — ใหญ่สุดในโปรเจกต์!)

---

## 5️⃣ PDPA Compliance — ห้ามให้ข้อมูลคนไข้รั่ว

> "เอาทางที่ปลอดภัยที่สุด คือ hn Pt's name ห้ามเอาขึ้น supabase
>  ชื่อบุคลากรทางการแพทย์ต้อง masking เพราะ จำเป็นต้องใช้ในทางสถิติ"
> — Mukky

### ระบบ Anonymization 2 ชั้น

**ชั้นที่ 1: ก่อน upload cloud**
- HN, ชื่อคนไข้ → **ลบทิ้ง** ก่อน upload
- ชื่อแพทย์ → mask เป็น `SURG_001`, `SURG_002`...
- ชื่อพยาบาล → `SCRUB_001`, `CIRC_001`...
- script: `supabase/anonymize_for_cloud.py`

**ชั้นที่ 2: เวลาแสดงผล UI**
- Streamlit รัน local + อ่านจาก cloud (masked)
- ตอน return data → **un-mask กลับเป็นชื่อจริง** ด้วย `staff_mapping.csv`
- `staff_mapping.csv` อยู่ในเครื่อง local เท่านั้น (gitignore + ห้าม commit)
- ไฟล์: `staff_unmask.py`

**ผลลัพธ์**:
- Cloud มีแค่ masked data → safe ตาม PDPA
- พยาบาลที่ใช้งานเห็นชื่อจริง (เพราะมี mapping file)
- Streamlit Cloud (public deploy) เห็น masked code → ไม่ leak

---

## 6️⃣ UI Polish — Enterprise Medical Theme

ก่อนปรับ: หน้าตา default Streamlit (เทาๆ ดูเหมือน demo)
หลังปรับ: navy ink + brand cyan, font Inter + IBM Plex Sans Thai

### ไฟล์ใหม่: `ui_theme.py` (CSS กลาง)
- inject เข้าทั้ง 3 หน้า (tracking, admin, settings)
- override Streamlit components ทุกอย่าง: ปุ่ม, metric, tab, input, expander
- เพิ่ม custom classes: `.kpi-card`, `.case-card`, `.cw-tip` (hover tooltip)

### บั๊กที่เจอตอนทำ theme
**"CSS leak as text on login page"** — Streamlit markdown parser ทำลาย `<style>` block ที่มี blank lines ในกลาง → fix โดย concat เป็น **single continuous string** (zero newlines)

**"Theme หายหลัง rerun"** — มี session_state guard กันการ re-inject → ลบทิ้ง เพราะ Streamlit rebuild DOM ทุก rerun

---

## 7️⃣ Deploy — ขึ้น Streamlit Community Cloud

### Migration: SQLite → Supabase PostgreSQL
ทำไม? เพราะ:
- SQLite อยู่ที่ disk → multi-user concurrent write ไม่ได้
- Streamlit Cloud restart ทุกครั้ง → SQLite หาย
- Supabase free tier มี PostgreSQL + auth + storage

### ปัญหา SQLite → PostgreSQL ที่ต้องแก้
- `strftime('%w', date)` → `EXTRACT(DOW FROM ...)` หรือ `TO_CHAR()`
- `DATE('now')` → `to_char(CURRENT_DATE, 'YYYY-MM-DD')` (เพราะ op_date เก็บเป็น TEXT)
- `?` placeholder → `%s` (psycopg2)
- `%` literal ใน string → escape เป็น `%%`
- `AUTOINCREMENT` → `SERIAL`

ไฟล์ที่จัดการ: `db_connection.py` (มี SQL converter อัตโนมัติ)

### Security gate
- Streamlit password gate ก่อนเข้าหน้าใดๆ
- API key ของ Supabase อยู่ใน `.streamlit/secrets.toml` (gitignore)

---

## 🛠️ Stack ทั้งหมด

| Layer | เครื่องมือ |
|-------|-----------|
| Frontend | Streamlit |
| Charts | Plotly |
| ML | scikit-learn (Random Forest) |
| Data | Pandas + NumPy |
| DB | SQLite (local) + Supabase PostgreSQL (cloud) |
| Auth | Streamlit password gate |
| Deploy | Streamlit Community Cloud |
| Version Control | Git + GitHub |
| Theme | Custom CSS (Inter + IBM Plex Sans Thai) |

---

## 📈 ตัวเลขโปรเจกต์

- **โค้ดทั้งหมด**: ~600 KB Python (10 ไฟล์หลัก)
- **commits**: 100+
- **iterations กับ Claude**: นับไม่ถ้วน 😄
- **เวลาที่ใช้**: ~4 เดือน (ต.ค. 2025 - พ.ค. 2026)
- **ข้อมูลที่ train**: 1,000+ เคสย้อนหลัง 12 เดือน
- **Tasks ที่ปิดไป**: 146 tasks
- **บรรทัดโค้ดที่ลบเพราะ refactor**: 2,000+ (cleanup ล่าสุดเอง)

---

## 🎓 บทเรียนที่ได้

1. **เริ่มจากปัญหาจริง ไม่ใช่ technology** — มุ้กกเป็น user เองทำให้ feedback แม่นมาก
2. **iterate เล็กๆ ไม่ใช่ big bang** — ทุก feature ทดสอบกับ data จริงก่อน ค่อยขยาย
3. **UI ที่ใช้งานได้ > UI ที่สวย** (แต่สวยด้วยก็ดี)
4. **PDPA ไม่ใช่ทางเลือก** — ออกแบบตั้งแต่แรก เปลี่ยนทีหลังลำบาก
5. **commit บ่อยๆ** — recover ง่าย (ใช้บ่อยมากในโปรเจกต์นี้)
6. **Master degree thesis ไม่จำเป็นต้องเป็น paper** — ของจริงที่ใช้งานได้ก็เป็น thesis ที่ดี

---

## 🏁 สถานะปัจจุบัน (พฤษภาคม 2026)

✅ **ทำเสร็จแล้ว 95%**
- Data pipeline + ML model
- Tracking page + Demo mode
- Admin page + Analytics
- PDPA anonymization
- Enterprise UI theme
- Supabase migration
- Streamlit Cloud deploy + password

⏳ **เหลือ 5%**
- Test ทุก feature อย่างจริงจัง (Phase 5)
- รัน `anonymize_for_cloud.py` re-upload ข้อมูลล่าสุด
- Verify Supabase Dashboard ไม่มี PII

---

## 💬 ข้อความถึงมุ้กก

โปรเจกต์นี้เกิดเพราะมุ้กกมี 3 อย่างที่หายาก:
1. **เห็นปัญหาชัด** (เพราะอยู่หน้างาน)
2. **มี domain expertise** (พยาบาล OR ตัวจริง)
3. **กล้าทำของจริง** (ไม่หยุดที่ paper)

ส่วน claude-kun แค่เป็นเครื่องมือช่วยพิมพ์โค้ดให้เร็วขึ้น ❤️
ของจริงทั้งหมดมาจากมุ้กกที่เห็นปัญหาแล้วลงมือแก้

defense thesis ขอให้ราบรื่นครับ — ถ้าอาจารย์ถามอะไร ตอบจากใจได้เลย เพราะทุกบรรทัดของโปรเจกต์นี้เกิดจาก insight ของมุ้กกเอง

— คล็อดคุง · พฤษภาคม 2026
