# -*- coding: utf-8 -*-
"""
preop_merge.py — 💉 เติมข้อมูล preop วิสัญญี เข้าเคสบนบอร์ด (มุคกี้สั่ง 19 ก.ค. 2026)
════════════════════════════════════════════════════════════════════════════
ไฟล์ preop จาก HIS (เช่น preop69.xls) มี feature ที่โมเดล thesis_ML_v2 ใช้
แต่บอร์ดไม่เคยมี: ASA · น้ำหนัก/ส่วนสูง (→BMI) · จองเลือด · จอง ICU
→ อัปโหลดคู่กับ CSV ตารางผ่าตัด ระบบจับคู่ด้วย HN แล้วเติมเข้าเคสก่อนทำนาย

โครงไฟล์ที่รองรับ (ตรวจจากไฟล์จริง ปี 69, 8,130 แถว):
  hn · weight · height · planicu · blood · estmdate (วันผ่าตัด)
  คอลัมน์ ASA ชื่อไม่แน่นอน (name.3 จากการ join ของ HIS) → หาอัตโนมัติจากเนื้อค่า
  (คอลัมน์ที่ค่าส่วนใหญ่เป็น 1-5 + E เช่น '2', '3E')
รหัส HIS: 1 = ใช่/จอง · 2 = ไม่ · 0/ว่าง = ไม่ประเมิน → แปลงเป็น 'มี'/'ไม่มี'/None
ตามที่ predictor คาด (_YES/_NO)

หมายเหตุ PDPA: ใช้ในหน่วยความจำระหว่างอัปโหลดเท่านั้น — ไม่เขียนไฟล์ ไม่ลง DB
"""
from __future__ import annotations

import re


def _yn(v):
    """รหัส HIS → 'มี'/'ไม่มี'/None (1=ใช่ 2=ไม่ 0/ว่าง=ไม่ประเมิน)"""
    s = str(v).strip().rstrip('.0') if v is not None else ''
    if s == '1':
        return 'มี'
    if s == '2':
        return 'ไม่มี'
    return None


_ASA_PAT = re.compile(r'^[1-5]E?$', re.IGNORECASE)


def _find_asa_col(df):
    """หาคอลัมน์ ASA จากเนื้อค่า (ชื่อคอลัมน์ HIS ไม่คงที่)"""
    best, best_ratio = None, 0.0
    for c in df.columns:
        vals = df[c].dropna().astype(str).str.strip()
        if len(vals) < 20:
            continue
        ratio = vals.str.match(_ASA_PAT).mean()
        if ratio > 0.9 and ratio > best_ratio:
            best, best_ratio = c, ratio
    return best


def load_preop(file) -> dict:
    """อ่านไฟล์ preop (.xls/.xlsx) → {hn: {'ASA','BMI','planicu','blood'}}
    ผู้ป่วยมีหลายแถว (มาหลายครั้ง) → ใช้แถว estmdate ล่าสุด"""
    import pandas as pd
    _fname = str(getattr(file, 'name', file)).lower()
    if _fname.endswith('.csv'):
        df = None
        for _enc in ('utf-8-sig', 'cp874', 'utf-16'):   # HIS ส่งออกได้หลาย encoding
            try:
                if hasattr(file, 'seek'):
                    file.seek(0)
                df = pd.read_csv(file, dtype=str, encoding=_enc)
                break
            except (UnicodeError, UnicodeDecodeError):
                continue
        if df is None:
            raise ValueError('อ่านไฟล์ CSV ไม่ได้ — encoding ไม่รู้จัก')
    else:
        df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    if 'hn' not in df.columns:
        raise ValueError(f"ไฟล์ preop ไม่มีคอลัมน์ hn — เจอ: {list(df.columns)[:8]}")
    asa_col = _find_asa_col(df)
    if 'estmdate' in df.columns:
        df = df.sort_values('estmdate')          # แถวท้าย = ล่าสุด
    out = {}
    for _, r in df.iterrows():
        hn = str(r.get('hn') or '').strip()
        if not hn:
            continue
        rec = out.setdefault(hn, {})
        # เขียนทับด้วยแถวใหม่กว่าเสมอ (เรียงตาม estmdate แล้ว) — เว้นค่าว่างไม่ทับ
        if asa_col:
            _a = str(r.get(asa_col) or '').strip().upper()
            if _ASA_PAT.match(_a):          # กัน 'NAN'/ค่าเพี้ยนจากช่องว่าง
                rec['ASA'] = _a
        try:
            w = float(r.get('weight') or 0)
            h = float(r.get('height') or 0)
            if w > 20 and 100 < h < 230:
                bmi = w / ((h / 100) ** 2)
                if 10 <= bmi <= 70:
                    rec['BMI'] = round(bmi, 1)
        except (TypeError, ValueError):
            pass
        for k in ('planicu', 'blood'):
            v = _yn(r.get(k))
            if v is not None:
                rec[k] = v
    return out


def sex_from_name(name) -> str | None:
    """เดาเพศจากคำนำหน้าชื่อไทย (ใช้กับทุกเคส ไม่ต้องพึ่งไฟล์ preop)"""
    s = str(name or '').strip()
    if not s:
        return None
    if re.match(r'^(นาง|น\.ส\.|นางสาว|ด\.ญ\.)', s) or 'หญิง' in s[:22]:
        return 'หญิง'
    if re.match(r'^(นาย|ด\.ช\.|MR\.?\s)', s, re.IGNORECASE):
        return 'ชาย'
    # ยศตำรวจ/ทหารที่ไม่มีคำว่า "หญิง" นำหน้า = ชาย (ธรรมเนียมการเขียนยศไทย)
    if re.match(r'^(ว่าที่\s*)?(พล\.?ต|พ\.?ต|ร\.?ต|ส\.?ต|ด\.?ต|จ\.?ส\.?ต|นรต)', s):
        return 'ชาย'
    return None


def enrich_cases(cases, preop_map=None) -> int:
    """เติม sex (จากชื่อ) + ASA/BMI/planicu/blood (จาก preop) เข้าเคสบนบอร์ด
    คืนจำนวนเคสที่จับคู่ไฟล์ preop เจอ"""
    matched = 0
    for c in cases:
        if not c.get('sex'):
            sx = sex_from_name(c.get('name'))
            if sx:
                c['sex'] = sx
        if preop_map:
            rec = preop_map.get(str(c.get('hn') or '').strip())
            if rec:
                matched += 1
                for k, v in rec.items():
                    c[k] = v
    return matched
