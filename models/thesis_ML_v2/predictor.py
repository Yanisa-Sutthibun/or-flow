# -*- coding: utf-8 -*-
"""
predictor.py — ModelV2: ทำนายเวลาใช้ห้องผ่าตัดจาก artifacts โมเดลวิทยานิพนธ์ (13 features)
ไม่พึ่ง streamlit — ใช้ได้ทั้งในแอป OR Flow, notebook, หรือสคริปต์ประเมินผล
สร้างโดย scripts/export_artifacts.py (โฟลเดอร์ train) — แก้ที่ต้นทางแล้ว export ใหม่

การใช้:
    from predictor import ModelV2
    mv2 = ModelV2()                       # โหลด artifacts ในโฟลเดอร์เดียวกับไฟล์นี้
    r = mv2.predict_case({'procedure': 'LC', 'surgeon': '...', 'division': '75', 'age': 55})
    r['predicted_min'], r['range90'], r['confidence']

หลักการ: แปลงข้อมูลบอร์ด → 13 features แบบเดียวกับตอนเทรนเป๊ะ
(TE lookup + median impute + OHE string coercion) · ค่าที่โมเดลไม่รู้จัก → OHE ignore (ไม่ error)
"""
import os
import re
import json

import numpy as np
import pandas as pd
import joblib

OHE = ["surgeon", "สาขา", "proc_group", "or_room", "is_inpatient",
       "planicu", "blood", "ASA", "patient_sex"]
TE = ["procedure", "diagnosis"]
FEATS = OHE + ["BMI_i", "age_i"] + [c + "_te" for c in TE]

# division code → ชื่อสาขา (ตรงกับ DIV_CODE_MAP ของแอป + ค่า "สาขา" ที่โมเดลเทรน)
DIV_CODE_MAP = {
    '72': 'กุมารเวชกรรม', '73': 'ศัลยกรรมเด็ก', '74': 'ศัลยกรรมตกแต่ง',
    '75': 'ศัลยกรรมทั่วไป', '76': 'ศัลยกรรมระบบทางเดินปัสสาวะ',
    '77': 'ศัลยกรรมหู คอ จมูก', '78': 'ศัลยกรรมหลอดเลือด',
    '79': 'ศัลยกรรมเลเซอร์', '701': 'ผิวหนัง',
    '1': 'ศัลยกรรมทั่วไป', '2': 'ศัลยกรรมประสาทและสมอง',
    '3': 'ศัลยกรรมหู คอ จมูก', '4': 'ศัลยกรรมตกแต่ง',
    '5': 'ศัลยกรรมระบบทางเดินปัสสาวะ', '6': 'ศัลยกรรมลำไส้ใหญ่และทวารหนัก',
    '7': 'ศัลยกรรมหลอดเลือด', '8': 'ศัลยกรรมทรวงอก',
    '9': 'ศัลยกรรมตับ ตับอ่อน ทางเดินน้ำดี', '10': 'ปลูกถ่ายอวัยวะ',
}
_SEX_MAP = {'M': 'ชาย', 'MALE': 'ชาย', 'ช': 'ชาย', 'ชาย': 'ชาย',
            'F': 'หญิง', 'FEMALE': 'หญิง', 'ญ': 'หญิง', 'หญิง': 'หญิง'}
_YES = {'1', '1.0', 'TRUE', 'Y', 'YES', 'มี'}
_SURG_PAT = re.compile(r'^SURG_\d+$')
_NO = {'0', '0.0', 'FALSE', 'N', 'NO', 'ไม่มี'}


def _norm(s):
    """normalize ข้อความหัตถการ/วินิจฉัย ให้เทียบ key ได้ (upper + ยุบช่องว่าง)"""
    s = str(s or '').strip().upper()
    return re.sub(r'\s+', ' ', s)


def _norm_name(s):
    """normalize ชื่อบุคคล (ยุบช่องว่าง — ไม่ upper เพราะเป็นไทย)"""
    return re.sub(r'\s+', ' ', str(s or '').strip())


class ModelV2:
    def __init__(self, art_dir=None, staff_map=None):
        art_dir = art_dir or os.path.dirname(os.path.abspath(__file__))
        self.dir = art_dir
        # 🔑 ชื่อแพทย์ → SURG_xxx (โมเดลถูก mask): หา staff_mapping.csv ตามลำดับ
        #    (บน cloud ไม่มีไฟล์ → surgeon เป็น unknown — โมเดลยังทำนายได้จาก feature อื่น)
        self.name2code = {}
        for pth in (staff_map,
                    os.path.join(art_dir, 'staff_mapping.csv'),
                    os.path.join(art_dir, '..', '..', 'staff_mapping.csv'),
                    os.path.join(art_dir, '..', 'staff_mapping_ADD_thesis_ML_v2.csv')):
            if pth and os.path.exists(pth):
                try:
                    df = pd.read_csv(pth, encoding='utf-8-sig')
                    if 'role' in df.columns:
                        df = df[df['role'].astype(str).str.strip() == 'surgeon']
                    self.name2code.update({
                        _norm_name(n): str(c).strip()
                        for c, n in zip(df['masked_code'], df['original_name'])
                        if pd.notna(n)})
                except Exception:
                    pass
        self.pipe = joblib.load(os.path.join(art_dir, 'model.pkl'))
        self.te = self._j('te_maps.json')
        self.impute = self._j('impute.json')
        self.cats = {k: set(v) for k, v in self._j('ohe_categories.json').items()}
        self.conf = self._j('conformal.json')
        m = os.path.join(art_dir, 'maps')
        self.proc_group = self._csvmap(os.path.join(m, 'procedure_to_proc_group.csv'),
                                       'procedure', 'proc_group')
        self.canon9 = self._csvmap(os.path.join(m, 'map_icd9cm_name_fuzzy.csv'),
                                   'variant', 'canonical')
        self.canon10 = self._csvmap(os.path.join(m, 'map_icd10_name_fuzzy.csv'),
                                    'variant', 'canonical')
        self.abbrev = {}
        ab = os.path.join(m, 'manual_abbrev_map.csv')
        if os.path.exists(ab):
            df = pd.read_csv(ab, encoding='utf-8-sig')
            for _, r in df.iterrows():
                self.abbrev[_norm(r['abbrev'])] = (_norm(r.get('full_name', '')),
                                                   str(r.get('proc_group', '')))

    def _j(self, name):
        with open(os.path.join(self.dir, name), encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _csvmap(path, k, v):
        if not os.path.exists(path):
            return {}
        df = pd.read_csv(path, encoding='utf-8-sig')
        return {_norm(a): str(b) for a, b in zip(df[k], df[v]) if pd.notna(a)}

    # ---------- resolvers ----------
    def _cat(self, feat, val):
        """coerce ค่าให้ตรง category ตอนเทรน (เช่น ห้อง 17 → '17.0') — ไม่ตรงก็ปล่อยผ่าน
        (OneHotEncoder(handle_unknown='ignore') จะเมินให้เอง) คืน (ค่า, รู้จักไหม)"""
        s = str(val).strip() if val not in (None, '') else 'Unknown'
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

    def resolve_procedure(self, name):
        n = _norm(name)
        if n in self.abbrev and self.abbrev[n][0]:
            n = self.abbrev[n][0]
        return self.canon9.get(n, n)

    def resolve_proc_group(self, canon, raw=''):
        for key in (_norm(canon), _norm(raw)):
            if key and key in self.proc_group:
                return self.proc_group[key]
        n = _norm(raw)
        if n in self.abbrev and self.abbrev[n][1]:
            return self.abbrev[n][1]
        return 'UNKNOWN'

    # ---------- main ----------
    def predict_case(self, case):
        """case: dict — คีย์ที่รองรับ (ส่งเท่าที่มี):
        procedure*, diagnosis, surgeon (ชื่อจริงหรือ SURG_xxx), division|specialty,
        age, sex|patient_sex, ASA, BMI, is_inpatient|ward, planicu, blood,
        proc_group (override ได้), or_room (ไม่ต้องส่งก็ได้ — ห้องตึกใหม่ 90-97
        ไม่อยู่ในชุดเทรน โมเดลจะไม่ใช้ห้องในการทำนายโดยอัตโนมัติ)"""
        raw_proc = case.get('procedure', '')
        proc = self.resolve_procedure(raw_proc)
        diag = self.canon10.get(_norm(case.get('diagnosis', '')),
                                _norm(case.get('diagnosis', '')))
        group = (str(case['proc_group']) if case.get('proc_group')
                 else self.resolve_proc_group(proc, raw_proc))

        spec = case.get('specialty') or DIV_CODE_MAP.get(
            str(case.get('division', '')).strip().rstrip('.0') or 'x',
            str(case.get('division', '')))
        s_raw = str(case.get('surgeon') or '').strip()
        s_in = s_raw if _SURG_PAT.match(s_raw) else \
            self.name2code.get(_norm_name(s_raw), s_raw)
        surgeon, surg_known = self._cat('surgeon', s_in)
        spec, _ = self._cat('สาขา', spec)
        group_c, group_known = self._cat('proc_group', group)
        room, room_known = self._cat('or_room', case.get('or_room'))

        asa_m = re.search(r'(\d)', str(case.get('ASA', case.get('asa', ''))))
        asa, _ = self._cat('ASA', asa_m.group(1) if asa_m else 'Unknown')

        def yn(v):
            s = str(v).strip().upper()
            if v is None or s in ('', 'NAN', 'NONE', 'UNKNOWN'):
                return 'Unknown'
            return 'มี' if s in _YES else ('ไม่มี' if s in _NO else 'Unknown')

        sex = _SEX_MAP.get(str(case.get('sex', case.get('patient_sex', ''))).strip().upper(),
                           str(case.get('sex', case.get('patient_sex', 'Unknown')) or 'Unknown'))
        inp = case.get('is_inpatient')
        if inp is None:
            inp = 1 if str(case.get('ward', '') or '').strip() else 0
        inp = '1' if str(inp).strip() in _YES else '0'

        def num(v, med):
            try:
                f = float(v)
                return f if np.isfinite(f) else med
            except (TypeError, ValueError):
                return med

        te_vals, te_hit, proc_n = {}, {}, 0
        for c, key in (('procedure', proc), ('diagnosis', diag)):
            entry = self.te[c]['map'].get(key)
            te_hit[c] = entry is not None
            te_vals[c] = entry[0] if entry else self.te[c]['global_mean']
            if c == 'procedure' and entry:
                proc_n = entry[1]

        row = pd.DataFrame([{
            'surgeon': surgeon, 'สาขา': spec, 'proc_group': group_c, 'or_room': room,
            'is_inpatient': inp, 'planicu': yn(case.get('planicu')),
            'blood': yn(case.get('blood')), 'ASA': asa, 'patient_sex': sex,
            'BMI_i': num(case.get('BMI', case.get('bmi')), self.impute['BMI_median']),
            'age_i': num(case.get('age'), self.impute['age_median']),
            'procedure_te': te_vals['procedure'], 'diagnosis_te': te_vals['diagnosis'],
        }])[FEATS]
        pred = float(np.clip(np.expm1(self.pipe.predict(row))[0], 5, 720))

        q90 = self.conf['per_proc_group_q90'].get(group_c,
                                                  self.conf['global']['q90'])
        hits = te_hit['procedure'] + surg_known + group_known
        confidence = 'สูง' if (te_hit['procedure'] and hits == 3) else \
                     ('ปานกลาง' if hits >= 2 else 'ต่ำ')
        return {
            'predicted_min': int(round(pred)),
            'range90': (int(max(5, round(pred - q90))), int(round(pred + q90))),
            'confidence': confidence, 'proc_n': int(proc_n),
            'model_version': 'thesis_ML_v2',
            'details': {'procedure_canon': proc, 'proc_group': group_c,
                        'สาขา': spec, 'te_hit': te_hit, 'surgeon_known': surg_known,
                        'room_known': room_known, 'q90': round(float(q90), 1)},
        }


if __name__ == '__main__':
    mv = ModelV2()
    demo = {'procedure': 'LC', 'diagnosis': 'GALLSTONE', 'surgeon': 'ทดสอบ',
            'division': '75', 'or_room': 93, 'age': 55, 'sex': 'หญิง', 'ASA': '2',
            'is_inpatient': 1}
    print(json.dumps(mv.predict_case(demo), ensure_ascii=False, indent=1, default=str))
