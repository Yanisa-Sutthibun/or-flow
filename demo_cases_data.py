# -*- coding: utf-8 -*-
"""
demo_cases_data.py — 🎬 ชุดเคสโหมดสาธิต (Main OR — mask แล้ว 100%)
════════════════════════════════════════════════════════════════════
ที่มา: ตารางผ่าตัดจริง Main OR 5 วัน (13-17 ก.ค. 2569) + ไฟล์ preop วิสัญญี
นำมา mix แบบ "ห้องละหนึ่งวัน" — แต่ละห้องดึงจากวันเดียวกันทั้งห้อง
เพื่อคง pattern แพทย์ประจำวันของ OR ศัลยกรรม (มุคกี้สั่ง 28 ก.ค. 2026)

การ mask (ไฟล์นี้อยู่ใน git — ห้ามมี PII):
  · แพทย์  → ชื่อจำลอง "{ชื่อ} {พยัญชนะ}" วนจาก 6 ชื่อ (ปิติ/มานะ/ชูใจ/มานี/วีระ/ดวงแก้ว)
    + พยัญชนะ ก ข ค ... ตามเลขแพทย์เดิม (คนเดียวกันชื่อเดิมเสมอ ข้ามวัน/ข้ามห้อง)
    + surgeon_code = SURG_xxx จริง ไว้ส่งเข้าโมเดล → AI ทำนายแม่นเท่าของจริง
  · ผู้ป่วย → ชื่อจำลอง "{ชื่อ} {นามสกุลสมมติ}" วนจากชื่อชาย/หญิง/กลาง 12 ชื่อ ตามเพศคำนำหน้าเดิม
    · เปลี่ยนนามสกุลจากตัวเลขเป็นนามสกุลไทยสมมติ 30 ส.ค. 2026 ตามคำสั่งมุกกี้ เพื่อให้บอร์ดย่อเป็นอักษรเดียวเหมือนระบบจริง
    · HN ปลอม 99000xxx (เปลี่ยนชุดชื่อ 9 ส.ค. 2026 ตามคำสั่งมุกกี้)
  · หัตถการ/วินิจฉัย/อายุ/ASA/BMI คงจริง (ไม่ระบุตัวตน) — ให้ AI มีของโชว์
สนามเวลา/สถานะ ไม่อยู่ในไฟล์นี้ — _or_board_demo() เติมสด ๆ ตอนเปิดสาธิต
"""

DEMO_POOL = [
    {'room': 97, 'day': 'จันทร์', 'ororder': 1, 'sched_h': 9, 'sched_m': 0, 'name': 'ร.ต.อ. สมพร กิจเจริญ', 'hn': '99000001', 'age': 72, 'procedure': 'TEMPORARY TRACHEOSTOMY', 'diagnosis': 'Malignant neoplasm of hypopharynx, unspecified', 'division': '3', 'ward': 'ฉก.6 (ตา หู คอ จมูก)', 'optype': 'Elective', 'surgeon': 'โกมินทร์ กุมาร', 'surgeon_code': 'SURG_944', 'ASA': '4', 'BMI': 13.8, 'planicu': 'ไม่มี', 'blood': 'ไม่มี'},
    {'room': 97, 'day': 'จันทร์', 'ororder': 2, 'sched_h': 7, 'sched_m': 0, 'name': 'นาง สมหญิง ขจรกุล', 'hn': '99000002', 'age': 60, 'procedure': 'LC', 'diagnosis': 'symptomatic gall stone', 'division': '1', 'ward': 'ฉก.8', 'optype': 'Elective', 'surgeon': 'มานะ รักเผ่าไทย', 'surgeon_code': 'SURG_066', 'ASA': '2', 'BMI': 25.1, 'planicu': 'ไม่มี', 'blood': 'ไม่มี'},
    {'room': 92, 'day': 'อังคาร', 'ororder': 1, 'sched_h': 9, 'sched_m': 0, 'name': 'นาย สมชาย คงเจริญ', 'hn': '99000003', 'age': 40, 'procedure': 'LT. DJ STENT EXCHANGING', 'diagnosis': 'Lt. nephrocalcinosis', 'division': '5', 'ward': 'ฉก.12', 'optype': 'Elective', 'surgeon': 'ชูใจ เลิศล้ำ', 'surgeon_code': 'SURG_084', 'ASA': '1', 'BMI': 20.2, 'planicu': 'ไม่มี', 'blood': 'ไม่มี'},
    {'room': 92, 'day': 'อังคาร', 'ororder': 2, 'sched_h': 9, 'sched_m': 0, 'name': 'ด.ต. สมศักดิ์ งามพร้อม', 'hn': '99000004', 'age': 74, 'procedure': 'REZUM', 'diagnosis': 'BPH', 'division': '5', 'ward': 'nan', 'optype': 'Elective', 'surgeon': 'ชูใจ เลิศล้ำ', 'surgeon_code': 'SURG_084', 'ASA': '3', 'BMI': 29.0, 'planicu': 'ไม่มี', 'blood': 'ไม่มี'},
    {'room': 92, 'day': 'อังคาร', 'ororder': 3, 'sched_h': 9, 'sched_m': 0, 'name': 'น.ส. สมศรี จันทร์ทอง', 'hn': '99000005', 'age': 85, 'procedure': 'FLEX. CYSTO', 'diagnosis': 'CA bladder', 'division': '5', 'ward': 'nan', 'optype': 'Elective', 'surgeon': 'ชูใจ เลิศล้ำ', 'surgeon_code': 'SURG_084', 'BMI': 21.3},
    {'room': 91, 'day': 'พุธ', 'ororder': 1, 'sched_h': 7, 'sched_m': 0, 'name': 'พ.ต.ท. สมหมาย ฉิมพลี', 'hn': '99000006', 'age': 41, 'procedure': 'OPEN APPENDECTOMY', 'diagnosis': 'Ruptured appendicitis', 'division': '1', 'ward': 'nan', 'optype': 'Emergency', 'surgeon': 'มานี รักเผ่าไทย', 'surgeon_code': 'SURG_080', 'ASA': '2E', 'BMI': 24.5, 'planicu': 'ไม่มี', 'blood': 'ไม่มี'},
    {'room': 91, 'day': 'พุธ', 'ororder': 2, 'sched_h': 15, 'sched_m': 30, 'name': 'นาย สมคิด ชูเกียรติ', 'hn': '99000007', 'age': 46, 'procedure': 'ANEURYSMECTOMY OR LIGATE AVF', 'diagnosis': 'Giant AVF Rt arm', 'division': '7', 'ward': 'nan', 'optype': 'Elective', 'surgeon': 'วีระ ประสงค์สุข', 'surgeon_code': 'SURG_003', 'ASA': '2', 'BMI': 24.6},
    {'room': 91, 'day': 'พุธ', 'ororder': 3, 'sched_h': 15, 'sched_m': 30, 'name': 'ร.ต.ท.หญิง สมใจ ซื่อสัตย์', 'hn': '99000008', 'age': 71, 'procedure': 'PROXIMALIZED AVF RT WRIST', 'diagnosis': 'AVF stenosis', 'division': '7', 'ward': 'nan', 'optype': 'Elective', 'surgeon': 'วีระ ประสงค์สุข', 'surgeon_code': 'SURG_003', 'BMI': 24.2},
    {'room': 93, 'day': 'พฤหัสบดี', 'ororder': 1, 'sched_h': 9, 'sched_m': 0, 'name': 'นาง สมปอง ญาณโสภณ', 'hn': '99000009', 'age': 24, 'procedure': 'LC', 'diagnosis': 'SGS', 'division': '9', 'ward': 'ฉก.13', 'optype': 'Elective', 'surgeon': 'ฟ้าลั่น มะม่วง', 'surgeon_code': 'SURG_087', 'ASA': '2', 'BMI': 33.0, 'planicu': 'ไม่มี'},
    {'room': 93, 'day': 'พฤหัสบดี', 'ororder': 2, 'sched_h': 7, 'sched_m': 0, 'name': 'ส.ต.ต. สมมาตร ดำรงชัย', 'hn': '99000010', 'age': 69, 'procedure': 'DEBRIDEMENT LEFT FOOT', 'diagnosis': 'NF left foot', 'division': '1', 'ward': 'คศ.2', 'optype': 'Elective', 'surgeon': 'ปิติ พิทักษ์ถิ่น', 'surgeon_code': 'SURG_085', 'ASA': '3', 'BMI': 23.6, 'planicu': 'ไม่มี', 'blood': 'ไม่มี'},
    {'room': 93, 'day': 'พฤหัสบดี', 'ororder': 3, 'sched_h': 7, 'sched_m': 0, 'name': 'นาย สมดุล ตั้งมั่น', 'hn': '99000011', 'age': 49, 'procedure': 'LC', 'diagnosis': 'symptomatic GB polyp 6-9 mm', 'division': '9', 'ward': 'คศ.3/1', 'optype': 'Elective', 'surgeon': 'สุดสาคร เกาะแก้ว', 'surgeon_code': 'SURG_069', 'ASA': '2', 'BMI': 23.3, 'planicu': 'ไม่มี', 'blood': 'ไม่มี'},
    {'room': 94, 'day': 'พฤหัสบดี', 'ororder': 1, 'sched_h': 7, 'sched_m': 0, 'name': 'พ.ต.อ. สมภพ ถาวรกุล', 'hn': '99000012', 'age': 76, 'procedure': 'TCC LT IJV , CENTROS', 'diagnosis': 'ESRD', 'division': '7', 'ward': 'nan', 'optype': 'Elective', 'surgeon': 'วีระ ประสงค์สุข', 'surgeon_code': 'SURG_003', 'BMI': 20.8},
    {'room': 94, 'day': 'พฤหัสบดี', 'ororder': 2, 'sched_h': 7, 'sched_m': 0, 'name': 'น.ส. สมหญิง ทองดี', 'hn': '99000013', 'age': 50, 'procedure': 'TCC', 'diagnosis': 'ESRD', 'division': '7', 'ward': 'มภร.10/2', 'optype': 'Elective', 'surgeon': 'วีระ ประสงค์สุข', 'surgeon_code': 'SURG_003', 'ASA': '3', 'planicu': 'ไม่มี', 'blood': 'มี'},
    {'room': 94, 'day': 'พฤหัสบดี', 'ororder': 3, 'sched_h': 7, 'sched_m': 0, 'name': 'ด.ต.หญิง สมศรี ธนกิจ', 'hn': '99000014', 'age': 52, 'procedure': 'AVF RT CUBITAL', 'diagnosis': 'ESRD', 'division': '7', 'ward': 'nan', 'optype': 'Elective', 'surgeon': 'วีระ ประสงค์สุข', 'surgeon_code': 'SURG_003', 'BMI': 23.9},
    {'room': 95, 'day': 'ศุกร์', 'ororder': 1, 'sched_h': 9, 'sched_m': 0, 'name': 'นาย สมพร นพคุณ', 'hn': '99000015', 'age': 39, 'procedure': 'L4-S1 LAMINECTOMY WITH PDS FIXATION', 'diagnosis': 'L4-S1 spondylosis', 'division': '2', 'ward': 'ฉก.13', 'optype': 'Elective', 'surgeon': 'พิมพิลาลัย วันทอง', 'surgeon_code': 'SURG_919', 'ASA': '2', 'BMI': 30.0, 'planicu': 'ไม่มี', 'blood': 'มี'},
    # 🎬 9 ส.ค. 2026 (มุคกี้สั่ง): ชื่อตั้งใจให้ "ตรงเป๊ะ" กับเคสห้อง 92#1 (นาย สมชาย 3)
    #    เพื่อสาธิตป้าย 👥 ชื่อซ้ำ บนบอร์ด — OR3 (กำลังผ่า) ชนกับ OR6 (ยังไม่มา)
    {'room': 95, 'day': 'ศุกร์', 'ororder': 2, 'sched_h': 13, 'sched_m': 0, 'name': 'นาย สมชาย คงเจริญ', 'hn': '99000016', 'age': 36, 'procedure': 'RT CRANIOTOMY C TUMOR REMOVAL UNDER NAVUGATOR', 'diagnosis': 'RT parasagital glioma', 'division': '2', 'ward': 'ICU NEURO', 'optype': 'Elective', 'surgeon': 'พิมพิลาลัย วันทอง', 'surgeon_code': 'SURG_919', 'ASA': '2', 'BMI': 30.0, 'planicu': 'ไม่มี', 'blood': 'มี'},
    {'room': 95, 'day': 'ศุกร์', 'ororder': 3, 'sched_h': 17, 'sched_m': 0, 'name': 'นาง สมใจ บุญมี', 'hn': '99000017', 'age': 61, 'procedure': 'LEFT FRONTAL VP SHUNT', 'diagnosis': 'Hydrorcephalus', 'division': '2', 'ward': 'ICU NEURO', 'optype': 'Emergency', 'surgeon': 'ก้านกล้วย คชสาร', 'surgeon_code': 'SURG_924', 'ASA': '3E', 'BMI': 35.4, 'planicu': 'มี', 'blood': 'ไม่มี'},
    {'room': 96, 'day': 'ศุกร์', 'ororder': 1, 'sched_h': 13, 'sched_m': 0, 'name': 'จ.ส.อ. สมศักดิ์ ปรีชากุล', 'hn': '99000018', 'age': 68, 'procedure': 'OSTEOTOM, EXCISION', 'diagnosis': 'Forehead osteoma, mass at left shoulder, mass at buttock', 'division': '4', 'ward': 'nan', 'optype': 'Elective', 'surgeon': 'เจ้าหญิง พิกุลทอง', 'surgeon_code': 'SURG_011', 'BMI': 25.4},
    {'room': 96, 'day': 'ศุกร์', 'ororder': 2, 'sched_h': 13, 'sched_m': 0, 'name': 'นาย สมหมาย ผลบุญ', 'hn': '99000019', 'age': 72, 'procedure': 'EXCISION', 'diagnosis': 'mass at medail side of eyelid', 'division': '4', 'ward': 'nan', 'optype': 'Elective', 'surgeon': 'เจ้าหญิง พิกุลทอง', 'surgeon_code': 'SURG_011', 'BMI': 20.0},
    {'room': 96, 'day': 'ศุกร์', 'ororder': 3, 'sched_h': 13, 'sched_m': 0, 'name': 'พ.ต.ต.หญิง สมปอง พงษ์ไทย', 'hn': '99000020', 'age': 37, 'procedure': 'EXCISION', 'diagnosis': 'mass at neck', 'division': '4', 'ward': 'คศ.3/1', 'optype': 'Elective', 'surgeon': 'เจ้าหญิง พิกุลทอง', 'surgeon_code': 'SURG_011', 'ASA': '2', 'BMI': 31.2, 'planicu': 'ไม่มี', 'blood': 'ไม่มี'},
]
