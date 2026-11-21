# -*- coding: utf-8 -*-
"""
procedure_master.py : 📚 พจนานุกรมหัตถการมาตรฐานของ OR Flow (ฉบับร่าง รอมุกกี้ตรวจ)
════════════════════════════════════════════════════════════════════════════
สร้าง 21 พ.ย. 2026 (มุกกี้สั่ง: "ต้องแก้ไขให้ถูกต้องก่อนใช้งานจริง ... operation/procedure
มันต้องเก็บเป็นสถิติ ถ้าผิดสถิติอาจเพี้ยน")

ปัญหาเดิม : ชื่อหัตถการใน HIS เป็นข้อความพิมพ์อิสระ (ปี 64-69 มี 8,266 แบบ จาก 23,394 เคส)
  · ชั้นทำนายจับคู่ทั้งประโยคแบบ fuzzy จึงจับหัตถการพ่วงเป็นตัวเล็ก และคำกว้าง (EXCISION) กลืนหัตถการเฉพาะ
  · หน้าสถิติใช้กติกาอีกชุด (_normalize_procedure_name) ที่เขียนไว้สำหรับห้องผ่าตัดเล็ก
  → สองที่นับไม่ตรงกัน และไม่มีที่ไหนตรวจย้อนได้ว่าคำไหนถูกจับเป็นอะไร

ลำดับการคิด (มุกกี้สั่ง 21 พ.ย. 2026) : สาขา >> แพทย์ >> หัตถการ
  คำเดียวกันคนละสาขาเป็นคนละหัตถการ (LOBECTOMY ของหู คอ จมูก = ไทรอยด์ · RFA ของหลอดเลือด = เส้นเลือดขอด)
  และดู diagnosis ร่วมเพื่อรู้ว่าทำที่ส่วนไหนของร่างกาย (CORRECTION + ptosis = เปลือกตา · EXCISION + breast mass = เต้านม)
  จึงดูกติกาของสาขา (SP_RULES) ก่อน · คำที่ยังกำกวมในสาขาเดียวกันดูที่แพทย์ (SURGEON_RULES) · แล้วจึงใช้กติกาทั่วไป

วิธีใหม่ (ตรวจย้อนได้ทุกคำ ไม่มี fuzzy ทั้งประโยค)
  1. ทำความสะอาด : ตัดข้าง (RT/LT) วิธีระงับความรู้สึก (UNDER GA) วงเล็บหมายเหตุ คำไทยท้ายชื่อ
  2. แยกหัตถการพ่วงเป็นชิ้น ( A + B , A WITH B , A C B ) · ชิ้นหลัง +/- คือ "อาจทำ" ไม่นับเป็นหัตถการหลัก
  3. แต่ละชิ้นเทียบกับกติกา RULES ตามลำดับ (เจาะจงก่อน กว้างทีหลัง) → หัตถการมาตรฐาน + กลุ่ม + รหัส ICD-9-CM
  4. หัตถการหลักของเคส = ชิ้นที่ "ใหญ่" ที่สุด (ระดับ 1-4) เท่ากันเอาชิ้นแรก

รหัส ICD-9-CM ตรวจกับรายการ CMS ICD-9-CM v32 (Volume 3) แล้วว่ามีจริงทุกรหัส
⚠️ เป็นรหัสระดับ "หัตถการมาตรฐาน" เพื่อจัดหมวดสถิติ ไม่ใช่การให้รหัสรายเคสแทนเวชสถิติ

⛔ logic ล้วน ห้าม import streamlit · ยังไม่ถูกเรียกใช้จากแอปหรือแบบจำลอง จนกว่ามุกกี้ตรวจพจนานุกรมผ่าน
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

VERSION = "2026-11-21e"


class Std(NamedTuple):
    name: str          # ชื่อหัตถการมาตรฐาน (ใช้แสดงในสถิติ)
    group: str         # กลุ่มหัตถการ (19 กลุ่มเดิมของแบบจำลอง)
    icd9: str          # รหัส ICD-9-CM (Volume 3) ที่เป็นตัวแทน
    level: int         # ขนาดหัตถการ 1 เล็ก .. 4 ใหญ่มาก (ใช้เลือกหัตถการหลัก) · 0 = ส่องตรวจ/ฉีดสีนำทาง ที่มักพ่วงหัตถการจริง


# ── กติกา : (รูปแบบ, ชื่อมาตรฐาน, กลุ่ม, ICD-9-CM, ระดับ) เรียงจากเจาะจงไปกว้าง ──
_R = [
    # 🩺 มุกกี้ตัดสิน 21 พ.ย. 2026 (20:29) จากแผ่น "คำที่ต้องตัดสิน"
    #    ฉีดยาเข้าช่องไขสันหลัง / เส้นประสาทส่วนปลาย = pain management ทำโดยวิสัญญีแพทย์ จัดกลุ่ม Non-surgical
    (r'INJECTION\s+OF\s+.*SPINAL\s+CANAL|\bSI\s+JOINT\s+INJ|\bESI\b', 'Spinal injection (pain management)', 'Non_surgical', '03.92', 1),
    (r'INJECTION\s+OF\s+ANESTHETIC\s+INTO\s+PERIPHERAL\s+NERVE', 'Peripheral nerve block (pain management)', 'Non_surgical', '04.81', 1),
    #    FRENULECTOMY (ankyloglossia) = ตัดเนื้อเยื่อยึดใต้ลิ้น ศัลยกรรมเด็ก
    (r'FRENULECTOMY|FRENECTOMY', 'Lingual frenulectomy', 'ENT', '25.92', 1),
    #    FIA = fistula-in-ano อาจเป็น fistulotomy / fistulectomy / LIFT : ไม่ระบุชนิด นับแยกไว้
    (r'^FIA(\s+OPERATION)?$|FISTULA\s*-?\s*IN\s*-?\s*ANO', 'Anal fistula surgery (type unspecified)', 'Anorectal', '49.11', 1),
    # ═══ สายสวนฟอกไต / สายสวนหลอดเลือดดำ ═══
    (r'REVI[SC]\w*.*\b(TCC|PERM)|\b(TCC|PERM)\b.*REVIS', 'Revise TCC', 'Central_line', '38.95', 1),
    (r'DLC\s*(TO|>|->)?\s*TCC|CHANGE\s+DLC', 'DLC to TCC', 'Central_line', '38.95', 1),
    (r'\b(OFF|REMOV\w*)\b.*\b(TCC|PERM|DLC|CATH\w*)\b(?!.*(DJ|JJ|FOLEY|URETH))', 'Off TCC/DLC', 'Central_line', '97.49', 1),
    (r'\bTCC\b|TUNNEL\w*\s+CUFF|\bPERM\b|PALINDROME|HEMOFLOW', 'TCC insertion', 'Central_line', '38.95', 1),
    (r'\bDLC\b', 'DLC insertion', 'Central_line', '38.95', 1),
    (r'(REMOV\w*|OFF)\s+(CHEMO\s*)?PORT|PORT\w*\s+REMOV|CHEMOPORT\s+REMOV', 'Chemoport removal', 'Central_line', '86.05', 1),
    (r'CHEMO\s*PORT|PORT\s*-?\s*A\b|PORTA\b', 'Chemoport insertion', 'Central_line', '86.07', 1),
    (r'(OFF|REMOV\w*)\b.*\b(TK|TENCKHOFF)|\bTK\s+REMOV', 'Off TK catheter', 'Other', '97.82', 1),
    (r'\bTK\b|TENCKHOFF|\bPD\s+CATH', 'TK (Tenckhoff) catheter', 'Other', '54.93', 2),
    (r'C\s*-\s*LINE|CENTRAL\s+LINE|\bCVC\b|\bPICC\b', 'Central line', 'Central_line', '38.93', 1),
    # ═══ เส้นฟอกไต (AVF / AVBG) ═══
    (r'THROMBECTOMY|THORMBECTOMY', 'Graft thrombectomy', 'Vascular_access', '39.49', 2),
    (r'LIGAT\w*.*(AVF|AVBG|FISTULA)|(AVF|AVBG).*LIGAT', 'Ligate AVF/AVBG', 'Vascular_access', '39.53', 1),
    (r'REVIS\w*.*(AVBG|GRAFT)', 'Revise AVBG', 'Vascular_access', '39.42', 2),
    (r'REVIS\w*.*(AVF|FISTULA)', 'Revise AVF', 'Vascular_access', '39.42', 2),
    (r'PROXIMALI\w*|SUPERFICIALI\w*|\bTB\s*[12]\b|TRANSPOSITION', 'AVF transposition / superficialization', 'Vascular_access', '39.42', 2),
    (r'ANEURYSMECTOMY', 'Aneurysmectomy (AV access)', 'Vascular_access', '39.52', 2),
    (r'(REMOV\w*|OFF|EXCIS\w*|RESECT\w*)\b.*\b(AVBG|AVG|GRAFT)\b|GRAFT\s+(REMOV\w*|RESECT\w*)', 'Remove AVBG', 'Vascular_access', '39.43', 2),
    (r'\bAVBG\b|\bAVG\b|AV\s+GRAFT|LOOP\s+GRAFT', 'AVBG creation', 'Vascular_access', '39.27', 2),
    (r'\bAVF\b|A\s*-?V\s+FISTULA|BRACHIOCEPHALIC|RADIOCEPHALIC|\b[RB]C\s*-?\s*AVF', 'AVF creation', 'Vascular_access', '39.27', 2),
    # ═══ หลอดเลือด (หัตถการสวน/ผ่าตัด) ═══
    (r'\bEVAR\b|\bTEVAR\b', 'EVAR / TEVAR', 'Vascular_interv', '39.71', 3),
    (r'FISTULOGRAM', 'Fistulogram', 'Vascular_interv', '88.49', 0),
    (r'BALLOON|VENOPLAST|VENOPALST|ANGIOPLAST|\bPTA\b|ATHERECTOMY|ARTHRECTOMY', 'Balloon angioplasty / venoplasty (PTA)', 'Vascular_interv', '39.50', 1),
    (r'CHOLANGIOGRA|CHOLECYSTOGRA', 'Cholangiogram', 'Hepatobiliary', '87.54', 0),
    (r'ANGIOGRAM|VENOGRAM', 'Angiogram / venogram', 'Vascular_interv', '88.49', 0),
    (r'VENASEAL|\bEVL[TA]\b|\bHL\b|HIGH\s+LIGATION|STRIPPING|\bVS\b|PHLEBECTOMY|PHELBECTOMY|VARICOSE|STAB\s+AVULSION', 'Varicose vein surgery', 'Vascular_interv', '38.59', 2),
    (r'\bRFA\b(?!.*(LIVER|HCC|THYROID|HEM))', 'Varicose vein surgery', 'Vascular_interv', '38.59', 2),
    (r'BYPASS', 'Arterial bypass', 'Vascular_interv', '39.29', 4),
    (r'EMBOLECTOMY', 'Thromboembolectomy', 'Vascular_interv', '38.08', 3),
    (r'SYMPATHECTOMY', 'Sympathectomy', 'Other', '05.29', 2),
    (r'\bBKA\b|BELOW\s+KNEE', 'Below-knee amputation (BKA)', 'Other', '84.15', 2),
    (r'\bAKA\b|ABOVE\s+KNEE', 'Above-knee amputation (AKA)', 'Other', '84.17', 2),
    (r'AMPUTAT', 'Toe / ray amputation', 'Other', '84.11', 1),
    # ═══ ส่องกล้องทางเดินอาหาร ═══
    (r'\bERCP\b', 'ERCP', 'Endoscopy_GI', '51.10', 2),
    (r'EGDCOLONO', 'EGD + Colonoscopy', 'Endoscopy_GI', '45.23', 1),
    (r'COLONO|COLONSO|COLONSCOP', 'Colonoscopy', 'Endoscopy_GI', '45.23', 1),
    (r'\bEGD\b|GASTROSCOP|^GASTRO$|ESOPHAGOGASTRO|ENDOSCOPY\s+OF\s+SMALL\s+INTESTINE', 'EGD', 'Endoscopy_GI', '45.13', 1),
    (r'SIGMOIDOSCOP', 'Sigmoidoscopy', 'Endoscopy_GI', '45.24', 1),
    (r'\bPEG\b|GASTROSTOMY', 'Gastrostomy', 'GI_abdominal', '43.19', 2),
    # ═══ ทวารหนัก ═══
    (r'(LASER|RFA)\s+HEM|HEM\w*(PLASTY|PALSTY|PEXY)', 'Laser / RFA hemorrhoidoplasty', 'Anorectal', '49.49', 1),
    (r'HEMM?ORR?H?I?OI?D', 'Hemorrhoidectomy', 'Anorectal', '49.46', 1),
    (r'(BROW|FACE|TEMPORAL|NECK|MID\w*|FOREHEAD)\s*-?\s*LIFT|LIFTING', 'Face / brow lift', 'Skin_softtissue', '86.82', 3),
    (r'\bLIFT\b', 'LIFT (anal fistula)', 'Anorectal', '49.73', 1),
    (r'FISTULOTOMY|FISTULECTOMY|\bSETON\b|\bFIPS\b', 'Anal fistulotomy / fistulectomy', 'Anorectal', '49.11', 1),
    (r'\bLIS\b|SPHINCTEROTOMY', 'Lateral internal sphincterotomy (LIS)', 'Anorectal', '49.51', 1),
    (r'KARYDAKIS|PILONIDAL', 'Pilonidal sinus excision', 'Anorectal', '86.21', 2),
    (r'TRANSANAL|TRANANAL|\bTAMIS\b', 'Transanal excision', 'Anorectal', '48.35', 2),
    (r'ALTE?I?MEIER|DELORME|PROLAPSE|RECTOPEXY|RECTOPLEXY', 'Rectal prolapse repair', 'Anorectal', '48.76', 3),
    # ═══ ตับ ทางเดินน้ำดี ตับอ่อน ═══
    (r'WHIPPLE|PANCREATI?C?O?DUODEN', 'Whipple operation', 'Hepatobiliary', '52.7', 4),
    (r'PANCREATECTOMY|\bRAMPS\b|\bDP\b', 'Pancreatectomy', 'Hepatobiliary', '52.52', 4),
    (r'HEPATECTOMY|LIVER\s+RESECTION|WEDGE.*(LIVER|S\d)|\bRH\b|\bLH\b|SECTIONECTOMY|SEG\w*IONECTOMY|SEGMENTECTOMY|\bS\d\w*\s+(RESECTION|SEGMENT)|LIVER\s+S\d|CAUDATE|RESECTION\s+SEGMENT', 'Liver resection', 'Hepatobiliary', '50.22', 4),
    (r'(MICROWAV\w*|\bMWA\b|\bRFA\b|ABLATION).*THYROID|THYROID.*ABLATION', 'Thyroid ablation (MWA / RFA)', 'Thyroid_neck', '06.98', 2),
    (r'MICROWAVE|\bMWA\b|\bIRE\b|\bRFA\b', 'Tumor ablation (MWA / RFA / IRE)', 'Hepatobiliary', '50.24', 2),
    (r'\bOC\b|OPEN\s+CHOLE?CYST', 'Open cholecystectomy', 'Hepatobiliary', '51.22', 3),
    (r'\bLC\b|CHOLE?CYSTECT', 'Laparoscopic cholecystectomy (LC)', 'Hepatobiliary', '51.23', 2),
    (r'SPLENECTOMY', 'Splenectomy', 'GI_abdominal', '41.5', 3),
    # ═══ ช่องท้อง ลำไส้ ═══
    (r'APPE\w*ECTOMY', None, None, None, 0),          # แยก lap/open ด้านล่าง (_APPROACH)
    (r'\bTEP\b|\bTAPP\b|\bIPOM\b|HERNIO|HERNIA|HENIO', None, None, None, 0),
    (r'SIGMOIDECTOMY', None, None, None, 0),
    (r'\bE?[RL]HC\b|HEMICOLECTOMY', None, None, None, 0),
    (r'\bLAR\b|\bAR\b|\bAPR\b|ANTERIOR\s+RESECTION', 'Rectal resection (AR / LAR / APR)', 'GI_abdominal', '48.63', 4),
    (r'COLECTOMY', 'Colectomy (subtotal / total)', 'GI_abdominal', '45.79', 4),
    (r'CLOSURE\s+(OF\s+)?(COLOSTOMY|ILEOSTOMY|COLOTOMY)', 'Closure of colostomy / ileostomy', 'GI_abdominal', '46.52', 2),
    (r'COLOSTOMY|ILEOSTOMY', 'Colostomy / ileostomy creation', 'GI_abdominal', '46.10', 2),
    (r'GASTRECTOMY', 'Gastrectomy', 'GI_abdominal', '43.89', 4),
    (r'SMALL\s+BOWEL\s+RESECTION|\bSB\s+RESECTION', 'Small bowel resection', 'GI_abdominal', '45.62', 3),
    (r'\bEL\b|E/L|EXPLOR\w*\s+LAP\w*|LAPAROTOMY', 'Exploratory laparotomy', 'GI_abdominal', '54.11', 3),
    # ═══ เต้านม ═══
    (r'MASTEC\w+|\bMRM\b|\bTM\b|\bNSM\b|\bSSM\b', 'Mastectomy', 'Breast', '85.41', 3),
    (r'\bBCT\b|BREAST\s+CONSERV|LUMPECTOMY|QUA\w*DRANTECTOMY|(WIRE|NEEDLE)\s+LOCALI\w*|\bNL\b|\bNLWE\b|WIDE\s+EXCISION.*BREA\w+', 'Breast-conserving surgery (BCT / wide excision)', 'Breast', '85.21', 2),
    (r'BREA?ST?\w*\s+IMPLANT|IMPLANT.*BREAST|AUGMENT|RECONSTRUCT', 'Breast implant / reconstruction', 'Breast', '85.53', 3),
    (r'\bVA[EB][BE]?\b|MICRODOCHECTOMY|\bNLE\b|BREAST\s+MASS|EXCIS\w*.*BREAST|ACCESSORY\s+BREAST|LESION\s+OF\s+BREAST|BREAST\s+TISSUE', 'Excision of breast mass / VAE', 'Breast', '85.21', 1),
    (r'\bSLNB\b|\bALND\b|AXILLARY\s+(NODE|LN|LYMPH|DISSECT)', 'Axillary surgery (SLNB / ALND)', 'Breast', '40.23', 1),
    # ═══ ไทรอยด์ คอ ═══
    (r'TOETVA', 'TOETVA (transoral endoscopic thyroidectomy)', 'Thyroid_neck', '06.39', 3),
    (r'PARATHYROID', 'Parathyroidectomy', 'Thyroid_neck', '06.89', 3),
    (r'\b(TOTAL|COMPLETE|COMPLETION)\s+\w*\s*THYROIDECTOMY|THYROIDECTOMY.*TOTAL|\bTTD\b', 'Total thyroidectomy', 'Thyroid_neck', '06.4', 3),
    (r'THYROID\s*LOBECTOMY|ISTHMECTOMY|HEMITHYROID|LINGUAL\s+THYROID', 'Thyroid lobectomy', 'Thyroid_neck', '06.2', 3),
    (r'THYROIDECTOMY', 'Thyroidectomy (unspecified)', 'Thyroid_neck', '06.39', 3),
    (r'NECK\s+DISSECTION', 'Neck dissection', 'Thyroid_neck', '40.41', 3),
    (r'LYMPH\s+NODE|\bLN\b', 'Lymph node excision / biopsy', 'Thyroid_neck', '40.21', 1),
    (r'PAROTIDECTOMY|SIALOADEN|SALIVA\w+|SUBMANDIBUL', 'Salivary gland excision', 'ENT', '26.30', 3),
    (r'(CHANGE|REPLACE)\w*\s+TRACHEO', 'Change tracheostomy tube', 'Tracheostomy', '97.23', 1),
    (r'TRAC\w*OSTOMY|TRACHESOTOMY|TRACHOESTOMY|^TRACHEO$', 'Tracheostomy', 'Tracheostomy', '31.1', 1),
    # ═══ หู คอ จมูก ═══
    (r'TONSI+LL?ECTOMY|ADENOIDECTOMY|\bT\s*(&|AND)?\s*A\b|^T$', 'Tonsillectomy ± adenoidectomy', 'ENT', '28.2', 2),
    (r'\bRF\b|\bRFIT\b|RADIOFREQ', 'Radiofrequency (nose / palate)', 'ENT', '21.61', 1),
    (r'\bFESS\b|\bESS\b|\bMMA\b|ANTROSTOMY|SINUS\s+SURG|SPHENOIDOTOMY|SINUSOTO\w+|NASAL\s+POLYP|ENDOSCOPIC\s+POLYPECTOMY', 'Endoscopic sinus surgery (FESS / ESS)', 'ENT', '22.60', 3),
    (r'RHINOPLASTY', 'Rhinoplasty', 'ENT', '21.87', 3),
    (r'SEPTO|TURBIN|TUBINOPLASTY', 'Septoplasty / turbinoplasty', 'ENT', '21.88', 2),
    (r'TYMPANO|MYRINGOPLASTY|MASTOID', 'Tympanoplasty / mastoidectomy', 'ENT', '19.4', 3),
    (r'MYRINGOTOMY|PE\s+TUBE', 'Myringotomy ± PE tube', 'ENT', '20.01', 1),
    (r'\bDL\b|MICRO\s*DL|LARYNGOSCOP|\bMLS\b|MICROLARYNG', 'Direct laryngoscopy ± biopsy', 'ENT', '31.42', 1),
    (r'GLOSSECTOMY', 'Glossectomy', 'ENT', '25.1', 3),
    (r'MANDIBULECTOMY|MAXILLECTOMY', 'Mandibulectomy / maxillectomy', 'ENT', '76.39', 4),
    (r'UVUL\w+|PALATOPLASTY|\bUPPP\b|\bBSP\b|\bCAPSO\b', 'Palatal surgery (UPPP / uvulectomy)', 'ENT', '27.69', 2),
    # ═══ ทางเดินปัสสาวะ ═══
    (r'TUR\s*-?\s*BT|TURBT|\bTUF\b', 'TURBT', 'Cystoscopy_URO', '57.49', 2),
    (r'TUR\s*-?\s*P\b|\bTURP\b|\bHOLEP\b|\bTHULEP\b|TRANSURETHRAL\s+PROSTATECTOMY', 'TURP / HoLEP', 'Cystoscopy_URO', '60.29', 2),
    (r'REZUM|WATER\s+VAPOR', 'Rezum (water vapor therapy)', 'Cystoscopy_URO', '60.97', 1),
    (r'\bPCNL\b', 'PCNL', 'Uro_other', '55.04', 3),
    (r'\bRIRS\b|\bURSL?\b|URS\s+L\b|URETEROSCOP', 'Ureteroscopy (URS / URSL / RIRS)', 'Cystoscopy_URO', '56.31', 2),
    (r'\bESWL\b', 'ESWL', 'Uro_other', '98.51', 1),
    (r'(OFF|REMOV\w*)\b.*\b(DJ|JJ)\b|\b(DJ|JJ)\b.*\b(REMOV\w*|OFF)', 'Off DJ stent', 'Cystoscopy_URO', '97.62', 1),
    (r'(CHANGE|EXCHA\w*)\b.*\b(DJ|JJ)\b|\b(DJ|JJ)\b.*(CHANGE|EXCHA\w*)', 'Change DJ stent', 'Cystoscopy_URO', '59.8', 1),
    (r'\b(DJ|JJ)\b', 'DJ stent insertion', 'Cystoscopy_URO', '59.8', 1),
    (r'TRUS|TRUX|TRIUX|PROSTATE\s+B(X|IOPSY)|FUSION\s*(B|C\b|$)|MRI\s*-?\s*(US|FUSION)', 'Prostate biopsy (TRUS / MRI fusion)', 'Cystoscopy_URO', '60.11', 1),
    (r'CYSTOLIT\w+|LITHOLAPAXY', 'Cystolitholapaxy', 'Cystoscopy_URO', '57.0', 2),
    (r'CYSTOGRAM|LOOPOGRAM', 'Cystogram', 'Cystoscopy_URO', '87.77', 1),
    (r'CYSTOSTOMY|CYSTOTOMY|SUPRAPUBIC', 'Suprapubic cystostomy', 'Cystoscopy_URO', '57.18', 1),
    (r'F?CYSTO\w*|FLEX\w*\s+CYSTO|URETHROSCOP', 'Cystoscopy', 'Cystoscopy_URO', '57.32', 0),
    (r'URETHRAL?\s+DILAT|DILA?T\w*\s+URETHRA|\bDIALTE\b', 'Urethral dilation', 'Cystoscopy_URO', '58.6', 1),
    (r'URETHROPLASTY', 'Urethroplasty', 'Uro_other', '58.49', 3),
    (r'MEATOTOMY', 'Meatotomy', 'Uro_other', '58.1', 1),
    (r'NEPHRO?\w*ECTOMY', 'Nephrectomy', 'Uro_other', '55.51', 4),
    (r'ADRENALECTOMY', 'Adrenalectomy', 'Uro_other', '07.22', 3),
    (r'PROSTATECTOMY|\bLRP\b', 'Radical prostatectomy', 'Uro_other', '60.5', 4),
    (r'\bCYSTECTOMY', 'Cystectomy', 'Uro_other', '57.71', 4),
    (r'\b[DL]?DKT\b|\bL?R?KT\b|KIDNEY\s+TRANSPLANT', 'Kidney transplantation', 'Uro_other', '55.69', 4),
    (r'NEPHROSTOMY|\bPCN\b', 'Nephrostomy (PCN)', 'Uro_other', '55.03', 1),
    (r'CIRCUMCIS', 'Circumcision', 'Uro_other', '64.0', 1),
    (r'VASECTOMY', 'Vasectomy', 'Uro_other', '63.73', 1),
    (r'ORCHID?ECTOMY', 'Orchiectomy', 'Uro_other', '62.3', 1),
    (r'HYDROCELE', 'Hydrocelectomy', 'Uro_other', '61.2', 1),
    (r'VARICOCELE', 'Varicocelectomy', 'Uro_other', '63.1', 2),
    (r'PARAFFIN|PARAFIN', 'Excision of penile paraffinoma', 'Uro_other', '64.2', 2),
    # ═══ สมอง ═══
    (r'CRAN\w*(OTOMY|ECTOMY|ECOTMY).*(MICROVASCULAR|\bMVD\b)|MICROVASCULAR\s+DECOMP|\bMVD\b', 'Craniotomy with microvascular decompression', 'Neuro_cranial', '04.41', 4),
    (r'CRAN\w*(OTOMY|ECTOMY|ECOTMY)', None, None, None, 0),   # แยกชนิดด้านล่าง
    (r'BUR+\s*HOLE|SUBDURAL\s+DRAIN', 'Burr hole drainage', 'Neuro_cranial', '01.31', 2),
    (r'CRAN\w*PLASTY', 'Cranioplasty', 'Neuro_cranial', '02.06', 3),
    (r'\bVP\b|\bV\s*-\s*P\b|SHUNT', 'VP shunt', 'Neuro_cranial', '02.34', 2),
    (r'\bEVD\b|VENT\w*CULOSTOMY', 'External ventricular drainage (EVD)', 'Neuro_cranial', '02.21', 2),
    (r'TRANS\w*PHENOID|\bTSS\b|TRANSNASAL|HYP\w*PHYSECTOMY', 'Endoscopic transsphenoidal tumor removal', 'Neuro_cranial', '07.62', 4),
    # ═══ กระดูกสันหลัง ═══
    (r'\bACDF\b', 'ACDF', 'Spine', '81.02', 3),
    (r'\b[TP]LIF\b|\bPDS\b|PEDIC\w+|\bTPS|FIXATION.*\b[CTL]\d|\b[CTL]\d[\d\s-]*(FIXATION|FUSION)|LAMINEC\w*.*FIX|CORPECTOMY|MIS\s+SCREW', 'Spinal decompression with fixation / fusion', 'Spine', '81.08', 4),
    (r'LAMINEC|LAINEC|LAMINOPLASTY|DIS+EC\w*TOMY|\bACDE\b', 'Laminectomy / discectomy', 'Spine', '03.09', 3),
    (r'KYPHOPLASTY|VERTEBROPLASTY', 'Kyphoplasty / vertebroplasty', 'Spine', '81.66', 2),
    # ═══ ทรวงอก ═══
    (r'TEMPORAL\s+LOBECTOMY', 'Temporal lobectomy', 'Neuro_cranial', '01.53', 4),
    (r'\bVATS?\b|THORACOSCOP|BLEBECTOMY|PLEURODESIS|DECORTICAT\w+|LOBECTOMY|THORACOTOMY|PERICARDI\w+|P\s*-?P\s*-?\s*WINDOW|STERNOTOMY|THYMECTOMY|RIBS?\s+RESECTION|PLEURECTOMY|WEDGE\s+RESECTION\s+[RL][UML]L|[RL][UML]L\s+MASS|BRONCHOSCOP|MEDIASTIN', 'Thoracic surgery (VATS / lung resection)', 'Other', '32.20', 4),
    (r'\bICD\b|CHEST\s+DRAIN', 'Chest drain insertion', 'Other', '34.04', 1),
    # ═══ หัตถการเฉพาะทางที่พบน้อย (เก็บหางยาว 21 พ.ย. 2026) ═══
    (r'HEPATICOJEJUNO|\bBDR\b|BILE\s+DUCT\s+RESECTION', 'Bile duct resection / hepaticojejunostomy', 'Hepatobiliary', '51.69', 4),
    (r'\bECMO\b', 'ECMO', 'Other', '39.65', 2),
    (r'(OFF|REMOV\w*)\s+IVC|IVC\s+FILTER\s+REMOV', 'IVC filter removal', 'Vascular_interv', '39.99', 1),
    (r'IVC\s+FILTER', 'IVC filter insertion', 'Vascular_interv', '38.7', 1),
    (r'CAROTID.*STENT', 'Carotid artery stenting', 'Vascular_interv', '00.63', 2),
    (r'ENDARTERECTOMY', 'Carotid endarterectomy', 'Vascular_interv', '38.12', 3),
    (r'COLON\w*\s+STENT', 'Colonic stent', 'Endoscopy_GI', '46.86', 1),
    (r'EMBOLI[ZS]ATION|\bTAE\b', 'Embolization', 'Vascular_interv', '39.79', 2),
    (r'PERITONEAL\s+WINDOW', 'Peritoneal window', 'GI_abdominal', '54.95', 2),
    (r'FASCIOTOMY', 'Fasciotomy', 'Skin_softtissue', '83.14', 2),
    (r'REVIS\w*\s+(\w+\s+)?STUMP|DISARTICULATION', 'Amputation stump revision', 'Other', '84.3', 2),
    (r'SPHINCTEROPLASTY|STRICTUROPLASTY', 'Anal sphincteroplasty / stricturoplasty', 'Anorectal', '49.79', 2),
    (r'PELVIC\s+EXENTERATION', 'Pelvic exenteration', 'GI_abdominal', '68.8', 4),
    (r'ORCHI\w*PL?EXY', 'Orchiopexy', 'Uro_other', '62.5', 1),
    (r'PYELOPLASTY', 'Pyeloplasty', 'Uro_other', '55.87', 3),
    (r'URETEROLITHOTOMY', 'Ureterolithotomy', 'Uro_other', '56.2', 3),
    (r'\bTUI\b|URETHROTOMY', 'Internal urethrotomy / TUI-BN', 'Cystoscopy_URO', '58.5', 1),
    (r'URETEROSTOMY\s+EXCHA\w*|(CHANGE|EXCHA\w*)\s+URETEROSTOMY', 'Change ureterostomy tube', 'Cystoscopy_URO', '59.93', 1),
    (r'HYPOSPADIAS|STAGE\s+REPAIR', 'Hypospadias repair', 'Uro_other', '58.45', 3),
    (r'\bDCR\b', 'Dacryocystorhinostomy (DCR)', 'ENT', '09.81', 2),
    (r'BREAST\s+REDUCTION|MAMMO?\s*REDUCTION|REDUCTION\s+MAMMO|MAMMOPLASTY', 'Reduction mammoplasty', 'Breast', '85.31', 3),
    (r'ABDOMIN\w*PLASTY|LIPECTOMY', 'Abdominoplasty / lipectomy', 'Skin_softtissue', '86.83', 3),
    (r'LIPOFILL|FAT\s+GRAFT', 'Lipofilling / fat graft', 'Skin_softtissue', '86.89', 2),
    (r'CHEILOPLASTY', 'Cheiloplasty', 'Skin_softtissue', '27.54', 2),
    (r'OSTEOTOMY|OSTECTOMY', 'Facial bone osteotomy', 'Fracture_fixation', '76.69', 3),
    (r'REMOV\w*\s+(SILICONE|PROSTHESIS|IMPLANT|FB\b|FOREIGN)|\bFB\s+REMOV', 'Removal of foreign body / implant', 'Skin_softtissue', '86.05', 1),
    (r'IRRIGAT\w+|OPEN\s+DRAINAGE|WOUND\s+TOILET', 'Wound irrigation / drainage', 'Skin_softtissue', '96.59', 1),
    # ═══ ตกแต่ง ผิวหนัง เนื้อเยื่ออ่อน ═══
    (r'BLEPHA\w+|\bUB\b|\bLB\b|EYELID|PTOSIS|ECTROPION|ENTROPION', 'Eyelid surgery (blepharoplasty / ptosis)', 'Blepharoplasty', '08.38', 2),
    (r'LIPOSUCTION', 'Liposuction', 'Skin_softtissue', '86.83', 2),
    (r'\bSTSG\b|\bFTSG\b|SKIN\s+GRAFT', 'Skin graft (STSG / FTSG)', 'Skin_softtissue', '86.69', 2),
    (r'\bFLAP\b', 'Flap coverage', 'Skin_softtissue', '86.74', 3),
    (r'(CHANGE\s+)?VACC?\b|VACC?U+M+N?', 'VAC dressing', 'Skin_softtissue', '86.28', 1),
    (r'DEBR\w*MENT|DEBRID\w*|^D\s*B\b|\bDB\b', 'Debridement', 'Skin_softtissue', '86.22', 1),
    (r'IANDD|\bI\s*(&|/)?\s*D\b|INCISION\s+WITH\s+DRAIN', 'Incision and drainage (I&D)', 'Skin_softtissue', '86.04', 1),
    (r'EXPLOR\w*\s+WOUND|STOP\s+BLEED', 'Wound exploration / stop bleeding', 'Skin_softtissue', '86.09', 2),
    (r'SUTURE|REPAIR\s+WOUND', 'Wound suture', 'Skin_softtissue', '86.59', 1),
    (r'SCAR|REVISION\s+OF\s+WOUND', 'Scar revision', 'Skin_softtissue', '86.84', 1),
    (r'NAIL', 'Nail procedure', 'Skin_softtissue', '86.23', 1),
    (r'(EXCIS\w*|INCIS\w*)\s*(B\s*X\b|BIOP\w*|BIOSY|BISOPSY)|^EXCISIONAL$|\bBIOPSY\b|\bBX\b', 'Biopsy (excisional / incisional)', 'Skin_softtissue', '86.11', 1),
    (r'WIDE\s+(LOCAL\s+)?EXC', 'Wide excision (skin / soft tissue)', 'Skin_softtissue', '86.4', 2),
    (r'EXC\w*ION|EXCISE|\bEC\b|MASS\s+REMOVAL|REMOV\w*\s+(MASS|LIPOMA|CYST)', 'Excision of skin / soft-tissue lesion', 'Skin_softtissue', '86.3', 1),
    # ═══ กระดูกและข้อ ═══
    (r'\bORIF\b|K\s*-?\s*WIRE|CLOSED?\s+RED\w+|\bCRIF\b|\bIMF\b|\bMMF\b|ARCH\s+BAR|INTERMAXILLARY|PLATE\s+AND\s+SCREW|\bCR\s+NASAL', 'Fracture reduction / fixation', 'Fracture_fixation', '79.30', 2),
    (r'TENDON', 'Tendon repair', 'Fracture_fixation', '83.64', 2),
]
RULES = [(re.compile(p), n, g, c, lv) for p, n, g, c, lv in _R]

# ═══ ชั้นสาขา (มุกกี้สั่ง 21 พ.ย. 2026 : คิดจากภาพใหญ่ สาขา >> แพทย์ >> หัตถการ) ═══
# คำเดียวกันคนละสาขาเป็นคนละหัตถการ จึงดูสาขาก่อนเสมอ แล้วค่อยตกมาที่กติกาทั่วไป
SPECIALTIES = {
    'GEN': 'ศัลยกรรมทั่วไป', 'NEU': 'ศัลยกรรมประสาทและสมอง', 'ENT': 'ศัลยกรรมหู คอ จมูก',
    'PLA': 'ศัลยกรรมตกแต่ง', 'URO': 'ศัลยกรรมระบบทางเดินปัสสาวะ',
    'CRS': 'ศัลยกรรมลำไส้ใหญ่และทวารหนัก', 'VAS': 'ศัลยกรรมหลอดเลือด', 'CVT': 'ศัลยกรรมทรวงอก',
    'HPB': 'ศัลยกรรมตับ ตับอ่อน ทางเดินน้ำดี', 'TX': 'ปลูกถ่ายอวัยวะ',
}
_SP_BY_NAME = {v: k for k, v in SPECIALTIES.items()}
_SP_BY_DIV = {'1': 'GEN', '2': 'NEU', '3': 'ENT', '4': 'PLA', '5': 'URO', '6': 'CRS', '7': 'VAS',
              '8': 'CVT', '9': 'HPB', '10': 'TX', '74': 'PLA', '75': 'GEN', '76': 'URO',
              '77': 'ENT', '78': 'VAS'}


def specialty_key(specialty) -> str:
    """ชื่อสาขา (ไทย) หรือรหัส division ของ HIS → รหัสย่อ เช่น 'ENT' · ไม่รู้จัก = ''"""
    s = re.sub(r'\s+', ' ', str(specialty or '').strip())
    if s.endswith('.0'):
        s = s[:-2]
    if s in SPECIALTIES:
        return s
    return _SP_BY_NAME.get(s) or _SP_BY_DIV.get(s) or ''


# (สาขา) → [(รูปแบบของชิ้น, รูปแบบที่ "ห้ามมี" ในทั้งชื่อ หรือ None, ชื่อมาตรฐาน, กลุ่ม, ICD-9-CM, ระดับ)]
_SP = {
    'ENT': [
        (r'\bLOBECTOMY\b', r'LUNG|\b[RL][UML]L\b', 'Thyroid lobectomy', 'Thyroid_neck', '06.2', 3),
        (r'ENDOSCOPIC\s+TUMOU?R\s+REMOV', None, 'Endoscopic sinonasal tumor removal', 'ENT', '21.31', 3),
        (r'\bSPA\s+LIGAT', None, 'Sphenopalatine artery ligation', 'ENT', '21.09', 2),
        (r'\bT\s*-?\s*PLASTY', None, 'Tympanoplasty / mastoidectomy', 'ENT', '19.4', 3),
    ],
    'NEU': [
        (r'TUMOU?R\s+REMOV|\bSOC\b', r'LAMINEC|SPINE|\b[CTL]\d|TRANS\w*SPHENOID',
         'Craniotomy with tumor removal', 'Neuro_cranial', '01.59', 4),
        (r'\bTPS\b|\bC\d\s*-\s*\d\s+(FIXATION|FUSION)', None,
         'Spinal decompression with fixation / fusion', 'Spine', '81.08', 4),
    ],
    'URO': [
        (r'\bIRE\b', None, 'Prostate IRE (focal therapy)', 'Uro_other', '60.61', 2),
        # 🩺 คำย่อของทางเดินปัสสาวะ (มุกกี้ตัดสิน 21 พ.ย. 2026 20:29)
        (r'^LASER\s+VC$|VESICOLITHO\w*', None, 'Cystolitholapaxy', 'Cystoscopy_URO', '57.0', 2),      # VC = vesical calculus
        (r'\bSLING\b|\bTVT\b|\bTOT\b', None, 'Suburethral sling', 'Uro_other', '59.79', 2),
        (r'^S\s*-?\s*CURVE$|TIEMAN', None, 'Urethral dilation', 'Cystoscopy_URO', '58.6', 1),          # sound โค้งรูปตัว S / Tiemann
        (r'^U\s*-?\s*CATH$', None, 'Ureteral catheterization', 'Cystoscopy_URO', '59.8', 1),
        (r'PENI\w+', r'PARAF', 'Penile augmentation / reconstruction', 'Uro_other', '64.49', 2),
    ],
}
for _k in ('GEN', 'HPB', 'CRS'):
    _SP[_k] = [(r'\bRFA\b|MICROWAV\w*|\bMWA\b', r'HEM|THYROID|LEG|STAB|PHLEB|VARICOSE',
                'Tumor ablation (MWA / RFA / IRE)', 'Hepatobiliary', '50.24', 2)]
SP_RULES = {k: [(re.compile(p), re.compile(x) if x else None, n, g, c, lv) for p, x, n, g, c, lv in v]
            for k, v in _SP.items()}

# ═══ ชั้นแพทย์ : คำกำกวมที่ต้องรู้ว่าแพทย์คนนั้นทำอะไรเป็นหลัก ═══
# (สาขา, รหัสแพทย์ SURG_xxx, คำหลังทำความสะอาด) → Std · เว้นว่างไว้จนกว่ามุกกี้ตัดสินจากแผ่น "คำกำกวม"
# ⛔ ใส่ได้เฉพาะรหัส SURG_xxx ห้ามใส่ชื่อจริง (ไฟล์นี้เข้า git)
SURGEON_RULES: dict = {}

_LAP = re.compile(r'\bLAP\w*\b|LAPARO|\bTEP\b|\bTAPP\b|ROBOT')


def _by_approach(comp: str) -> Optional[Std]:
    """หัตถการที่ต้องแยก ส่องกล้อง กับ เปิด เพราะเวลาใช้ห้องต่างกัน และกลุ่มสมองที่แยกตามชนิด"""
    lap = bool(_LAP.search(comp))
    if re.search(r'APPE\w*ECTOMY', comp):
        return (Std('Laparoscopic appendectomy', 'GI_abdominal', '47.01', 2) if lap
                else Std('Open appendectomy', 'GI_abdominal', '47.09', 2))
    if re.search(r'\bTEP\b|\bTAPP\b|\bIPOM\b|HERNIO|HERNIA|HENIO', comp):
        if re.search(r'INCISIONAL|VENTRAL|UMBILICAL|\bIPOM\b', comp):
            return Std('Ventral / incisional hernia repair', 'GI_abdominal', '53.61', 2)
        return (Std('Laparoscopic inguinal hernia repair (TEP / TAPP)', 'GI_abdominal', '17.13', 2) if lap
                else Std('Open inguinal hernioplasty', 'GI_abdominal', '53.05', 2))
    if 'SIGMOIDECTOMY' in comp:
        return (Std('Laparoscopic sigmoidectomy', 'GI_abdominal', '17.36', 3) if lap
                else Std('Open sigmoidectomy', 'GI_abdominal', '45.76', 3))
    if re.search(r'\bE?[RL]HC\b|HEMICOLECTOMY', comp):
        return (Std('Laparoscopic hemicolectomy', 'GI_abdominal', '17.33', 3) if lap
                else Std('Open hemicolectomy', 'GI_abdominal', '45.73', 3))
    if re.search(r'CRAN\w*(OTOMY|ECTOMY|ECOTMY)', comp):
        if re.search(r'CLOT|HEMATOMA|EVACUAT|DECOMPRESS', comp):
            return Std('Craniotomy / craniectomy with clot removal', 'Neuro_cranial', '01.24', 4)
        if re.search(r'TUMOU?R|CUSA|\bBX\b|BIOPSY', comp):
            return Std('Craniotomy with tumor removal', 'Neuro_cranial', '01.59', 4)
        return Std('Craniotomy / craniectomy (other)', 'Neuro_cranial', '01.24', 4)
    return None


# ── ทำความสะอาด ──
_ANES = (r'(?:IV\s+SEDAT\w*|SEDAT\w*|TIVA|MAC|LOCAL(?:\s+AN\w*)?|FULL\s+GA|GA|LA|SB|SA|TA|ETT)')
_CLEAN = [
    # รุ่น v4 : คำที่มีเครื่องหมายอยู่ข้างใน ต้องรวมก่อนถูกแยกชิ้นด้วย + , &
    (re.compile(r'\bE\s*(?:&|\+|AND)\s*C\b|\bE\.\s*C\b\.?'), ' ELECTROCAUTERY '),
    (re.compile(r'CHEM,OPORT'), 'CHEMOPORT'),
    (re.compile(r'TUR\*-?BT'), 'TURBT'),
    (re.compile(r'\bD[HK]\\?J\b'), 'DJ'),
    (re.compile(r'[฀-๿]+[^+,]*'), ' '),                         # ข้อความไทยท้ายชื่อ (นอกเวลา รายปี ชื่อคน)
    (re.compile(r'\([^)]*\)|\*+[^*]*\*+'), ' '),                           # (OPD, TIVA)  **เคส1**
    (re.compile(r'\bUNDER\s*' + _ANES + r'\b|\bUNDERGA\b|\bU[BN]DER\s+\w+(\s+SEDAT\w*)?'), ' '),
    (re.compile(r'[/,]\s*' + _ANES + r'\b\s*$'), ' '),
    (re.compile(r'\b(RT|LT|RIGHT|LEFT|BILATERAL|BILAT|BIALTERAL|BOTH)\b\.?'), ' '),
    (re.compile(r'(EGD|GASTRO\w*)\s*(\+|AND|&|WITH|,|/|THEN)?\s*COLO\w+'), ' EGDCOLONO '),
    (re.compile(r'\bI\s*(AND|&|\+)\s*D\b|INCISION\s+(AND|&)\s+DRAIN\w*'), ' IANDD '),
    # craniotomy WITH clot removal = หัตถการเดียว ไม่แยกชิ้น
    (re.compile(r'(CRAN\w+)\s*(?:WITH|AND|\+|C)\s+(?=BLOOD|CLOT|TUMOU?R|HEMATOMA|EVACUAT|MICROVASC|MVD|CUSA|REMOV)'), r'\1 '),
    (re.compile(r'COLONOSCOPY\s*,\s*OTHER\s+ENDOSCOPY\s+OF\s+SMALL\s+INTESTINE'), ' EGDCOLONO '),
]
_OPT = re.compile(r'\+\s*/\s*-|\+\s*-|±')
_SPLIT = re.compile(r'\s*\+\s*|\s+WITH\s+|\s+W\s+|\s+C\s+|\s*,\s*|\s+AND\s+|\s+THEN\s+|\s*;\s*|\s+OR\s+')


def clean(raw) -> str:
    s = re.sub(r'\s+', ' ', str(raw or '').upper()).strip()
    s = spellfix(s)                                  # 🔤 แก้คำสะกดผิดทีละคำก่อนเทียบกติกา (รุ่น v4)
    for pat, rep in _CLEAN:
        s = pat.sub(rep, s)
    return re.sub(r'\s+', ' ', s).strip(' .+-/')


def classify_component(comp: str, sp: str = '', ctx: str = '') -> Optional[Std]:
    comp = re.sub(r'[._]', ' ', comp)
    comp = re.sub(r'\s+', ' ', comp).strip(' -/')
    if not comp:
        return None
    for pat, bad, name, group, code, lv in SP_RULES.get(sp, ()):
        if pat.search(comp) and not (bad is not None and bad.search(ctx or comp)):
            return Std(name, group, code, lv)
    for pat, name, group, code, lv in RULES:
        if pat.search(comp):
            if name is None:
                got = _by_approach(comp)
                if got is not None:
                    return got
                continue
            return Std(name, group, code, lv)
    for sps, pat, name in _R2:                         # 🩺 กติกาชั้นสุดท้าย (รุ่น v4) : เฉพาะชิ้นที่กติกาเดิมจัดไม่ได้
        if (sps is None or sp in sps) and pat.search(comp):
            bad = _R2_BAD.get(name)
            if bad is not None and bad.search(ctx or comp):
                continue
            return _std(name)
    return None


# ═══ ชั้นการวินิจฉัย (มุกกี้สั่ง 21 พ.ย. 2026 : ดู diagnosis ร่วม จะได้รู้ว่าทำที่ส่วนไหนของร่างกาย) ═══
# ชื่อหัตถการกว้าง ๆ (EXCISION / CORRECTION / REVISION / DEBRIDEMENT) ไม่บอกตำแหน่ง แต่ diagnosis บอก
_SITES = [(re.compile(p), n) for p, n in [
    (r'BREAST|NIPPLE|FIBROADENOMA|PHYLLOD|GYNECOMASTIA', 'เต้านม'),
    (r'EYELID|PTOSIS|ENTROPION|ECTROPION|XANTHEL|DERMATOCHALASIS|BLEPHAR|\bEYES?\b|CANTH', 'เปลือกตา'),
    (r'TONGUE|\bLIPS?\b|BUCCAL|\bGUM\b|PALATE|MUCOCELE|\bORAL\b|VESTIBULE|\bMOUTH\b|RANULA|TONSIL', 'ช่องปาก'),
    (r'\bEARS?\b|PINNA|LOBULE|AURIC|HELIX|PREAURICULAR', 'หู'),
    (r'NASAL|\bNOSE\b|RHINO|SINUS(?!\s+TRACT)|SEPTUM|INVERTED\s+PAPILLOMA', 'จมูก'),
    (r'\bNECK\b|SUBMANDIB|SUBMENTAL|THYROGLOSS|BRANCHIAL|CERVICAL\s+L|SUPRACLAV|THYROID|PAROTID', 'คอ'),
    (r'\bFACE\b|FACIAL|SCALP|\bHEAD\b|FOREHEAD|\bCHIN\b|CHEEK|TEMPORAL|\bBROW|OCCIP', 'ศีรษะและใบหน้า'),
    (r'\bANAL\b|PERIANAL|\bANUS\b|BUTTOCK|COCCYX|SACR|GLUTEAL|PILONIDAL|PERINE', 'ก้นและรอบทวารหนัก'),
    (r'PENI\w+|SCROT|TESTI|VULV|PREPUCE|FORESKIN', 'อวัยวะเพศ'),
    (r'\bHANDS?\b|FINGER|THUMB|WRIST|\bPALM\b', 'มือ'),          # แยกมือออกจากแขน (มุกกี้สั่ง 21 พ.ย. 2026)
    (r'\bARMS?\b|FOREARM|UPPERARM|SHOULDER|AXILLA|ELBOW', 'แขน'),
    (r'\bLEGS?\b|THIGH|\bFOOT\b|\bFEET\b|\bTOES?\b|KNEE|ANKLE|HEEL|PLANTAR|STUMP|\bHIP\b|MALLEOL|\bCALF\b', 'ขาและเท้า'),
    (r'\bBACK\b|CHEST|ABDOM|FLANK|UMBILIC|TRUNK|SUPRAPUBIC|GROIN|INGUINAL|STERN', 'ลำตัว'),
]]
# รหัสตำแหน่งแบบ ASCII ใช้ใน key ของแบบจำลอง (export_artifacts กรอง key ที่มีอักษรไทยทิ้ง)
_SITE_EN = {'เต้านม': 'BREAST', 'เปลือกตา': 'EYELID', 'ช่องปาก': 'ORAL', 'หู': 'EAR', 'จมูก': 'NOSE',
            'คอ': 'NECK', 'ศีรษะและใบหน้า': 'HEAD_FACE', 'ก้นและรอบทวารหนัก': 'PERIANAL',
            'อวัยวะเพศ': 'GENITAL', 'มือ': 'HAND', 'แขน': 'ARM', 'ขาและเท้า': 'LEG_FOOT', 'ลำตัว': 'TRUNK'}
_GENERIC = {'Excision of skin / soft-tissue lesion', 'Biopsy (excisional / incisional)',
            'Wide excision (skin / soft tissue)', 'Debridement', 'Incision and drainage (I&D)',
            'Wound suture', 'Scar revision', 'Skin graft (STSG / FTSG)', 'Flap coverage', 'VAC dressing',
            'Wound exploration / stop bleeding', 'Removal of foreign body / implant',
            'Wound irrigation / drainage', 'Fasciotomy'}
# ช่องหัตถการที่ไม่ใช่หัตถการ : รหัสระงับความรู้สึก หรือรายการเครื่องมือที่พิมพ์หลุดมา
_NONPROC = re.compile(r'^INJECTION\s+OF|INSERTION\s+OF\s+ENDOTRACHEAL|PROLONG\w*\s+INTUB|^MICROSCOPE|MAYFI|'
                      r'CONTRAST\s+AGENT|^ENDOSCOPE\s*,|^(VOID|NAN|-)?$')
NOT_PROCEDURE = 'ไม่ใช่หัตถการ (รหัสระงับความรู้สึกหรือรายการเครื่องมือ)'
_EXC = {'Excision of skin / soft-tissue lesion', 'Biopsy (excisional / incisional)'}


def body_site(diagnosis) -> str:
    """ข้อความ diagnosis → ส่วนของร่างกาย (ไทย) · บอกไม่ได้ = ''"""
    d = re.sub(r'\s+', ' ', str(diagnosis or '').upper())
    d = re.sub(r'(?<=[A-Z])\.(?=[A-Z])', '. ', d)          # LT.EAR → LT. EAR
    for pat, name in _SITES:
        if pat.search(d):
            return name
    return ''


def _by_diagnosis(c: str, main: Optional[Std], site: str, dx: str, sp: str) -> Optional[Std]:
    """คำกว้างที่ diagnosis ชี้ชัดว่าเป็นหัตถการเฉพาะ → Std นั้น · ไม่ชัด = คืนของเดิม"""
    name = main.name if main else ''
    if main is None:                                   # รุ่น v4 : คู่ ชื่อ + diagnosis ที่ความหมายชัด
        got = _infer_from_dx(c, site, dx, sp)
        if got is not None:
            return got
    if site == 'เต้านม':
        if name == 'Wide excision (skin / soft tissue)':
            return Std('Breast-conserving surgery (BCT / wide excision)', 'Breast', '85.21', 2)
        if name in _EXC:
            return Std('Excision of breast mass / VAE', 'Breast', '85.21', 1)
    if name in _EXC and site == 'ช่องปาก':
        return Std('Excision of oral lesion', 'ENT', '27.49', 1)
    if main is None and re.fullmatch(r'(RE\s*-?\s*)?CORRECT(ION|ED|)?', c):
        if site == 'เปลือกตา':
            return Std('Eyelid surgery (blepharoplasty / ptosis)', 'Blepharoplasty', '08.38', 2)
        if site == 'หู':
            return Std('Otoplasty (prominent ear)', 'ENT', '18.5', 2)
        if site == 'จมูก' and re.search(r'#|FRACTURE|\bFX\b', dx):
            return Std('Fracture reduction / fixation', 'Fracture_fixation', '79.30', 2)
        if re.search(r'SCAR|KELOID', dx):
            return Std('Scar revision', 'Skin_softtissue', '86.84', 1)
    if main is None and sp == 'URO' and c == 'RP':
        # RP กำกวม (มุกกี้ชี้ 21 พ.ย. 2026) : radical prostatectomy หรือ retrograde pyelogram ดูจาก diagnosis
        #    มะเร็งต่อมลูกหมากที่ไม่มีเรื่องท่อไต/ไต = ผ่าตัดต่อมลูกหมาก นอกนั้น = ฉีดสีย้อนทางท่อไต
        if re.search(r'PROSTAT', dx) and not re.search(r'\bPCN\b|HYDRO|STONE|STRICTURE|\bUPJ|URETER', dx):
            return Std('Radical prostatectomy', 'Uro_other', '60.5', 4)
        return Std('Retrograde pyelogram', 'Cystoscopy_URO', '87.74', 0)
    if main is None and re.fullmatch(r'REVIS(ION|E|ED)', c):
        # 💄 REVISION เฉย ๆ ส่วนใหญ่คือ revision scar (หัตถการเพื่อความสวยงาม) แยก lip กับ nipple
        #    (มุกกี้เคาะ 21 พ.ย. 2026)
        if re.search(r'NIPPLE|AREOLA', dx):
            return Std('Nipple revision', 'Breast', '85.87', 1)
        if re.search(r'\bLIPS?\b', dx):
            return Std('Lip revision', 'Skin_softtissue', '27.59', 1)
        if re.search(r'RHINOPLAST', dx):
            return Std('Rhinoplasty', 'ENT', '21.87', 3)
        return Std('Scar revision', 'Skin_softtissue', '86.84', 1)
    return main


def resolve(raw, specialty=None, surgeon=None, diagnosis=None) -> dict:
    """ชื่อหัตถการดิบ (+ สาขา + รหัสแพทย์) →
    {'main': Std|None, 'parts': [(ข้อความชิ้น, Std|None, optional)], 'clean': str, 'specialty': รหัสย่อ,
     'site': ส่วนของร่างกายจาก diagnosis, 'label': ชื่อที่ใช้นับสถิติ (หัตถการกว้างจะต่อท้ายด้วยตำแหน่ง)}
    ลำดับการคิด : สาขา >> แพทย์ >> หัตถการ (ดู diagnosis ร่วม) · main = ชิ้นที่ไม่ใช่ "อาจทำ" ที่ระดับสูงสุด เท่ากันเอาชิ้นแรก"""
    c = clean(raw)
    sp = specialty_key(specialty)
    dx = re.sub(r'\s+', ' ', str(diagnosis or '').upper()).strip()
    site = body_site(dx)

    def _out(main, parts):
        gen = main is not None and main.name in _GENERIC
        # ไม่รู้จัก : นับเป็น "หัตถการอื่นของสาขา" สถิติรายสาขาจะได้ครบ โดยไม่เดาชื่อ (มุกกี้สั่ง 21 พ.ย. 2026)
        # key = ชื่อแบบ ASCII ล้วน ใช้เป็นกุญแจ target encoding ของแบบจำลอง (เทรนกับตอนใช้งานต้องได้ค่าเดียวกัน)
        if main is not None:
            label = key = main.name
        elif _NONPROC.search(c):
            label, key = NOT_PROCEDURE, 'NOT_PROCEDURE'
        elif sp:
            label, key = 'หัตถการอื่นของ' + SPECIALTIES[sp], 'OTHER_' + sp
        else:
            label, key = 'ยังไม่จัดกลุ่ม', 'UNKNOWN'
        if gen and site:
            label = f'{label} : {site}'
            key = f'{key} @ {_SITE_EN[site]}'
        return {'main': main, 'parts': parts, 'clean': c, 'specialty': sp,
                'site': site, 'label': label, 'key': key}

    hit = SURGEON_RULES.get((sp, str(surgeon or '').strip(), c))
    if hit is not None:
        return _out(hit, [(c, hit, False)])
    marked = _OPT.sub(' + ?', c)                      # ชิ้นที่ตามหลัง +/- ขึ้นต้นด้วย ?
    parts = []
    for piece in _SPLIT.split(marked):
        piece = piece.strip()
        opt = piece.startswith('?')
        piece = piece.lstrip('? ').strip()
        if not piece:
            continue
        got = classify_component(piece, sp, c)
        if got is None:                                # 🔎 คำกำกวม : ดู diagnosis ประกอบ (มุกกี้สั่ง 21 พ.ย. 2026 22:08)
            got = _dx_component(piece, sp, dx, c)
        parts.append((piece, got, opt))
    known = [(p, s, o) for p, s, o in parts if s is not None]
    main = None
    if known:
        firm = [x for x in known if not x[2]] or known
        # EGD คู่กับ Colonoscopy ที่ถูกแยกชิ้น → นับเป็น EGD + Colonoscopy
        names = {s.name for _, s, _ in firm}
        if {'EGD', 'Colonoscopy'} <= names and max(s.level for _, s, _ in firm) == 1:
            main = Std('EGD + Colonoscopy', 'Endoscopy_GI', '45.23', 1)
        else:
            best = max(s.level for _, s, _ in firm)
            main = next(s for _, s, _ in firm if s.level == best)
    if main is None or main.name in _GENERIC:
        main = _by_diagnosis(c, main, site, dx, sp)
    if main is not None:
        main = _refine(main, c, dx, sp)                # 🔬 ชนิดย่อยที่ขนาดการผ่าตัดต่างกัน (รุ่น v4)
    return _out(main, parts)


def standard_name(raw, specialty=None, surgeon=None, diagnosis=None) -> str:
    """ชื่อที่ใช้นับสถิติ · หัตถการกว้างจะมีตำแหน่งจาก diagnosis ต่อท้าย เช่น 'Debridement : ขาและเท้า'"""
    return resolve(raw, specialty, surgeon, diagnosis)['label']


def all_standards():
    seen, out = set(), []
    for _, n, g, c, lv in _R:
        if n and n not in seen:
            seen.add(n)
            out.append(Std(n, g, c, lv))
    for n, g, c, lv in [('Excision of oral lesion', 'ENT', '27.49', 1),
                        ('Otoplasty (prominent ear)', 'ENT', '18.5', 2),
                        ('Nipple revision', 'Breast', '85.87', 1),
                        ('Lip revision', 'Skin_softtissue', '27.59', 1)]:
        seen.add(n)
        out.append(Std(n, g, c, lv))
    for rules in _SP.values():
        for _, _, n, g, c, lv in rules:
            if n not in seen:
                seen.add(n)
                out.append(Std(n, g, c, lv))
    return out


# ══════════════════════════════════════════════════════════════════════════
# 🧠 ส่วนเสริมสำหรับแบบจำลองรุ่น v4 (มุกกี้สั่ง 21 พ.ย. 2026 20:54 : ให้เฟเบิลจัดการเรื่อง procedure/operation เองเต็มที่)
#    ทุกอย่างในส่วนนี้คิดจาก "ข้อความที่พิมพ์ก่อนผ่าตัด" เท่านั้น (ชื่อหัตถการ + diagnosis ในตารางผ่าตัด)
#    หน้าสถิติไม่ได้ใช้ส่วนนี้ · แบบจำลองเรียก features() ทั้งตอนเทรนและตอนทำนาย จึงได้ค่าเดียวกันเสมอ
# ══════════════════════════════════════════════════════════════════════════

# ⏱ ค่าประมาณเวลาใช้ห้อง (นาที เข้าห้องถึงออกห้อง) ของหัตถการมาตรฐานแต่ละตัว "จากความรู้ทางคลินิกของเฟเบิล"
#    เขียนขึ้นโดยไม่ได้คำนวณจากข้อมูลของโรงพยาบาล (มี 45 ตัวที่เฟเบิลเคยเห็นค่ากลางจริงจากรายงานวิเคราะห์ก่อนเขียน
#    ดูรายชื่อใน train\processed\clinical_prior_check.csv) · ใช้เป็นตัวแปรช่วยสำหรับหัตถการที่มีเคสน้อย
CLINICAL_PRIOR_MIN = {
    'Anal fistula surgery (type unspecified)': 50, 'Anal fistulotomy / fistulectomy': 45,
    'Anal sphincteroplasty / stricturoplasty': 70, 'Hemorrhoidectomy': 50, 'LIFT (anal fistula)': 55,
    'Laser / RFA hemorrhoidoplasty': 40, 'Lateral internal sphincterotomy (LIS)': 35, 'Pilonidal sinus excision': 60,
    'Rectal prolapse repair': 120, 'Transanal excision': 75,
    'Eyelid surgery (blepharoplasty / ptosis)': 90, 'Axillary surgery (SLNB / ALND)': 90,
    'Breast implant / reconstruction': 180, 'Breast-conserving surgery (BCT / wide excision)': 110,
    'Excision of breast mass / VAE': 60, 'Mastectomy': 170, 'Nipple revision': 50, 'Reduction mammoplasty': 210,
    'Central line': 35, 'Chemoport insertion': 60, 'Chemoport removal': 35, 'DLC insertion': 30, 'DLC to TCC': 45,
    'Off TCC/DLC': 20, 'Revise TCC': 45, 'TCC insertion': 40,
    'Change DJ stent': 30, 'Change ureterostomy tube': 20, 'Cystogram': 25, 'Cystolitholapaxy': 70, 'Cystoscopy': 20,
    'DJ stent insertion': 35, 'Internal urethrotomy / TUI-BN': 40, 'Off DJ stent': 15,
    'Prostate biopsy (TRUS / MRI fusion)': 35, 'Rezum (water vapor therapy)': 30, 'Suprapubic cystostomy': 40,
    'TURBT': 65, 'TURP / HoLEP': 100, 'Ureteral catheterization': 30, 'Ureteroscopy (URS / URSL / RIRS)': 85,
    'Urethral dilation': 25, 'Retrograde pyelogram': 30,
    'Dacryocystorhinostomy (DCR)': 110, 'Direct laryngoscopy ± biopsy': 50, 'Endoscopic sinonasal tumor removal': 180,
    'Endoscopic sinus surgery (FESS / ESS)': 140, 'Excision of oral lesion': 55, 'Glossectomy': 150,
    'Lingual frenulectomy': 30, 'Mandibulectomy / maxillectomy': 360, 'Myringotomy ± PE tube': 35,
    'Otoplasty (prominent ear)': 120, 'Palatal surgery (UPPP / uvulectomy)': 100, 'Radiofrequency (nose / palate)': 40,
    'Rhinoplasty': 180, 'Salivary gland excision': 170, 'Septoplasty / turbinoplasty': 95,
    'Sphenopalatine artery ligation': 90, 'Tonsillectomy ± adenoidectomy': 80, 'Tympanoplasty / mastoidectomy': 200,
    'Colonic stent': 60, 'Colonoscopy': 40, 'EGD': 25, 'EGD + Colonoscopy': 55, 'ERCP': 70, 'Sigmoidoscopy': 25,
    'Facial bone osteotomy': 240, 'Fracture reduction / fixation': 110, 'Tendon repair': 90,
    'Closure of colostomy / ileostomy': 130, 'Colectomy (subtotal / total)': 280, 'Colostomy / ileostomy creation': 100,
    'Exploratory laparotomy': 180, 'Gastrectomy': 300, 'Gastrostomy': 70, 'Pelvic exenteration': 480,
    'Peritoneal window': 70, 'Rectal resection (AR / LAR / APR)': 330, 'Small bowel resection': 170, 'Splenectomy': 200,
    'Laparoscopic appendectomy': 110, 'Open appendectomy': 90, 'Laparoscopic hemicolectomy': 270, 'Open hemicolectomy': 240,
    'Laparoscopic sigmoidectomy': 270, 'Open sigmoidectomy': 240,
    'Laparoscopic inguinal hernia repair (TEP / TAPP)': 130, 'Open inguinal hernioplasty': 95,
    'Ventral / incisional hernia repair': 130,
    'Bile duct resection / hepaticojejunostomy': 360, 'Cholangiogram': 40, 'Laparoscopic cholecystectomy (LC)': 120,
    'Liver resection': 330, 'Open cholecystectomy': 150, 'Pancreatectomy': 330, 'Tumor ablation (MWA / RFA / IRE)': 90,
    'Whipple operation': 540,
    'Burr hole drainage': 90, 'Cranioplasty': 180, 'Craniotomy with microvascular decompression': 270,
    'Craniotomy with tumor removal': 330, 'Craniotomy / craniectomy (other)': 240,
    'Craniotomy / craniectomy with clot removal': 180, 'Endoscopic transsphenoidal tumor removal': 270,
    'External ventricular drainage (EVD)': 75, 'Temporal lobectomy': 360, 'VP shunt': 140,
    'Peripheral nerve block (pain management)': 30, 'Spinal injection (pain management)': 35,
    'Above-knee amputation (AKA)': 100, 'Amputation stump revision': 80, 'Below-knee amputation (BKA)': 105,
    'Chest drain insertion': 40, 'ECMO': 120, 'Off TK catheter': 50, 'Sympathectomy': 100, 'TK (Tenckhoff) catheter': 75,
    'Thoracic surgery (VATS / lung resection)': 210, 'Toe / ray amputation': 55,
    'Abdominoplasty / lipectomy': 240, 'Biopsy (excisional / incisional)': 45, 'Cheiloplasty': 120, 'Debridement': 60,
    'Excision of skin / soft-tissue lesion': 50, 'Face / brow lift': 240, 'Fasciotomy': 75, 'Flap coverage': 180,
    'Incision and drainage (I&D)': 40, 'Lip revision': 60, 'Lipofilling / fat graft': 120, 'Liposuction': 150,
    'Nail procedure': 30, 'Removal of foreign body / implant': 60, 'Scar revision': 60, 'Skin graft (STSG / FTSG)': 90,
    'VAC dressing': 50, 'Wide excision (skin / soft tissue)': 90, 'Wound exploration / stop bleeding': 80,
    'Wound irrigation / drainage': 50, 'Wound suture': 45,
    'ACDF': 190, 'Kyphoplasty / vertebroplasty': 80, 'Laminectomy / discectomy': 170,
    'Spinal decompression with fixation / fusion': 260,
    'Lymph node excision / biopsy': 55, 'Neck dissection': 240, 'Parathyroidectomy': 150,
    'TOETVA (transoral endoscopic thyroidectomy)': 210, 'Thyroid ablation (MWA / RFA)': 60, 'Thyroid lobectomy': 130,
    'Thyroidectomy (unspecified)': 150, 'Total thyroidectomy': 170,
    'Change tracheostomy tube': 20, 'Tracheostomy': 60,
    'Adrenalectomy': 210, 'Circumcision': 45, 'Cystectomy': 420, 'ESWL': 60, 'Excision of penile paraffinoma': 120,
    'Hydrocelectomy': 70, 'Hypospadias repair': 150, 'Kidney transplantation': 300, 'Meatotomy': 25, 'Nephrectomy': 240,
    'Nephrostomy (PCN)': 50, 'Orchiectomy': 65, 'Orchiopexy': 75, 'PCNL': 170, 'Penile augmentation / reconstruction': 120,
    'Prostate IRE (focal therapy)': 90, 'Pyeloplasty': 220, 'Radical prostatectomy': 300, 'Suburethral sling': 70,
    'Ureterolithotomy': 170, 'Urethroplasty': 210, 'Varicocelectomy': 80, 'Vasectomy': 35,
    'AVBG creation': 110, 'AVF creation': 70, 'AVF transposition / superficialization': 100,
    'Aneurysmectomy (AV access)': 120, 'Graft thrombectomy': 100, 'Ligate AVF/AVBG': 55, 'Remove AVBG': 100,
    'Revise AVBG': 100, 'Revise AVF': 90,
    'Angiogram / venogram': 60, 'Arterial bypass': 300, 'Balloon angioplasty / venoplasty (PTA)': 65,
    'Carotid artery stenting': 110, 'Carotid endarterectomy': 190, 'EVAR / TEVAR': 200, 'Embolization': 110,
    'Fistulogram': 50, 'IVC filter insertion': 50, 'IVC filter removal': 60, 'Thromboembolectomy': 150,
    'Varicose vein surgery': 100,
}

_NAN = float('nan')
_VERT = {**{f'C{i}': i for i in range(1, 8)}, **{f'T{i}': 7 + i for i in range(1, 13)},
         **{f'L{i}': 19 + i for i in range(1, 6)}, 'S1': 25, 'S2': 26}
_SPINE_CTX = re.compile(r'LAMIN|DIS[CK]|FUSION|\b[TPOAX]LIF\b|\bTILF\b|ACDF|ADCF|SPIN[EA]|SPONDYL|FIXATION|DECOMPRESS|'
                        r'KYPHO|VERTEBRO|SCREW|\bHNP\b|\bTPS\b|\bPDS\b|FORAMINO|CORPECT|LATERAL\s+MASS|STENOSIS')
_VRANGE = re.compile(r'\b([CTLS])\s?(\d{1,2})\s?[-–/]\s?([CTLS])?\s?(\d{1,2})(?:\s?[-–/]\s?([CTLS])?\s?(\d{1,2}))?')
_VSINGLE = re.compile(r'\b([CTL])\s?(\d{1,2})\b')


def spine_levels(proc: str, dx: str = '') -> int:
    """จำนวนระดับกระดูกสันหลังที่ทำ (ช่วงข้อต่อ) จากข้อความ เช่น L4-5 = 1 · L3-5 = 2 · C4-7 = 3 · L4-5, L5-S1 = 2
    อ่านเฉพาะเมื่อข้อความเป็นเรื่องกระดูกสันหลัง (S8 ของตับ, C4B ของหลอดเลือดดำ, L2 L3 ตำแหน่งก้อนเต้านม ไม่นับ)"""
    if not _SPINE_CTX.search(proc + ' ' + dx):
        return 0
    for t in (proc, dx):                      # ชื่อหัตถการก่อน ไม่มีระดับจึงดู diagnosis
        segs = set()
        for m in _VRANGE.finditer(t):
            i = _VERT.get(m.group(1) + m.group(2))
            ends = [((m.group(3) or m.group(1)), m.group(4))]
            if m.group(6):
                ends.append(((m.group(5) or m.group(3) or m.group(1)), m.group(6)))
            for reg, num in ends:
                j = _VERT.get(reg + num)
                if j is None or (i is not None and j <= i):
                    # พิมพ์ย่อข้ามช่วง เช่น L5-1 (= L5-S1) , C7-1 (= C7-T1)
                    j = _VERT.get({'C': 'T', 'T': 'L', 'L': 'S'}.get(m.group(1), '') + num)
                if i is not None and j is not None and 0 < j - i <= 10:
                    segs.update(range(i, j))
        if segs:
            return len(segs)
        m = re.search(r'(\d)\s*LEVELS?', t)
        if m:
            return int(m.group(1))
        if _VSINGLE.search(t):
            return 1
    return 0


_MOD = {k: re.compile(v) for k, v in {
    # ทำสองข้าง / ทำซ้ำ
    'bilat': r'\bBILAT\w*|\bBOTH\b|\bB\s*/\s*L\b|\bBIL\b|2\s*SIDES?|\b(?:RT|RIGHT)\.?\s*(?:\+|AND|&|,|/)\s*(?:LT|LEFT)\b'
             r'|\b(?:LT|LEFT)\.?\s*(?:\+|AND|&|,|/)\s*(?:RT|RIGHT)\b|\bU\s*\+\s*L\b',
    'redo': r'\bRE\s*-?\s*(?:DO|OPERAT\w*|EXPLOR\w*|EXCIS\w*|RESECT\w*|INSERT\w*|IMPLANT\w*|CORRECT\w*|FIX\w*|SUTUR\w*)'
            r'|\bREVIS\w*|\b2ND\b|SECOND\s+(?:LOOK|STAGE)|\bREDO\b',
    # วิธีเข้าทำ
    'lap': r'\bLAP\w*|\bTEP\b|\bTAPP\b|\bVATS\b|THORACOSCOP|\bLRP\b',
    'robot': r'ROBOT|\bRA[RL]P\b|DA\s*VINCI',
    'endo': r'ENDOSCOP|\bSCOPE\b|TELESCOP|SINUSCOP|\bFESS\b|\bESS\b',
    'open': r'\bOPEN\b',
    'micro': r'MICRO(?:SCOP|SURG|DIS[CK]|DECOMP|VASC)\w*|\bMICROSCOPE\b|\bCUSA\b',
    'navig': r'NAVIGAT|\bNIMS\b|NEUROMONITOR|\bIONM\b',
    'laser': r'LASER|\bCO2\b|\bEVLA\b|\bRFA\b|RADIOFREQ|MICROWAVE|\bMWA\b|ABLAT|CRYO|\bHIFU\b|COBLAT',
    # หัตถการพ่วงที่ทำให้เคสยาวขึ้น
    'frozen': r'FROZEN|\bF\s*/\s*S\b',
    'mesh': r'\bMESH\b',
    'stent': r'STENT',
    'biopsy': r'\bBX\b|BIOPSY|BIOSPY',
    'ln': r'\bSLNB?\b|SENTINEL|\bALND\b|AXILLARY\s+(?:LN|NODE|DISSECT)|\b[CMS]?R?ND\b|NECK\s+DISSECT|\bLND\b|\bPLND\b'
          r'|NODE\s+DISSECT|LYMPHADENECTOMY|\bTAD\b',
    'recon': r'\bFLAP\b|RECONSTRUCT|\bTRAM\b|\bDIEP\b|\bLD\b|EXPANDER|IMPLANT|PROSTHESIS|PROSTESIS|SILICONE|\bLICAP\b',
    'graft': r'GRAFT|\bSTSG\b|\bFTSG\b',
    'ioc': r'\bIOC\b|CHOLANGIOGRA|\bERCP\b|CBD\s+EXPLOR',
    'convert': r'CONVER[TS]|POSSIBLE|STAND\s*-?\s*BY|STANBY|\bPRN\b',
    'hipec': r'\bHIPEC\b|PERITONECTOMY|PERITONIECTOMY|DEBULK|EXENTERAT|EN\s*-?\s*BLOC|ENBLOC|ONBLOC',
    # ขอบเขตของการผ่าตัด
    'radical': r'RADICAL|EXTENDED|TOTAL|COMPLETE|COMPLETION|\bMRM\b|\bMRND\b',
    'partial': r'PARTIAL|SUBTOTAL|WEDGE|SEGMENT|\bHEMI\w*|SIMPLE|\bMINI\b|LOBECTOMY|LUMPECTOMY',
    # วิธีระงับความรู้สึกที่พิมพ์ติดมากับชื่อหัตถการ
    'ga': r'\bGA\b|GENERAL\s+AN|\bETT?\b|\bGAET\b|\bLMA\b|UNDERGA',
    'la': r'\bLA\b|\bLOCAL\b|\bMAC\b|SEDAT|\bTIVA\b',
    'block': r'SPINAL\s+BLOCK|\bSB\b|\bSA\b|\bBLOCK\b|\bBPB\b',
    'thai_note': r'[฀-๿]',
}.items()}
_MOD_DX = {k: re.compile(v) for k, v in {
    'bilat': r'\bBILAT\w*|\bBOTH\b|\bB\s*/\s*L\b|\bBIL\b',
    'ca': r'\bCA\b|\bCA\.|CARCINOMA|MALIGN|CANCER|SARCOMA|METASTA|\bMETS?\b|LYMPHOMA|MELANOMA|\bHCC\b|\bCCA\b|\bRCC\b'
          r'|\bGIST\b|NEOPLASM|\bNPC\b|GLIOMA|MENINGIOMA|ADENOMA|TUMOU?R',
    'recur': r'\bRECURR\w*|\bS\s*/\s*P\b|\bPOST\b|RESIDUAL|FAILED|\bSTATUS\b|\bPREVIOUS\b',
    'infect': r'ABSCESS|INFECT|GANGREN|NECRO|\bNF\b|PERFORAT|RUPTUR|PERITONITIS|OSTEOMYELITIS|CELLULITIS|EMPYEMA|SEPSIS',
    'trauma': r'FRACTURE|\bFX\b|#|INJUR|TRAUMA|LACERAT|\bBURN\b|GUNSHOT|\bGSW\b|STAB',
    'esrd': r'\bESRD\b|\bCKD\b|DIALYSIS|\bHD\b|\bCAPD\b|KIDNEY\s+DISEASE',
    'stone': r'STONE|CALCUL|\bUC\b|\bVC\b|\bRC\b|LITHIASIS',
    'big': r'\bHUGE\b|\bLARGE\b|\bGIANT\b|\bBIG\b|MASSIVE|ADVANCED?|LOCALLY',
    'complex': r'COMPLEX|COMPLICAT|MULTIPLE|MULTI\b|SEVERE|DIFFICULT|ADHESION',
}.items()}
_MULTI = re.compile(r'[X\*]\s?(\d)\b|\b(\d)\s*(?:SITES?|MASS(?:ES)?|LESIONS?|LEVELS?|POINTS?|ก้อน|ตำแหน่ง|จุด|ข้าง)')
_SIZE = re.compile(r'(\d{1,2}(?:\.\d)?)\s*(?:X\s*\d{1,2}(?:\.\d)?\s*)?CM\b')
_OPTIONAL = re.compile(r'\+\s*/\s*-|\+\s*-|±|\bOR\b')
MOD_NAMES = (['cx_' + k for k in _MOD] + ['cx_dx_' + k for k in _MOD_DX]
             + ['cx_spine_levels', 'cx_multi', 'cx_size_cm', 'cx_nopt', 'cx_nwords', 'cx_dx_nwords'])
PM_NUM = ['pm_level', 'pm_nparts', 'pm_level2', 'pm_nknown', 'pm_nopt', 'pm_prior', 'pm_prior_sum']


def _txt(v) -> str:
    return re.sub(r'\s+', ' ', '' if v is None or v != v else str(v)).upper().strip()


def modifiers(raw, diagnosis=None) -> dict:
    """ตัวบอกความซับซ้อนของเคส จากข้อความหัตถการและ diagnosis ที่พิมพ์ก่อนผ่าตัด (ความรู้ทางคลินิก ไม่ใช้เวลาจริง)
    คืน dict ตาม MOD_NAMES : 1/0 ของแต่ละลักษณะ + จำนวนระดับกระดูกสันหลัง จำนวนตำแหน่ง ขนาดก้อน (ซม.)"""
    p, d = _txt(raw), _txt(diagnosis)
    out = {'cx_' + k: int(bool(rx.search(p))) for k, rx in _MOD.items()}
    out.update({'cx_dx_' + k: int(bool(rx.search(d))) for k, rx in _MOD_DX.items()})
    out['cx_spine_levels'] = spine_levels(p, d)
    nums = [int(a or b) for a, b in _MULTI.findall(p + ' ' + d)]
    out['cx_multi'] = max(nums) if nums else (3 if 'MULTIPLE' in p + ' ' + d else 0)
    sizes = [float(x) for x in _SIZE.findall(p + ' ' + d)]
    out['cx_size_cm'] = max(sizes) if sizes else _NAN
    out['cx_nopt'] = len(_OPTIONAL.findall(p))
    out['cx_nwords'] = len(p.split())
    out['cx_dx_nwords'] = len(d.split())
    return out


def features(raw, specialty=None, diagnosis=None) -> dict:
    """ทุกค่าที่แบบจำลอง v4 ใช้จากชื่อหัตถการ : key + กลุ่ม + ระดับ + ค่าประมาณทางคลินิก + หัตถการรอง + ตัวบอกความซับซ้อน"""
    raw = '' if raw is None or raw != raw else raw
    diagnosis = '' if diagnosis is None or diagnosis != diagnosis else diagnosis
    r = resolve(raw, specialty, None, diagnosis)
    main = r['main']
    firm = [s for _, s, opt in r['parts'] if s is not None and not opt]
    rest = [s for s in firm if main is None or s.name != main.name]
    second = max(rest, key=lambda s: s.level) if rest else None
    pri = [x for x in (CLINICAL_PRIOR_MIN.get(n) for n in {s.name for s in firm}) if x]
    p_main = CLINICAL_PRIOR_MIN.get(main.name, _NAN) if main is not None else _NAN
    if p_main == p_main and p_main not in pri:
        pri.append(p_main)
    out = {
        'key': r['key'], 'group': main.group if main is not None else 'Other',
        'pm_level': main.level if main is not None else -1, 'pm_nparts': len(r['parts']),
        'pm_level2': second.level if second is not None else -1,
        'pm_nknown': len(firm), 'pm_nopt': sum(1 for _, _, opt in r['parts'] if opt),
        'pm_prior': p_main,
        # รวมเวลาของหัตถการพ่วง : ตัวที่ยาวสุดคิดเต็ม ตัวอื่นคิดครึ่งหนึ่ง (อยู่ในห้องเดียวกัน ดมยาครั้งเดียว)
        'pm_prior_sum': (max(pri) + 0.5 * (sum(pri) - max(pri))) if pri else _NAN,
        'key2': second.name if second is not None else 'NONE',
    }
    out.update(modifiers(raw, diagnosis))
    return out


# ══════════════════════════════════════════════════════════════════════════
# 🔤 ตัวแก้คำสะกดผิดทีละคำ (เฟเบิลเพิ่ม 21 พ.ย. 2026 สำหรับรุ่น v4 · มุกกี้ : "บางทีแพทย์ก็พิมพ์ผิด")
#    ไม่ใช่ fuzzy ทั้งประโยค : แก้เฉพาะ "คำ" ที่ยาว 6 ตัวอักษรขึ้นไปและไม่อยู่ในรายการคำศัพท์ ให้เป็นคำศัพท์หัตถการ
#    ที่ใกล้ที่สุด โดยต้องผ่านทุกข้อ (1) ตัวอักษรแรกเหมือนกัน (2) พิมพ์ผิดไม่เกิน 1 จุด (คำยาว 10 ตัวขึ้นไปให้ 2 จุด)
#    (3) มีคำที่เข้าเกณฑ์เพียงคำเดียว (4) ไม่ข้ามชนิดหัตถการ (-ECTOMY ตัดออก / -OSTOMY เปิดรู / -OTOMY ผ่า เป็นคนละอย่าง
#    เช่น GASTROTOMY จะไม่ถูกแก้เป็น GASTROSTOMY) (5) ไม่สลับท่อไต (URETER-) กับท่อปัสสาวะ (URETHR-)
#    ตรวจย้อนได้ : รายการคำที่ถูกแก้จริงในข้อมูลอยู่ที่ train\processed\spellfix_audit.csv
# ══════════════════════════════════════════════════════════════════════════
_VOCAB = frozenset('''
ABDOMINOPLASTY ADENOIDECTOMY ADRENALECTOMY AMPUTATION ANASTOMOSIS ANEURYSMECTOMY ANEURYSMORRHAPHY ANGIOGRAM
ANGIOGRAPHY ANGIOPLASTY APPENDECTOMY ATTICOTOMY AUGMENTATION BIOPSY BLEPHAROPLASTY BRONCHOSCOPY CANALOPLASTY
CAPSULECTOMY CATHETERIZATION CHEILOPLASTY CHEMOPORT CHOLANGIOGRAM CHOLECYSTECTOMY CHOLECYSTOSTOMY CIRCUMCISION
CLOSURE COLECTOMY COLONOSCOPY COLOSTOMY COLOTOMY CRANIECTOMY CRANIOPLASTY CRANIOTOMY CYSTECTOMY CYSTOLITHOLAPAXY
CYSTOSCOPY CYSTOSTOMY CYSTOTOMY DEBRIDEMENT DECOMPRESSION DECORTICATION DILATATION DILATION DISCECTOMY DISSECTION
DRAINAGE EMBOLIZATION ENDARTERECTOMY EPIDIDYMECTOMY ESOPHAGECTOMY EXCISION EXENTERATION EXPLORATION FASCIOTOMY
FISTULECTOMY FISTULOGRAM FISTULOTOMY FIXATION FRENULECTOMY FRENULOPLASTY GANGLIONECTOMY GASTRECTOMY
GASTROJEJUNOSTOMY GASTROSTOMY GASTROTOMY GLOSSECTOMY HEMICOLECTOMY HEMORRHOID HEMORRHOIDECTOMY HEMORRHOIDOPLASTY
HEPATECTOMY HEPATICOJEJUNOSTOMY HERNIOPLASTY HERNIORRHAPHY HYDROCELECTOMY HYSTERECTOMY ILEOSTOMY INSERTION
JEJUNOSTOMY KYPHOPLASTY LAMINECTOMY LAMINOTOMY LAPAROSCOPIC LAPAROTOMY LARYNGECTOMY LARYNGOSCOPY LIGATION
LIPOSUCTION LITHOTRIPSY LOBECTOMY LUMPECTOMY LYMPHADENECTOMY MAMMOPLASTY MANDIBULECTOMY MARSUPIALIZATION
MASTECTOMY MASTOIDECTOMY MAXILLECTOMY MEATOPLASTY MEATOTOMY MICRODISCECTOMY MICROWAVE MYRINGOTOMY NEPHRECTOMY
NEPHROLITHOTOMY NEPHROSTOMY OOPHORECTOMY ORCHIECTOMY ORCHIOPEXY OSSICULOPLASTY OTOPLASTY PALATOPLASTY
PANCREATECTOMY PARAFFINOMA PARATHYROIDECTOMY PAROTIDECTOMY PENECTOMY POLYPECTOMY PROSTATECTOMY PYELOLITHOTOMY
PYELOPLASTY RECONSTRUCTION RECTOPEXY REDUCTION REMOVAL REPAIR RESECTION REVISION RHINOPLASTY SCLEROTHERAPY
SEPTOPLASTY SIGMOIDECTOMY SIGMOIDOSCOPY SPHINCTEROPLASTY SPHINCTEROTOMY SPLENECTOMY STRICTUROPLASTY
SUPERFICIALIZATION SUTURE SYMPATHECTOMY SYNOVECTOMY THORACOSCOPY THORACOTOMY THROMBECTOMY THYMECTOMY
THYROIDECTOMY TONSILLECTOMY TRACHEOSTOMY TRANSPOSITION TURBINOPLASTY TYMPANOPLASTY URETERAL URETERECTOMY
URETERIC URETEROLITHOTOMY URETEROSCOPY URETEROSTOMY URETEROTOMY URETHRAL URETHRECTOMY URETHROPLASTY
URETHROSCOPY URETHROSTOMY URETHROTOMY VARICOCELECTOMY VASECTOMY VENOPLASTY VERTEBROPLASTY
CORPECTOMY CORDECTOMY METASTASECTOMY IRRIGATION EXCISIONAL INCISIONAL INCISION INJECTION INFECTION URETHRA
VULVECTOMY VAGOTOMY PHLEBECTOMY EMBOLECTOMY THROMBOLYSIS TURBINECTOMY URETEROLYSIS ADHESIOLYSIS SALPINGECTOMY
OMENTECTOMY PERITONECTOMY LARYNGOPLASTY CYSTOPLASTY SIALADENECTOMY ISTHMUSECTOMY URETEROURETEROSTOMY
VASOVASOSTOMY LESIONECTOMY FORAMINOTOMY CORRECTION COLLECTION OPERATION EXAMINATION CAUTERIZATION
'''.split())
# คำที่เกณฑ์ข้างบนแก้ไม่ถึง (สั้นเกิน หรือผิดหลายจุด) : ระบุตรง ๆ ทีละคำ
_SPELL_MAP = {
    'EXSION': 'EXCISION', 'EXCIIOSN': 'EXCISION', 'EACISION': 'EXCISION', 'ERPC': 'ERCP', 'ADCF': 'ACDF',
    'AFV': 'AVF', 'TILF': 'TLIF', 'TOTEVA': 'TOETVA', 'TOEVTA': 'TOETVA', 'TOEPVA': 'TOEPVA',
    'TANKOFF': 'TENCKHOFF', 'TENKOFF': 'TENCKHOFF', 'TENKHOFF': 'TENCKHOFF',
    'HAEMORRHOID': 'HEMORRHOID', 'HAEMORRHOIDECTOMY': 'HEMORRHOIDECTOMY', 'HAEMORRHOIDOPLASTY': 'HEMORRHOIDOPLASTY',
    'CYTO': 'CYSTO', 'CSYTO': 'CYSTO', 'LASEER': 'LASER', 'LASOR': 'LASER', 'LAASER': 'LASER',
    'DRAINGE': 'DRAINAGE', 'DRAINGAE': 'DRAINAGE', 'DRAINANGE': 'DRAINAGE',
    'BIOSY': 'BIOPSY', 'BIOIPSY': 'BIOPSY', 'BIOSPY': 'BIOPSY', 'BISOPSY': 'BIOPSY',
    'CRCHIECTOMY': 'ORCHIECTOMY', 'OCHIECTOMY': 'ORCHIECTOMY', 'ORCHIDECTOMY': 'ORCHIECTOMY',
    'GOIN': 'GROIN', 'PARRRAFINIOMA': 'PARAFFINOMA', 'PARAFINOMA': 'PARAFFINOMA', 'STST': 'STSG', 'STSTG': 'STSG',
    'FACELIFE': 'FACELIFT', 'BASILLIC': 'BASILIC', 'TRACHEOTOMY': 'TRACHEOSTOMY', 'TRACHESOTMY': 'TRACHEOSTOMY',
    'CHOMEPORT': 'CHEMOPORT', 'CHEMMORPORT': 'CHEMOPORT', 'KARIDAKIS': 'KARYDAKIS', 'KARYDAKYS': 'KARYDAKIS',
    'ALTEMIERE': 'ALTEMEIER', 'ALTIMIER': 'ALTEMEIER', 'HARTMAN': 'HARTMANN', 'ILIOSTOMY': 'ILEOSTOMY',
    'URETHERAL': 'URETHRAL', 'URATHRAL': 'URETHRAL', 'URETHTAL': 'URETHRAL', 'UREHRAL': 'URETHRAL',
    'MICRODICHECTOMY': 'MICRODOCHECTOMY', 'ENDOTIDE': 'ENDOTINE',
    'FISULOMY': 'FISTULOTOMY', 'WEDEG': 'WEDGE', 'UMBILLICOPLASTY': 'UMBILICOPLASTY',
    'METASTECTOMY': 'METASTASECTOMY', 'LRRIGATION': 'IRRIGATION', 'PERITONIECTOMY': 'PERITONECTOMY',
}
_SUFFIX = ('ECTOMY', 'OSTOMY', 'OTOMY', 'PLASTY', 'PEXY', 'SCOPY', 'SCOPIC', 'GRAPHY', 'RRHAPHY', 'GRAM',
           'LYSIS', 'DESIS', 'TRIPSY', 'LAPAXY')
_VOCAB_BY_INITIAL: dict = {}
for _w in _VOCAB:
    _VOCAB_BY_INITIAL.setdefault(_w[0], []).append(_w)
_SPELL_CACHE: dict = {}


def _suffix_class(w: str) -> str:
    for s in _SUFFIX:
        if w.endswith(s):
            return s
    return ''


def _edit_distance(a: str, b: str, cap: int = 2) -> int:
    """ระยะแก้คำแบบ Damerau (เพิ่ม ลบ แทน สลับตัวติดกัน) หยุดเมื่อเกิน cap"""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[-1]


def fix_word(w: str) -> str:
    """คำเดียว (ตัวใหญ่ล้วน) → คำที่แก้แล้ว หรือคำเดิมถ้าไม่เข้าเกณฑ์"""
    got = _SPELL_CACHE.get(w)
    if got is not None:
        return got
    out = _SPELL_MAP.get(w, w)
    if out == w and len(w) >= 6 and w not in _VOCAB:
        cap = 2 if len(w) >= 10 else 1
        best, tie = None, False
        for v in _VOCAB_BY_INITIAL.get(w[0], ()):
            dist = _edit_distance(w, v, cap)
            if dist > cap:
                continue
            sw, sv = _suffix_class(w), _suffix_class(v)
            if sw and sv and sw != sv:
                continue                                  # คนละชนิดหัตถการ ไม่แก้
            if ('URETHR' in w) != ('URETHR' in v) and ('URETER' in w or 'URETER' in v or 'URETHR' in w):
                continue                                  # ท่อไต กับ ท่อปัสสาวะ ไม่สลับกัน
            if best is None or dist < best[0]:
                best, tie = (dist, v), False
            elif dist == best[0] and v != best[1]:
                tie = True
        if best is not None and not tie:
            out = best[1]
    _SPELL_CACHE[w] = out
    return out


def spellfix(text) -> str:
    """ข้อความหัตถการ (ตัวใหญ่) → ข้อความที่แก้คำสะกดผิดแล้ว"""
    return re.sub(r'[A-Z]{3,}', lambda m: fix_word(m.group(0)), str(text or ''))


# ══════════════════════════════════════════════════════════════════════════
# 🩺 หัตถการมาตรฐานเพิ่มเติม + กติกาชั้นสุดท้าย (เฟเบิลเพิ่ม 21 พ.ย. 2026 สำหรับรุ่น v4)
#    มาจากการไล่คำที่ยังจัดไม่ได้ 545 เคสของช่วงเทรน (ก่อน 1 ก.ค. 2569) ด้วยความรู้ทางคลินิก
#    กติกาชุดนี้ถูกดู "หลังสุด" เฉพาะชิ้นที่กติกาเดิมจัดไม่ได้ จึงไม่ทับการจัดเดิมที่มุกกี้ตรวจแล้ว
#    ⚠️ รหัส ICD-9-CM ของหัตถการใหม่ในส่วนนี้ เฟเบิลใส่จากความรู้ ยังไม่ได้เทียบกับรายการ CMS ทีละรหัส
# ══════════════════════════════════════════════════════════════════════════
# ชื่อ : (กลุ่ม, ICD-9-CM, ระดับ, ค่าประมาณเวลาใช้ห้องทางคลินิก นาที)
_NEW_STD = {
    'Anal dilatation': ('Anorectal', '96.23', 1, 30),
    'Examination under anesthesia (anorectal)': ('Anorectal', '89.34', 0, 30),
    'Hartmann reversal': ('GI_abdominal', '46.52', 3, 240),
    'Enterocutaneous fistula repair': ('GI_abdominal', '46.74', 3, 200),
    'Intra-abdominal tumor resection / debulking': ('GI_abdominal', '54.4', 4, 360),
    'Diagnostic laparoscopy / adhesiolysis': ('GI_abdominal', '54.21', 2, 120),
    'Gastrointestinal bypass (gastrojejunostomy / enteroenterostomy)': ('GI_abdominal', '44.39', 3, 200),
    'Esophagectomy': ('GI_abdominal', '42.41', 4, 480),
    'Gastric wedge resection': ('GI_abdominal', '43.42', 3, 160),
    'Oophorectomy / salpingo-oophorectomy': ('GI_abdominal', '65.61', 2, 130),
    'Electrocautery of wart / skin lesion': ('Skin_softtissue', '86.3', 1, 35),
    'Wound dressing under anesthesia': ('Skin_softtissue', '93.57', 0, 40),
    'Excision of bone lesion': ('Skin_softtissue', '77.60', 2, 90),
    'Nerve exploration / repair': ('Skin_softtissue', '04.04', 3, 180),
    'Inguinal lymph node dissection': ('Skin_softtissue', '40.54', 3, 180),
    'Gynecomastia correction': ('Breast', '85.36', 2, 120),
    'Breast lesion ablation (cryoablation / HIFU)': ('Breast', '85.20', 1, 60),
    'Antegrade pyelogram (via nephrostomy)': ('Cystoscopy_URO', '87.75', 0, 30),
    'Endoscopic orbital decompression': ('ENT', '16.09', 3, 180),
    'Tracheocutaneous fistula closure': ('Tracheostomy', '31.72', 1, 60),
    'Laryngectomy': ('ENT', '30.3', 4, 420),
    'Temporal bone resection': ('ENT', '20.59', 4, 420),
    'Nasal endoscopy ± cautery': ('ENT', '21.03', 1, 45),
    'Cleft palate repair': ('ENT', '27.62', 3, 150),
    'Sistrunk operation (thyroglossal duct cyst)': ('Thyroid_neck', '06.7', 2, 120),
    'Vesicovaginal fistula repair': ('Uro_other', '57.84', 3, 180),
    'Scrotal surgery (epididymectomy / spermatocelectomy)': ('Uro_other', '63.4', 1, 70),
    'Ureteral reconstruction (ureteroureterostomy / reimplantation)': ('Uro_other', '56.75', 3, 220),
    'Penectomy': ('Uro_other', '64.3', 3, 150),
    'Urethrectomy': ('Uro_other', '58.39', 3, 150),
    'Vasovasostomy': ('Uro_other', '63.82', 3, 180),
    'Arterial repair / aneurysmorrhaphy': ('Vascular_interv', '39.31', 3, 150),
    'Open AAA repair': ('Vascular_interv', '38.44', 4, 360),
    'Endovascular stenting (arterial / venous)': ('Vascular_interv', '39.90', 2, 150),
}
CLINICAL_PRIOR_MIN.update({k: v[3] for k, v in _NEW_STD.items()})
_APPROACH_STD = {
    'Open appendectomy': ('GI_abdominal', '47.09', 2), 'Open inguinal hernioplasty': ('GI_abdominal', '53.05', 2),
    'Craniotomy / craniectomy (other)': ('Neuro_cranial', '01.24', 4),
    'Craniotomy / craniectomy with clot removal': ('Neuro_cranial', '01.24', 4),
    'Craniotomy with tumor removal': ('Neuro_cranial', '01.59', 4),
}
_STD_INDEX: dict = {}


def _std(name: str) -> Std:
    """หัตถการมาตรฐานตามชื่อ (ของเดิมจากกติกา + ของใหม่ในส่วนนี้)"""
    if not _STD_INDEX:
        for s0 in _all_standards_base():
            _STD_INDEX.setdefault(s0.name, s0)
        for n, g, c, lv in [('Excision of breast mass / VAE', 'Breast', '85.21', 1),
                            ('Breast-conserving surgery (BCT / wide excision)', 'Breast', '85.21', 2)]:
            _STD_INDEX.setdefault(n, Std(n, g, c, lv))
        for _, n, g, c, lv in _R:
            if n:
                _STD_INDEX.setdefault(n, Std(n, g, c, lv))
        for rules in _SP.values():
            for _, _, n, g, c, lv in rules:
                _STD_INDEX.setdefault(n, Std(n, g, c, lv))
        for n, (g, c, lv) in _APPROACH_STD.items():
            _STD_INDEX.setdefault(n, Std(n, g, c, lv))
        for n, g, c, lv in [('Scar revision', 'Skin_softtissue', '86.84', 1), ('Rhinoplasty', 'ENT', '21.87', 3),
                            ('Nipple revision', 'Breast', '85.87', 1), ('Lip revision', 'Skin_softtissue', '27.59', 1),
                            ('Eyelid surgery (blepharoplasty / ptosis)', 'Blepharoplasty', '08.38', 2)]:
            _STD_INDEX.setdefault(n, Std(n, g, c, lv))
        for n, (g, c, lv, _) in _NEW_STD.items():
            _STD_INDEX[n] = Std(n, g, c, lv)
    return _STD_INDEX[name]


_all_standards_base = all_standards


def all_standards():                                   # noqa: F811  (ต่อของใหม่ท้ายรายการเดิม)
    out = _all_standards_base()
    have = {s.name for s in out}
    return out + [Std(n, g, c, lv) for n, (g, c, lv, _) in _NEW_STD.items() if n not in have]


_A = None                                               # ทุกสาขา
# (สาขาที่ใช้กติกานี้ หรือ None = ทุกสาขา, รูปแบบของชิ้น, ชื่อหัตถการมาตรฐาน) · ดูตามลำดับ ตัวแรกที่ตรงชนะ
_R2_RAW = [
    (_A, r'ELECTROCAUT\w*|ELECTRODIS\w*|ELECTRO\s*COAG\w*', 'Electrocautery of wart / skin lesion'),
    ({'CRS', 'GEN', 'HPB', 'URO'}, r'EN\s*-?\s*BLOC|ENBLOC|ONBLOC|DEBULK\w*|\bHIPEC\b|PERITON\w*ECTOMY|METASTASECTOMY'
     r'|RETROPERITONEAL\s+(MASS|TUMOU?R)', 'Intra-abdominal tumor resection / debulking'),
    ({'CRS'}, r'^TUMOU?R\s+(REMOVAL|RESECTION)', 'Intra-abdominal tumor resection / debulking'),
    (_A, r'(CLOS\w*|REVERS\w*|TAKE\s*DOWN)\s+(OF\s+)?HARTMANN', 'Hartmann reversal'),
    ({'ENT'}, r'CLOS\w*\s*(OF\s+)?(FISTULA|TEF)|CLOSURETEF', 'Tracheocutaneous fistula closure'),
    ({'URO'}, r'FISTULA\s+REPAIR\w*|REPAIR\w*\s+.*FISTULA', 'Vesicovaginal fistula repair'),
    (_A, r'CLOS\w*\s+(OF\s+)?FISTULA|FISTULA\s+CLOSURE', 'Enterocutaneous fistula repair'),
    ({'CRS', 'GEN'}, r'ANAL\s+FISTULA|FISTULA\s+SURGERY|\bFIA\b|LASER\s+FISTULA',
     'Anal fistula surgery (type unspecified)'),
    (_A, r'ANAL\s+DILAT\w*|DILAT\w*\s+(ANAL|ANASTOMOSIS)', 'Anal dilatation'),
    ({'CRS', 'GEN'}, r'^EUA\b', 'Examination under anesthesia (anorectal)'),
    (_A, r'KARYDAKIS|PILONIDAL', 'Pilonidal sinus excision'),
    (_A, r'LEVATOPLASTY|MUCOSECTOMY|ALTEMEIER', 'Rectal prolapse repair'),
    (_A, r'DIAGNOS\w+\s+LAP\w*|LAP\w*\s+DIAGNOS\w*|LYSIS\s+ADHESION|ADHESIOLYSIS', 'Diagnostic laparoscopy / adhesiolysis'),
    (_A, r'\bSTC\b', 'Colectomy (subtotal / total)'),
    ({'CRS', 'GEN'}, r'REVIS\w*\s+OSTOMY|OSTOMY\s+REVIS\w*', 'Colostomy / ileostomy creation'),
    (_A, r'ABDOM\w*\s+(CLOSURE|TOILET)|CLOSURE\s+ABDOM\w*|TEMPORARY\s+CLOSURE|2ND\s+LOOK|SECOND\s+LOOK|OFF\s+PACKING'
     r'|SURGICAL\s+DECOMPRESSION|EXPLORE?\s*LAP', 'Exploratory laparotomy'),
    ({'NEU'}, r'LATERAL\s+MASS|\bSCREWS?\b|\bRODS?\b|\bTLIF\b|\bTPL\b', 'Spinal decompression with fixation / fusion'),
    ({'NEU'}, r'MICRO\s*DIS[CK]\w*|MICROSCOPIC\s+DIS[CK]\w*|ENDO\w*\s*DIS[CK]\w*|MICRO\s*DECOMP\w*|ENDOSCOPIC\s+DECOMP\w*'
     r'|FORAMINOTOMY|LAMINOTOMY|DECOMPRESS\w*\s+([LTC]\d|ROOT)|[LTC]\d\s*[/-]\s*[LTCS]?\d\s+DECOMPRESS\w*',
     'Laminectomy / discectomy'),
    ({'NEU'}, r'LESIONECTOMY', 'Craniotomy with tumor removal'),
    ({'NEU'}, r'RE\s*-?\s*EXPLOR\w*|CHIARI|ABSCESS\s+RESECTION', 'Craniotomy / craniectomy (other)'),
    ({'NEU'}, r'SKULL\s+DEFECT', 'Cranioplasty'),
    ({'GEN', 'CRS', 'HPB', 'VAS'}, r'RE\s*-?\s*EXPLOR\w*', 'Exploratory laparotomy'),
    (_A, r'\bBCS\b', 'Breast-conserving surgery (BCT / wide excision)'),
    (_A, r'\bSSO\b|OOPHORECTOMY|SALPING\w+', 'Oophorectomy / salpingo-oophorectomy'),
    (_A, r'\bMRND\b|\bCND\b|\bSND\b|\bRND\b', 'Neck dissection'),
    (_A, r'JEJUNOJ\w+STOMY|GASTROJEJUNOSTOMY|^GJ$|BRAUN', 'Gastrointestinal bypass (gastrojejunostomy / enteroenterostomy)'),
    (_A, r'JEJUNOSTOMY|GASTROTOMY', 'Gastrostomy'),
    (_A, r'STUMP', 'Amputation stump revision'),                      # มุกกี้เคาะ 21 พ.ย. 2026 22:08 : ถูกต้อง
    (_A, r'GYNECOMASTIA', 'Gynecomastia correction'),
    (_A, r'CRYOABLA\w*', 'Breast lesion ablation (cryoablation / HIFU)'),
    (_A, r'DRESSING|WOUND\s+(DRESS\w*|EVALUATION)|STSG\s+EVALUATION', 'Wound dressing under anesthesia'),
    (_A, r'EVACUAT\w*\s+HEMATOMA', 'Wound exploration / stop bleeding'),
    (_A, r'EXPANDER|CAPSULECTOMY|PRO\w*THESIS|PROSTESIS|SILICONE\s+REMOVAL\s+.*BREAST|REVISION\s+OF\s+.*BREAST',
     'Breast implant / reconstruction'),
    (_A, r'ESOPHAGECTOMY', 'Esophagectomy'),
    (_A, r'FUNDOPLIC\w*|NISSEN|HIATAL', 'Fundoplication / hiatal hernia repair'),
    (_A, r'WEDGE\s+(TUMOU?R\s+RESECTION|STOMACH|GASTR\w*)|GASTRIC\s+WEDGE', 'Gastric wedge resection'),
    (_A, r'SMALL\s+BOWEL\s+.*RESECTION', 'Small bowel resection'),
    (_A, r'\bTOEPVA\b', 'Parathyroidectomy'),
    (_A, r'MICRODOCHECTOMY|\bVACNB\b|ACCES+ORY\s+BREAST|CLIP\s+PLACEMENT', 'Excision of breast mass / VAE'),
    (_A, r'\bTAD\b', 'Axillary surgery (SLNB / ALND)'),
    ({'VAS'}, r'^CAPD$', 'TK (Tenckhoff) catheter'),
    (_A, r'LIVER\s+.*RESECTION|\bS\d[AB]?\b.*(RESECTION|WEDGE)|WEDGE\s+.*\bS\d|SEGMENT\w*\s+\d\s+RESECTION', 'Liver resection'),
    (_A, r'ISTHMUSECTOM\w*', 'Thyroid lobectomy'),
    ({'GEN', 'HPB'}, r'^(OPEN\s+|LAP\w*\s+)?PD$', 'Whipple operation'),
    (_A, r'PELVIC\s+EXEN', 'Pelvic exenteration'),
    (_A, r'FOREIGN\s+BODY|REMOV\w*\s+(OF\s+)?(BULLET|SILIC\w+|IMPLANT|PLATE|SKULL\s+PLATE|STAPLE|MESH)'
     r'|(SILIC\w+|IMPLANT|PLATE|STAPLE|MESH)\s+(REMOVAL|TRIMMING)', 'Removal of foreign body / implant'),
    (_A, r'AORT\w+\s+ANEURYSM\w*|\bAAA\b|ANEURYSMORRHAPHY\s+(USING|WITH)\s+.*GRAFT', 'Open AAA repair'),
    ({'VAS'}, r'ANEURYSMORRHAPHY', 'Aneurysmectomy (AV access)'),
    (_A, r'REPAIR\s+(\w+\s+)?(ARTERY|ANEURYSM|RADIAL|ULNAR|BRACHIAL)', 'Arterial repair / aneurysmorrhaphy'),
    ({'VAS'}, r'ANGIOGRAPHY|AORTOGRAPHY|VENOGRAPHY|ARTERIOGRAPHY', 'Angiogram / venogram'),
    ({'VAS'}, r'CH\s*-?\s*EVAR|\bFEVAR\b', 'EVAR / TEVAR'),
    ({'VAS'}, r'STENT\w*|\bCERAB\b|RELINING', 'Endovascular stenting (arterial / venous)'),
    ({'VAS'}, r'BANDING', 'Revise AVF'),
    ({'VAS'}, r'TRANSPOSITION|SUPERFICIALIZATION|TURN\s*-?\s*DOWN', 'AVF transposition / superficialization'),
    ({'VAS'}, r'LASER\s+ABLATION|\b[GS]SV\b|SCLEROTHERAPY', 'Varicose vein surgery'),
    ({'VAS'}, r'^LIGATE\b', 'Ligate AVF/AVBG'),
    (_A, r'BY\s*-?\s*PASS', 'Arterial bypass'),
    ({'VAS'}, r'\bPTFE\b|GRAFT\s+INTERPOSITION', 'AVBG creation'),
    (_A, r'REVISE?\s*(TCC|TVV)', 'Revise TCC'),
    (_A, r'HICKMAN\w*|TCCAT|TCCC', 'TCC insertion'),
    (_A, r'\bPORT\s+INSERT\w*|\bCMT\s+INSERT\w*', 'Chemoport insertion'),
    (_A, r'PERITON\w+\s+WINDOW', 'Peritoneal window'),
    (_A, r'ARTERIOVENOSTOMY', 'AVF creation'),
    ({'ENT'}, r'CANALOPLASTY|ATTICOTOMY|OSSICULOPLASTY|MIDDLE\s+EAR|\bMRMD\b|FACIAL\s+NERVE\s+DECOMP\w*',
     'Tympanoplasty / mastoidectomy'),
    (_A, r'TEMPORAL\s+BONE\s+RESECTION', 'Temporal bone resection'),
    (_A, r'LARYNGECTOMY', 'Laryngectomy'),
    ({'ENT'}, r'^D\s*/\s*L\b|DIAGNOSTIC\s+PROCEDURES\s+ON\s+(LARYNX|TRACHEA|ESOPHAGUS)|CORDECTOMY|TRACHEOSCOPY',
     'Direct laryngoscopy ± biopsy'),
    # ผ่าลดความดันเบ้าตาทางกล้อง (diagnosis : dysthyroid optic neuropathy) ไม่ใช่การตัดเนื้องอก
    ({'ENT'}, r'ORBITAL\s+DECOMP\w*', 'Endoscopic orbital decompression'),
    ({'ENT'}, r'ENDOSCOPIC\s+(MEDIAL|TUMOU?R|REMOV\w*|MARSUP\w*|REVIS\w*)|REVISION\s+SX',
     'Endoscopic sinonasal tumor removal'),
    ({'ENT'}, r'\bEMMM\b|OPERATIONS?\s+ON\s+NASAL\s+SINUS\w*', 'Endoscopic sinus surgery (FESS / ESS)'),
    ({'ENT'}, r'NASAL\s+TELE\w*|SYNE\w*CHIAE|EPISTAXIS', 'Nasal endoscopy ± cautery'),
    (_A, r'GROMMET|MYRINGOSCOP\w*', 'Myringotomy ± PE tube'),
    (_A, r'NASAL\s+VALVE', 'Rhinoplasty'),
    (_A, r'SAUCERIZATION', 'Excision of oral lesion'),
    (_A, r'ADENOID', 'Tonsillectomy ± adenoidectomy'),
    (_A, r'SISTRUNK', 'Sistrunk operation (thyroglossal duct cyst)'),
    ({'ENT'}, r'STOMA\w*\s+REVISION', 'Tracheostomy'),
    ({'PLA'}, r'PALATOPLASTY', 'Cleft palate repair'),
    (_A, r'PALATOPLASTY', 'Palatal surgery (UPPP / uvulectomy)'),
    (_A, r'ENDOTINE|EYEBROW\s*PLASTY|BROW\s*PLASTY|MINI\s+FACE|FACE\s*LIFT?\w*', 'Face / brow lift'),
    (_A, r'LIP\s+REVISION|REVISION\s+.*LIP|CORRECT\w*\s+.*LIP', 'Lip revision'),
    (_A, r'REDUCTION\s+.*NASAL|NASAL\s+.*REDUCTION|OPEN\s+REDUCTION', 'Fracture reduction / fixation'),
    (_A, r'OSTEOMA|BONE\s+RESECTION|SKULL\s+DRILLING|BURRING|BONE\s+GRAFT', 'Excision of bone lesion'),
    ({'PLA'}, r'^OSTOMY$', 'Excision of bone lesion'),                # มุกกี้ชี้ 21 พ.ย. 2026 22:08 : กระดูกงอกมาตัดออก (diagnosis : osteoma)
    (_A, r'KELOID|UMBILICOPLASTY', 'Scar revision'),
    (_A, r'\bBLEP\b', 'Eyelid surgery (blepharoplasty / ptosis)'),
    (_A, r'PAROTID', 'Salivary gland excision'),
    (_A, r'DIS[CK]ECTOMY', 'Laminectomy / discectomy'),
    (_A, r'NERVE\s+(EXPLOR\w*|REPAIR)|REPAIR\s+.*NERVE', 'Nerve exploration / repair'),
    (_A, r'(GROIN|INGUINAL)\s+(NODE|LN)\s+DISSECTION', 'Inguinal lymph node dissection'),
    (_A, r'SKIN\s*GRAFT|\bSTSG\b', 'Skin graft (STSG / FTSG)'),
    (_A, r'(WOUND|SKIN)\s+CLOSURE|REPAIR\s+LOBULE', 'Wound suture'),
    (_A, r'REVISION\s+NAC|\bNAC\s+REVISION', 'Nipple revision'),
    # AP = antegrade pyelogram ฉีดสีผ่านสาย PCN (ดู diagnosis แล้ว : PCN malfunction / S/P PCN) คู่กับ RP ที่มุกกี้ชี้ไว้
    ({'URO'}, r'^AP$|ANTEGRADE\s+(PYELO|NEPHROSTO)\w*', 'Antegrade pyelogram (via nephrostomy)'),
    ({'URO'}, r'STENT\s+REMOVAL|OFF\s+(\w+\s+)?STENT', 'Off DJ stent'),
    ({'URO'}, r'CHANG\s*E\s+D+J', 'Change DJ stent'),
    ({'URO'}, r'\bCYSTO\b', 'Cystoscopy'),
    ({'URO'}, r'TIE\s*MAN|URETHRAL\s+DILAT\w*', 'Urethral dilation'),
    ({'URO'}, r'URETER\w*\s+(TUBE\s+)?EXCHANG\w*|EXCHANG\w*\s+.*URETER\w+\s+TUBE', 'Change ureterostomy tube'),
    ({'URO'}, r'U\s*-?\s*CATH\w*|URETERIC\s+CATH\w*', 'Ureteral catheterization'),
    (_A, r'PYELOLITHOTOMY', 'Ureterolithotomy'),                      # มุกกี้เคาะ 21 พ.ย. 2026 22:08 : รวมได้
    ({'URO'}, r'LASER\s+(VC|LITHO\w*|URETHRAL\s+STONE)|URETHROLITHOTRIPSY', 'Cystolitholapaxy'),
    ({'URO'}, r'EPIDIDYMECTOMY|SPERMATOCEL\w*|SCROTAL|CYSTIC\s+REMOVAL', 'Scrotal surgery (epididymectomy / spermatocelectomy)'),
    (_A, r'MEATOPLASTY', 'Meatotomy'),
    ({'URO'}, r'PROSTATE\s+BIO\w*|FUSION', 'Prostate biopsy (TRUS / MRI fusion)'),
    (_A, r'URETEROURETEROSTOMY|REIMPLANT\w*', 'Ureteral reconstruction (ureteroureterostomy / reimplantation)'),
    ({'URO'}, r'OPERATIONS?\s+ON\s+PROSTATE|\bTRU\s*-?\s*P\b', 'TURP / HoLEP'),
    ({'URO'}, r'\bTURF\b', 'TURBT'),
    ({'URO'}, r'TUI\s*-?\s*BN|VISUAL\s+URETH\w+|\bVIU\b|TRANSURETHRAL\s+URET\w+OTOMY', 'Internal urethrotomy / TUI-BN'),
    (_A, r'PENECTOMY', 'Penectomy'),
    ({'URO'}, r'\bPVS\b', 'Suburethral sling'),
    ({'URO'}, r'REPAIR\s+URETHRA', 'Urethroplasty'),
    ({'URO'}, r'\bRUG\b|\bVCUG\b|URETHROGRA\w*', 'Cystogram'),
    ({'URO'}, r'PARAFFINOMA', 'Excision of penile paraffinoma'),
    (_A, r'URETHRECTOMY', 'Urethrectomy'),
    (_A, r'VASOVASOSTOMY', 'Vasovasostomy'),
    ({'URO'}, r'WATER\s*VAPOU?R', 'Rezum (water vapor therapy)'),
    (_A, r'ANORECTAL\s+MYECTOMY', 'Lateral internal sphincterotomy (LIS)'),
    (_A, r'^(OTHER\s+)?INCISION\s+(OF|WITH)\b|DRAINAGE|UNROOF', 'Incision and drainage (I&D)'),
    (_A, r'(RESECTION|REMOV\w*)\s+(OF\s+)?(MASS|TUMOU?R|CYST?|LIPOMA|POLYDACTYLY|SEROMA)|TUMOU?R\s+(RESECTION|REMOVAL)'
     r'|CYS\w*\s+REMOVAL|^MASS\s+AT\b|LIPOLYSIS', 'Excision of skin / soft-tissue lesion'),
    ({'PLA', 'GEN'}, r'^(OPEN\s+)?REVIS\w*\b', 'Scar revision'),
]
_R2 = [(sp, re.compile(p), n) for sp, p, n in _R2_RAW]
# กติกาชั้นสุดท้ายที่ต้องเว้น เมื่อทั้งชื่อ (ctx) มีคำเหล่านี้ : ACDF ใส่ plate + screw ยังเป็น ACDF ไม่ใช่ fusion ฯลฯ
_R2_BAD = {
    'Spinal decompression with fixation / fusion': re.compile(r'\bACDF\b'),
    'Amputation stump revision': re.compile(r'AMPUTAT'),
    'Breast implant / reconstruction': re.compile(r'HERNIA'),
    'Endoscopic sinonasal tumor removal': re.compile(r'ORBITAL\s+DECOMP'),
}

# 🔎 คำกำกวมที่ต้องดู diagnosis ประกอบ (มุกกี้สั่ง 21 พ.ย. 2026 22:08 : "อะไรที่ไม่มั่นใจให้ดู diagnosis หรือ procedure note ประกอบ")
#    (สาขา หรือ None, รูปแบบของชิ้น, [(รูปแบบที่ต้องเจอใน diagnosis หรือในชื่อทั้งชื่อ, หัตถการมาตรฐาน), ...])
#    ดูทีละคู่ตามลำดับ ไม่เข้าคู่ไหนเลย = ไม่จัด (ปล่อยเป็นหัตถการอื่นของสาขา ดีกว่าเดาผิด)
#    · HIFU : ไม่ใช่ยกกระชับใบหน้า (มุกกี้ชี้) ดูอวัยวะจาก diagnosis · ในข้อมูลมี thyroid mass กับ breast mass
#    · ENUCLEATION สาขาปัสสาวะ : ดูว่าทำที่ไหน (มุกกี้ชี้) ไต (AML ฯลฯ) = ผ่าไต · ต่อมลูกหมาก = TURP / HoLEP
#    · TRACTOTOMY : ดูสาขาและแพทย์ (มุกกี้ชี้) ในข้อมูลเป็นแพทย์ลำไส้ใหญ่และทวารหนัก diagnosis hidradenitis suppurativa
#      = เปิดโพรงหนอง (unroof) เวลานัด 30 นาที · ถ้า diagnosis เป็นฝีคัณฑสูตร = fistulotomy · สาขาอื่นไม่จัด
#    · IAS : จัดเป็นผ่าตัดฝีคัณฑสูตรเฉพาะเมื่อ diagnosis เป็น FIA / fistula
_DX_RULES_RAW = [
    (_A, r'\bHIFU\b', [(r'THYROID|GOIT', 'Thyroid ablation (MWA / RFA)'),
                        (r'BREAST|FIBROADENOMA', 'Breast lesion ablation (cryoablation / HIFU)'),
                        (r'\bHCC\b|\bCRLM\b|LIVER|HEPAT', 'Tumor ablation (MWA / RFA / IRE)')]),
    ({'URO'}, r'ENU\w*CLEATION', [(r'\bAML\b|ANGIOMYOLIPOMA|RENAL|KIDNEY|\b[RL]K\b|\bRCC\b', 'Nephrectomy'),
                                  (r'PROSTAT|\bBPH\b', 'TURP / HoLEP')]),
    ({'CRS', 'GEN'}, r'TRACTOTOMY', [(r'\bFIA\b|FISTUL', 'Anal fistulotomy / fistulectomy'),
                                    (r'HIDRADENITIS|SINUS|ABSCESS', 'Incision and drainage (I&D)')]),
    ({'CRS', 'GEN'}, r'\bIAS\b', [(r'\bFIA\b|FISTUL', 'Anal fistula surgery (type unspecified)')]),
]
_DX_RULES = [(sps, re.compile(p), [(re.compile(d), n) for d, n in opts]) for sps, p, opts in _DX_RULES_RAW]


def _dx_component(comp: str, sp: str, dx: str, ctx: str = '') -> Optional[Std]:
    """ชิ้นที่กติกาทุกชั้นจัดไม่ได้ และเป็นคำกำกวมใน _DX_RULES → หัตถการตาม diagnosis · ไม่เข้าเงื่อนไข = None"""
    comp = re.sub(r'\s+', ' ', re.sub(r'[._]', ' ', comp)).strip(' -/')
    hay = f'{dx} {ctx}'
    for sps, pat, opts in _DX_RULES:
        if (sps is None or sp in sps) and pat.search(comp):
            for dpat, name in opts:
                if dpat.search(hay):
                    return _std(name)
            return None
    return None


_EQUIP = re.compile(r'MICROSCOPE|MAYFI|NAVIGAT|\bCUSA\b|^ENDOSCOPE|RETRACTOR|TAFLON|TEFLON')
_LIVER_DX = re.compile(r'\bHCC\b|\bCRLM\b|LIVER|HEPAT')


def _infer_from_dx(c: str, site: str, dx: str, sp: str) -> Optional[Std]:
    """ชื่อหัตถการที่กติกาจัดไม่ได้ แต่ diagnosis บอกชัดว่าทำอะไร (เฟเบิลเพิ่ม 21 พ.ย. 2026 สำหรับรุ่น v4)
    ใช้เฉพาะคู่ที่ความหมายทางคลินิกชัด · ช่องหัตถการว่างหรือเป็นรายการเครื่องมือ (blank) จึงเดาจาก diagnosis ล้วน"""
    if site == 'เปลือกตา' and re.search(r'CORRECT|COLLECTION|BLEP|SLING|\bUPPER\b|\bLOWER\b|^U\b', c):
        return _std('Eyelid surgery (blepharoplasty / ptosis)')
    if 'CORRECT' in c and site == 'จมูก' and not re.search(r'#|FRACTURE|\bFX\b', dx):
        return _std('Rhinoplasty')
    if 'PARAF' in dx and re.search(r'REPAIR|EXCIS|STAGE', c):
        return _std('Excision of penile paraffinoma')
    if re.search(r'\bAAA\b|AORTIC\s+ANEURYSM', dx) and re.search(r'OPEN\s+REPAIR|ANEURYSMORRHAPHY', c):
        return _std('Open AAA repair')
    if _LIVER_DX.search(dx):
        if re.search(r'WEDGE|RESECTION', c):
            return _std('Liver resection')
        if 'ABLATION' in c:
            return _std('Tumor ablation (MWA / RFA / IRE)')
    if 'ABLATION' in c and 'THYROID' in dx:
        return _std('Thyroid ablation (MWA / RFA)')
    blank = (not c) or bool(_NONPROC.search(c)) or bool(_EQUIP.search(c)) or bool(re.search(r'PROLONG\w*\s+INTUB', c))
    if blank or sp == 'NEU':
        if re.search(r'PITUITARY', dx):
            return _std('Endoscopic transsphenoidal tumor removal')
        if re.search(r'TRIGEMINAL|\bTGN\b|HEMIFACIAL', dx):
            return _std('Craniotomy with microvascular decompression')
        if re.search(r'MENINGIOMA|GLIOMA|\bGBM\b|BRAIN\s+(TUMOU?R|METAS\w*)|(FRONT|TEMPOR|PARIET|OCCIPIT|CEREBEL)\w*\s+(BRAIN\s+)?(TUMOU?R|MASS|LESION)', dx):
            return _std('Craniotomy with tumor removal')
        if blank and re.search(r'\bHNP\b|DIS[CK]\s+DIS|HERNIATED\s+DIS', dx):
            return _std('Laminectomy / discectomy')
    if blank:
        if site == 'เปลือกตา':
            return _std('Eyelid surgery (blepharoplasty / ptosis)')
        if re.search(r'PROLONG\w*\s+INTUB', c):
            return _std('Tracheostomy')
        if 'APPENDICITIS' in dx:
            return _std('Open appendectomy')
        if re.search(r'INGUINAL\s+HER', dx):
            return _std('Open inguinal hernioplasty')
        if re.search(r'PROLONG\w*\s+INTUB|ATTENTION\s+TO\s+TRACHEOSTOMY|DIFFICULT\s+INTUB', dx):
            return _std('Tracheostomy')
        if re.search(r'PHIMOSIS|PREPUCE', dx):
            return _std('Circumcision')
        if 'KELOID' in dx:
            return _std('Scar revision')
    return None


# ══════════════════════════════════════════════════════════════════════════
# 🔬 แยกชนิดย่อยของหัตถการที่ชื่อเดียวกันแต่ขนาดการผ่าตัดต่างกันมาก (เฟเบิลเพิ่ม 21 พ.ย. 2026 สำหรับรุ่น v4)
#    เหตุผลทางคลินิก เช่น เสริมจมูกธรรมดา กับ open rhinoplasty ใช้กระดูกอ่อนซี่โครง · ขยายหลอดเลือด fistula กับ
#    ขยายหลอดเลือดแดงขา · ดึงจมูกหักเข้าที่ กับ ORIF กระดูกหน้า · ค่าประมาณเวลาเป็นค่าทางคลินิก ไม่ได้ลอกจากข้อมูล
# ══════════════════════════════════════════════════════════════════════════
_NEW_STD.update({
    'Rhinoplasty (open / rib cartilage graft)': ('ENT', '21.87', 4, 330),
    'Radical / extended cholecystectomy': ('Hepatobiliary', '51.22', 4, 330),
    'Liver resection (major hepatectomy)': ('Hepatobiliary', '50.3', 4, 450),
    'Closed reduction of facial fracture': ('Fracture_fixation', '21.71', 1, 50),
    'Lung lobectomy / segmentectomy': ('Other', '32.49', 4, 270),
    'Pericardial window': ('Other', '37.12', 2, 90),
    'Craniotomy with tumor removal (posterior fossa / skull base)': ('Neuro_cranial', '01.59', 4, 420),
    'Lower-limb arterial angioplasty': ('Vascular_interv', '39.50', 2, 150),
    'Facial reconstruction / orbital floor repair': ('Fracture_fixation', '76.92', 3, 180),
    'Brow lift': ('Skin_softtissue', '86.89', 2, 110),
    'Mastoidectomy / tympanomastoidectomy': ('ENT', '20.49', 4, 240),
    'Fundoplication / hiatal hernia repair': ('GI_abdominal', '44.67', 3, 210),
})
CLINICAL_PRIOR_MIN.update({k: v[3] for k, v in _NEW_STD.items()})
_STD_INDEX.clear()
_LEG_ART = re.compile(r'\bLEGS?\b|\bSFA\b|POPLIT|TIBIAL|\bILIAC|FEMORAL|CROSS\s*-?\s*OVER|DOWN\s*-?\s*HILL|UP\s*-?\s*HILL|ANTEGRADE'
                      r'|\bCLT?I\b|\bPAD\b|ISCHEMI|\bDM\s+FOOT|\bATA\b|\bPTA\s+LEG')


def _refine(main: Std, c: str, dx: str, sp: str) -> Std:
    """หัตถการหลัก → ชนิดย่อยที่ขนาดการผ่าตัดต่างกันชัดเจนทางคลินิก · ไม่เข้าเงื่อนไข = คืนของเดิม"""
    n = main.name
    if n == 'Rhinoplasty' and re.search(r'\bOPEN\b|COSTAL|\bRIB\b|CARTILAGE', c):
        return _std('Rhinoplasty (open / rib cartilage graft)')
    if 'cholecystectomy' in n and re.search(r'EXTENDED|RADICAL', c):
        return _std('Radical / extended cholecystectomy')
    if n == 'Liver resection' and re.search(r'HEPATECTOMY|SECTIONECTOMY|EXTENDED|TRISECT|LOBECTOMY|\bMAJOR\b', c) \
            and not re.search(r'PARTIAL|WEDGE', c):
        return _std('Liver resection (major hepatectomy)')
    if n == 'Fracture reduction / fixation' and re.search(r'CLOSED?\s+RED|\bCR\b|REDUCTION', c) \
            and not re.search(r'ORIF|PLATE|SCREW|\bOPEN\b|\bMMF\b|\bIMF\b|ARCH', c):
        return _std('Closed reduction of facial fracture')
    if n == 'Thoracic surgery (VATS / lung resection)':
        if re.search(r'PERICARD\w*\s+WINDOW|WINDOW', c):
            return _std('Pericardial window')
        if re.search(r'LOBECTOMY|SEGMENTECTOMY|PNEUMONECTOMY|\b[RL][UML]L\b', c) and not re.search(r'WEDGE', c):
            return _std('Lung lobectomy / segmentectomy')
    if n == 'Craniotomy with tumor removal' and (
            re.search(r'RETROSIGMOID|SUBOCCIPIT|\bSOC\b|POSTERIOR\s+FOSSA|SKULL\s+BASE|PETRO|CLIV|TRANSLAB|BIFRONTAL', c)
            or re.search(r'VESTIBULAR|ACOUSTIC|SCHWANNOMA|CEREBELL|\bCPA\b|SKULL\s+BASE|PETRO', dx)):
        return _std('Craniotomy with tumor removal (posterior fossa / skull base)')
    if n == 'Balloon angioplasty / venoplasty (PTA)' and (_LEG_ART.search(c) or _LEG_ART.search(dx)) \
            and not re.search(r'\bAVF\b|\bAVBG\b|FISTUL|\bESRD\b|VENOPLASTY|\bIJV\b|CENTRAL\s+VEIN', c + ' ' + dx):
        return _std('Lower-limb arterial angioplasty')
    if n == 'Breast implant / reconstruction' and re.search(r'ORBIT|NASAL|\bNOSE\b|MANDIB|FACIAL|CRANI|SKULL|\bEAR\b|ZYGOM', c):
        return _std('Facial reconstruction / orbital floor repair')
    if n == 'Face / brow lift' and re.search(r'BROW|ENDOTINE|TEMPORAL', c) and not re.search(r'FACE|NECK|\bFULL\b|\bMINI\b', c):
        return _std('Brow lift')
    if n == 'Tympanoplasty / mastoidectomy' and re.search(r'MASTOID|\bMRMD\b|RADICAL|TEMPORAL\s+BONE|FACIAL\s+NERVE', c):
        return _std('Mastoidectomy / tympanomastoidectomy')
    if re.search(r'hernia', n, re.I) and re.search(r'HIATAL|FUNDOPLIC|NISSEN|TOUPET|PARAESOPH', c):
        return _std('Fundoplication / hiatal hernia repair')
    return main
