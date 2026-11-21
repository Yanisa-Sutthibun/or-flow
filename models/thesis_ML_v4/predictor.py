# -*- coding: utf-8 -*-
"""
predictor.py : ModelV2 ของ thesis_ML_v4 : ทำนายเวลาใช้ห้องผ่าตัดจากข้อมูลก่อนผ่าตัด (ไม่พึ่ง streamlit)
ต้นฉบับ = train/scripts/predictor_v4.py (แก้ที่ต้นทางแล้วรัน train_v4.py ใหม่) · ชื่อคลาสคง ModelV2 เพราะแอปเรียกชื่อนี้

    from predictor import ModelV2
    mv = ModelV2()                         # โหลดไฟล์ในโฟลเดอร์เดียวกับไฟล์นี้
    r = mv.predict_case({'procedure': 'LC', 'diagnosis': 'gallstone', 'surgeon': 'ชื่อแพทย์หรือ SURG_xxx',
                         'division': '1', 'or_room': 93, 'age': 55, 'sex': 'หญิง', 'ASA': '2', 'is_inpatient': 1,
                         'sched_hour': 9})
    r['predicted_min'], r['range90'], r['confidence']

หลัก (รุ่น v4) : ทุกค่าที่มาจากชื่อหัตถการคำนวณด้วย procedure_master_frozen.py ซึ่งเป็นสำเนาพจนานุกรม ณ วันที่เทรน
จึงได้ค่าเดียวกับตอนเทรนเสมอ แม้พจนานุกรมกลางของแอปจะถูกแก้ต่อ · ช่องที่ไม่ส่งมา = ค่าว่างแบบเดียวกับตอนเทรน
🔒 ใช้เฉพาะข้อมูลที่มีก่อนผ่าตัด (มุกกี้ย้ำ 21 พ.ย. 2026 21:39) : ตารางผ่าตัด + ใบประเมินก่อนระงับความรู้สึก ไม่มีช่องไหนมาจาก intraop
   สาขา แปลงจากรหัส division ของตารางผ่าตัดด้วยตารางใน meta.json (division_name_map) · ผู้ป่วยใน/นอก ดูจากช่องหอผู้ป่วย
   ช่วงเวลานัด รับ estmtime ของตารางผ่าตัดได้ตรง ๆ (ตอนเทรนใช้ opetime ซึ่ง HIS ตั้งเป็น estmtime ลบ 5 นาที : 0 = ต่อคิว → 23)
"""
import os
import re
import json
import importlib.util

import numpy as np
import pandas as pd
import joblib

DIV_CODE_MAP = {
    '72': 'กุมารเวชกรรม', '73': 'ศัลยกรรมเด็ก', '74': 'ศัลยกรรมตกแต่ง', '75': 'ศัลยกรรมทั่วไป',
    '76': 'ศัลยกรรมระบบทางเดินปัสสาวะ', '77': 'ศัลยกรรมหู คอ จมูก', '78': 'ศัลยกรรมหลอดเลือด',
    '79': 'ศัลยกรรมเลเซอร์', '701': 'ผิวหนัง',
    '1': 'ศัลยกรรมทั่วไป', '2': 'ศัลยกรรมประสาทและสมอง', '3': 'ศัลยกรรมหู คอ จมูก', '4': 'ศัลยกรรมตกแต่ง',
    '5': 'ศัลยกรรมระบบทางเดินปัสสาวะ', '6': 'ศัลยกรรมลำไส้ใหญ่และทวารหนัก', '7': 'ศัลยกรรมหลอดเลือด',
    '8': 'ศัลยกรรมทรวงอก', '9': 'ศัลยกรรมตับ ตับอ่อน ทางเดินน้ำดี', '10': 'ปลูกถ่ายอวัยวะ',
}
_SEX_MAP = {'M': 'ชาย', 'MALE': 'ชาย', 'ช': 'ชาย', 'ชาย': 'ชาย', 'F': 'หญิง', 'FEMALE': 'หญิง', 'ญ': 'หญิง', 'หญิง': 'หญิง'}
_YES = {'1', '1.0', 'TRUE', 'Y', 'YES', 'มี'}
_NO = {'0', '0.0', 'FALSE', 'N', 'NO', 'ไม่มี'}
_SURG_PAT = re.compile(r'^SURG_\d+$')


def _blank(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def _norm_dx(s):
    """วินิจฉัย : ตัวใหญ่ ตัดเครื่องหมาย ยุบช่องว่าง (สูตรเดียวกับ build_merged_v3.norm_text)"""
    return '' if _blank(s) else re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9ก-๙]+', ' ', str(s).upper())).strip()


def _norm_name(s):
    return re.sub(r'\s+', ' ', str(s or '').strip())


def div_key(v):
    """รหัส division ของตารางผ่าตัด → ข้อความเลขล้วน (1.0 / '1.0' / ' 1 ' → '1') · ว่างหรือไม่ใช่เลข คืนข้อความเดิมที่ตัดช่องว่าง"""
    if _blank(v):
        return ''
    t = str(v).strip()
    try:
        f = float(t)
        return str(int(f)) if f == int(f) else t
    except ValueError:
        return t


class ModelV2:
    def __init__(self, art_dir=None, staff_map=None):
        art_dir = art_dir or os.path.dirname(os.path.abspath(__file__))
        self.dir = art_dir
        # 🧊 พจนานุกรมหัตถการ ณ วันที่เทรน (อยู่ในโฟลเดอร์แบบจำลอง)
        fz = os.path.join(art_dir, 'procedure_master_frozen.py')
        sp = importlib.util.spec_from_file_location('pm_frozen_' + os.path.basename(os.path.abspath(art_dir)), fz)
        self.pm = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(self.pm)
        # 🔑 ชื่อแพทย์ → SURG_xxx จากทะเบียนของแอป (บน cloud ไม่มีไฟล์ = ไม่รู้จักแพทย์ ยังทำนายได้จากตัวแปรอื่น)
        #    คนเดียวกันมีได้สองรหัส : รหัสทะเบียนวิจัย (role surgeon) ชนะรหัสที่แอปออกเองตอนลง log (role SURG)
        #    ลำดับเดียวกับ train_v4.surgeon_codes : แก้ที่หนึ่งต้องแก้อีกที่ด้วย
        self.name2code = {}
        for pth in (staff_map, os.path.join(art_dir, 'staff_mapping.csv'),
                    os.path.join(art_dir, '..', '..', 'staff_mapping.csv'),
                    os.path.join(art_dir, '..', '..', '..', 'main_OR_app', 'staff_mapping.csv')):
            if pth and os.path.exists(pth):
                try:
                    df = pd.read_csv(pth, encoding='utf-8-sig')
                    df = df[df['masked_code'].astype(str).str.match(r'^SURG_\d+$') & df['original_name'].notna()]
                    role = (df['role'].astype(str).str.strip() if 'role' in df.columns
                            else pd.Series('surgeon', index=df.index))
                    for part in (df[role != 'surgeon'], df[role == 'surgeon']):
                        self.name2code.update({_norm_name(n): str(c).strip()
                                               for c, n in zip(part['masked_code'], part['original_name'])})
                except Exception:
                    pass
        self.pipe = joblib.load(os.path.join(art_dir, 'model.pkl'))
        self.te = self._j('te_maps.json')
        self.impute = self._j('impute.json')
        self.cats = {k: set(v) for k, v in self._j('ohe_categories.json').items()}
        self.conf = self._j('conformal.json')
        self.meta = self._j('meta.json')
        self.feats = self.meta['features']
        self.div_name = self.meta.get('division_name_map') or {}       # รหัส division → ชื่อสาขาแบบที่ใช้ตอนเทรน
        self.version = self.meta.get('model_version', 'thesis_ML_v4')

    def _j(self, name):
        with open(os.path.join(self.dir, name), encoding='utf-8') as f:
            return json.load(f)

    def _cat(self, feat, val):
        """ปรับค่าให้ตรงหมวดตอนเทรน (ห้อง 93 → '93.0') · ไม่ตรงก็ปล่อยผ่าน แบบจำลองเมินหมวดที่ไม่รู้จักเอง"""
        s = str(val).strip() if not _blank(val) and val != '' else 'Unknown'
        cands = [s]
        try:
            f = float(s)
            cands += [f'{f:.1f}', f'{int(f)}', f'{f:g}']
        except ValueError:
            pass
        for c in cands:
            if c in self.cats.get(feat, ()):
                return c, True
        return s, False

    @staticmethod
    def _sched_hour(case):
        """ชั่วโมงของเวลานัดในตารางผ่าตัด 0-23 (23 = ช่องต่อคิว) แบบเดียวกับตอนเทรน
        รับ sched_hour · หรือ estmtime ของตารางผ่าตัด (HHMMSS / 'HH:MM' · 0 หรือว่าง = ต่อคิว) ซึ่งจะถอย 5 นาทีให้เท่า opetime
        · หรือ opetime / sched_time แบบ HHMMSS / 'HH:MM' (ไม่ถอย)"""
        v = case.get('sched_hour')
        if _blank(v) and 'estmtime' in case:
            t = str(case.get('estmtime') if not _blank(case.get('estmtime')) else '0').strip()
            try:
                if ':' in t:
                    hh, mm = int(t.split(':')[0]), int(t.split(':')[1])
                else:
                    n = int(float(t or 0))
                    hh, mm = n // 10000, (n // 100) % 100
            except ValueError:
                return np.nan
            return float(((hh * 60 + mm - 5) % 1440) // 60)
        if _blank(v):
            v = case.get('opetime', case.get('sched_time'))
            if _blank(v):
                return np.nan
            t = str(v).strip()
            try:
                return float(int(t.split(':')[0])) if ':' in t else float(int(float(t)) // 10000)
            except ValueError:
                return np.nan
        try:
            return float(v)
        except (TypeError, ValueError):
            return np.nan

    def _te(self, col, key):
        e = self.te[col]['map'].get(key)
        return (e[0], e[1]) if e else (self.te[col]['global_mean'], 0)

    def predict_case(self, case):
        """case : dict ของข้อมูลก่อนผ่าตัด ส่งเท่าที่มี
        procedure*, diagnosis, surgeon (ชื่อจริงหรือ SURG_xxx), division | specialty, or_room, age, sex | patient_sex,
        ASA, BMI, is_inpatient | ward, planicu, blood, sched_hour | estmtime | opetime"""
        pm = self.pm
        raw = '' if _blank(case.get('procedure')) else str(case.get('procedure'))
        if raw.strip().upper() in ('UNKNOWN', '-'):       # แอปเติมคำนี้เมื่อช่องหัตถการในตารางผ่าตัดว่าง : ตอนเทรนคือช่องว่าง
            raw = ''
        dx = '' if _blank(case.get('diagnosis')) else str(case.get('diagnosis'))
        # 🏷️ สาขา : รหัส division ของตารางผ่าตัดมาก่อนเสมอ (ชื่อสาขาที่ส่งมาใช้เมื่อไม่มีรหัสเท่านั้น)
        dk = div_key(case.get('division'))
        spec = self.div_name.get(dk) or DIV_CODE_MAP.get(dk) or case.get('specialty') or dk
        spk = pm.specialty_key(case.get('division')) or pm.specialty_key(spec)
        f = pm.features(raw, spk, dx)
        s_raw = str(case.get('surgeon') or '').strip()
        s_in = s_raw if _SURG_PAT.match(s_raw) else self.name2code.get(_norm_name(s_raw), s_raw)
        surgeon, surg_known = self._cat('surgeon', s_in)
        spec, _ = self._cat('สาขา', spec)
        group, group_known = self._cat('proc_group', f['group'])
        room, room_known = self._cat('or_room', case.get('or_room'))
        asa_m = re.search(r'(\d)', str(case.get('ASA', case.get('asa', ''))))
        asa, _ = self._cat('ASA', asa_m.group(1) if asa_m else 'Unknown')

        def yn(v):
            s = str(v).strip().upper()
            if _blank(v) or s in ('', 'NAN', 'NONE', 'UNKNOWN'):
                return 'Unknown'
            return 'มี' if s in _YES else ('ไม่มี' if s in _NO else 'Unknown')

        sex_in = case.get('sex', case.get('patient_sex', ''))
        sex = _SEX_MAP.get(str(sex_in).strip().upper(), str(sex_in or 'Unknown'))
        inp = case.get('is_inpatient')
        if inp is None:
            inp = 1 if str(case.get('ward', '') or '').strip() else 0
        inp = '1' if str(inp).strip() in _YES else '0'

        def num(v, med):
            try:
                x = float(v)
                return x if np.isfinite(x) else med
            except (TypeError, ValueError):
                return med

        p_te, p_n = self._te('procedure', f['key'])
        d_te, d_n = self._te('diagnosis', _norm_dx(dx))
        row = {
            'surgeon': surgeon, 'สาขา': spec, 'proc_group': group, 'or_room': room, 'is_inpatient': inp,
            'planicu': yn(case.get('planicu')), 'blood': yn(case.get('blood')), 'ASA': asa, 'patient_sex': sex,
            'BMI_i': num(case.get('BMI', case.get('bmi')), self.impute['BMI_median']),
            'age_i': num(case.get('age'), self.impute['age_median']),
            'procedure_te': p_te, 'diagnosis_te': d_te,
            'proc_clean_te': self._te('proc_clean', pm.clean(raw))[0],
            'surg_proc_te': self._te('surg_proc', f'{surgeon}|{f["key"]}')[0],
            'sched_hour': self._sched_hour(case),
            'proc_txt': pm.spellfix(raw.upper()),
        }
        row.update({k: f[k] for k in pm.PM_NUM + pm.MOD_NAMES})
        X = pd.DataFrame([row])[self.feats]
        pred = float(np.clip(np.expm1(self.pipe.predict(X))[0], 5, 720))

        lq = self.conf.get('per_proc_group_logq', {}).get(group) or self.conf['global_logq']
        lo, hi = pred * float(np.exp(lq[0])), pred * float(np.exp(lq[1]))
        hit = p_n > 0
        hits = hit + surg_known + group_known
        confidence = 'สูง' if (hit and hits == 3) else ('ปานกลาง' if hits >= 2 else 'ต่ำ')
        return {
            'predicted_min': int(round(pred)), 'range90': (int(max(5, round(lo))), int(round(hi))),
            'confidence': confidence, 'proc_n': int(p_n), 'model_version': self.version,
            'details': {'procedure_canon': f['key'], 'proc_group': group, 'สาขา': spec,
                        'te_hit': {'procedure': bool(hit), 'diagnosis': d_n > 0},
                        'surgeon_known': surg_known, 'room_known': room_known,
                        'clinical_prior_min': None if f['pm_prior'] != f['pm_prior'] else f['pm_prior'],
                        'range_method': 'log_ratio'},
        }


if __name__ == '__main__':
    mv = ModelV2()
    print(json.dumps(mv.predict_case({'procedure': 'LC', 'diagnosis': 'GALLSTONE', 'surgeon': 'ทดสอบ', 'division': '1',
                                      'or_room': 93, 'age': 55, 'sex': 'หญิง', 'ASA': '2', 'is_inpatient': 1,
                                      'sched_hour': 9}), ensure_ascii=False, indent=1, default=str))
