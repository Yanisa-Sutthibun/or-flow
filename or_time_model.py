"""
or_time_model.py — โมเดลทำนายเวลา OR แบบ honest (hierarchical median + XGBoost residual)
═══════════════════════════════════════════════════════════════════════
ออกแบบจากผลเปรียบเทียบบน locked test set (train 2021-2023 → test 2024, ไม่ leak):

  วิธี                         เวลาใช้ห้อง MAE   เวลาผ่าตัด MAE
  เดามัธยฐานรวม (naive)            71.8            60.8
  มัธยฐานต่อหัตถการ                55.2            47.8
  มัธยฐานลำดับชั้น (hier)          45.4            39.6
  hier + XGBoost residual (นี่)    41.8            37.5   ← ดีสุด (โมเดล deploy จริง, หลัง dedup)

2 target:
  - room_use  : เวลาครองห้องผ่าตัด (room-in → room-out)  — สำหรับจัดตารางห้อง
  - surg_time : เวลาผ่าตัดสุทธิ (opesttime ลงมีด → opendtime จบ)

วิธีทำนาย: hier = มัธยฐานของกลุ่มหัตถการที่เฉพาะที่สุดที่มีข้อมูล ≥ 5 เคส
           (ชื่อเต็ม → keyword 2 คำ → keyword 1 คำ → ค่ากลางรวม)
           จากนั้น XGBoost เรียน "ส่วนต่าง" จาก hier เพื่อปรับละเอียด

ช่วงทำนาย (prediction interval): split conformal prediction — คาลิเบรตจาก
           ชุด hold-out ปี 2567 (build_conformal.py → models/honest_v1/conformal.json)
           ช่วง = ŷ ± q̂ ที่ระดับ coverage 80% / 90%

🔒 PDPA บุคลากร: key ของ surg_med/surg_n ในไฟล์ artifact เป็นรหัส SURG_xxx
           (ไม่มีชื่อจริง) — _surgeon_key แปลง ชื่อจริง→รหัส ตอน predict
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from functools import lru_cache

from main_or_predictor import normalize_proc, normalize_surgeon

_DIR = Path(__file__).resolve().parent / "models" / "honest_v1"
_FEATS = ['hier', 'surg_med', 'surg_n', 'age', 'planned_hour', 'dow', 'month',
          'orroom', 'division', 'full_n']
TARGETS = ('room_use', 'surg_time')

# รหัส masked ของบุคลากร (ชุดเดียวกับ staff_mapping.csv / Supabase)
_SURG_CODE_RE = re.compile(r"^surg_\d{2,5}$", re.I)


def _phash(s: str) -> str:
    """รหัสแฮชของ 'ชื่อหัตถการเต็ม' (p_full) — ปกปิด free-text note ที่บางครั้งมีชื่อบุคคล
    ปนอยู่ ก่อนนำไฟล์โมเดลขึ้น repo · ใช้แฮชเดียวกันทั้งตอนสร้าง artifact และตอน lookup
    จึงทำนายได้ผลเท่าเดิมทุกประการ (PDPA-safe)"""
    import hashlib
    return "PF" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _pfull_lookup(meta: dict, full: str) -> str:
    """คืน key ที่ใช้ค้น p_full / full_n — แฮชเมื่อ artifact ถูกปกปิดคีย์แล้ว (proc_keys_hashed)"""
    return _phash(full) if meta.get("proc_keys_hashed") else full


@lru_cache(maxsize=4)
def _load(target: str):
    """โหลด hier tables (JSON) + residual model (pkl) — cache ไว้"""
    import joblib
    meta = json.load(open(_DIR / f"hier_{target}.json", encoding="utf-8"))
    model = joblib.load(_DIR / f"resid_{target}.pkl")
    return meta, model


@lru_cache(maxsize=1)
def _name2codes() -> dict:
    """แผนที่ ชื่อแพทย์ (normalized) → [SURG_xxx, ...] จาก staff_mapping.csv
    (คนเดียวอาจมีหลายรหัสจากแถว legacy — เก็บทุกตัวเรียงตามลำดับในไฟล์)
    บนเครื่องที่ไม่มี mapping (เช่น Streamlit Cloud) → dict ว่าง"""
    try:
        from staff_unmask import _load_mapping
        out: dict = {}
        for code, orig in _load_mapping().items():
            if code.startswith("SURG_"):
                out.setdefault(normalize_surgeon(orig), []).append(code)
        return out
    except Exception:
        return {}


def _surgeon_key(raw_name: str, meta: dict) -> str:
    """หา key ของแพทย์ใน surg_med — รองรับทั้ง 3 รูปแบบ input:
      1) ชื่อจริง  → แปลงเป็น SURG_xxx ผ่าน staff_mapping (เครื่องที่มี mapping)
         คนที่มีหลายรหัส → เลือกรหัสที่ "มีอยู่จริงในตารางโมเดล"
      2) รหัส SURG_xxx ตรงๆ (เช่นข้อมูลจาก Supabase ที่ mask แล้ว)
      3) artifact รุ่นเก่าที่ key เป็นชื่อจริง → ใช้ชื่อ normalized ตรงๆ (backward compat)
    ถ้าหาไม่เจอ คืนชื่อ normalized (จะ fallback เป็นค่ากลางรวมเหมือนเดิม)"""
    s = normalize_surgeon(raw_name or "")
    table = meta.get("surg_med", {})
    if s in table:                       # artifact เก่า (key ชื่อจริง) หรือชื่อตรง key
        return s
    if _SURG_CODE_RE.match(s):           # input เป็นรหัสอยู่แล้ว
        up = s.upper()
        return up if up in table else s
    for code in _name2codes().get(s, ()):    # ชื่อจริง → ลองทุกรหัสของคนนี้
        if code in table:
            return code
    return s


@lru_cache(maxsize=1)
def _conformal() -> dict:
    """โหลดค่าคาลิเบรต split conformal (models/honest_v1/conformal.json)
    — ไม่มีไฟล์ = dict ว่าง (ช่วงทำนายจะไม่ถูกแสดง)"""
    try:
        return json.load(open(_DIR / "conformal.json", encoding="utf-8"))
    except Exception:
        return {}


def conformal_q(target: str = "room_use", coverage: str = "0.90"):
    """ครึ่งกว้างช่วงทำนาย (นาที) ที่ระดับ coverage ที่ขอ — None ถ้าไม่ได้คาลิเบรต"""
    try:
        return float(_conformal()[target]["q"][coverage])
    except (KeyError, TypeError, ValueError):
        return None


def conformal_info(target: str = "room_use") -> dict:
    """ข้อมูลคาลิเบรตทั้งก้อน (n_calib, headline MAE, temporal check) สำหรับ UI"""
    return _conformal().get(target, {})


def _interval(pred: float, q):
    if q is None:
        return None
    return [int(max(5, round(pred - q))), int(min(1440, round(pred + q)))]


def _hier(meta: dict, full: str, kw2: str, kw1: str) -> float:
    """มัธยฐานลำดับชั้น: ชั้นเฉพาะที่สุดที่มี count >= min_count ชนะ"""
    g = meta["global_median"]; mc = meta["min_count"]; lv = meta["levels"]
    pred = g
    for key, name in (("p_kw1", kw1), ("p_kw2", kw2),
                      ("p_full", _pfull_lookup(meta, full))):  # กว้าง→เฉพาะ
        ent = lv[key].get(name)
        if ent and ent[1] >= mc:
            pred = ent[0]
    return pred


def _hier_detail(meta, full, kw2, kw1):
    """คืน (ค่า hier, ชั้นที่ใช้, จำนวนเคสที่อิง)"""
    g = meta["global_median"]; mc = meta["min_count"]; lv = meta["levels"]
    pred, level, n = g, "ค่ากลางรวม", 0
    for key, name, lname in (("p_kw1", kw1, "keyword 1 คำ"),
                             ("p_kw2", kw2, "keyword 2 คำ"),
                             ("p_full", _pfull_lookup(meta, full), "ชื่อหัตถการเต็ม")):
        ent = lv[key].get(name)
        if ent and ent[1] >= mc:
            pred, level, n = ent[0], lname, ent[1]
    return pred, level, n


def predict_detail(case: dict, target: str = "room_use") -> dict:
    """ทำนาย + รายละเอียด: predicted_min, n_cases, level, base_hier
    + ช่วงทำนายแบบ split conformal (interval80 / interval90) ถ้าคาลิเบรตไว้"""
    if target not in TARGETS:
        raise ValueError("target ต้องเป็น %s" % (TARGETS,))
    meta, model = _load(target)
    g = meta["global_median"]
    full, kw2, kw1 = normalize_proc(case.get("procedure_name", "") or "")
    surg = _surgeon_key(case.get("surgeon_name", ""), meta)
    h, level, n = _hier_detail(meta, full, kw2, kw1)

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    feat = {
        "hier": h, "surg_med": meta["surg_med"].get(surg, g),
        "surg_n": meta["surg_n"].get(surg, 0), "age": _num(case.get("age")),
        "planned_hour": _num(case.get("planned_hour")), "dow": _num(case.get("dow")),
        "month": _num(case.get("month")),
        "orroom": _num(case.get("orroom", case.get("room_no"))),
        "division": _num(case.get("division", case.get("division_code"))),
        "full_n": meta["full_n"].get(_pfull_lookup(meta, full), 0),
    }
    import numpy as np
    X = np.array([[feat[f] for f in _FEATS]], dtype=float)
    pred = float(h + model.predict(X)[0])
    pred_clip = min(max(pred, 5), 1440)
    q80, q90 = conformal_q(target, "0.80"), conformal_q(target, "0.90")
    return {"predicted_min": int(round(pred_clip)),
            "n_cases": int(n), "level": level, "base_hier": int(round(h)),
            # ช่วงทำนาย split conformal (None = ยังไม่คาลิเบรต target นี้)
            "interval80": _interval(pred_clip, q80),
            "interval90": _interval(pred_clip, q90),
            "conformal": q90 is not None}


def predict(case: dict, target: str = "room_use") -> int:
    """ทำนายเวลา (นาที) ของเคสเดียว

    case: dict — ใช้คีย์ procedure_name (จำเป็น), surgeon_name, division,
                 orroom/room_no, age, planned_hour, dow, month (มีก็ใช้ ไม่มีก็ได้)
    target: 'room_use' (เวลาครองห้อง) หรือ 'surg_time' (เวลาผ่าตัดสุทธิ)
    """
    if target not in TARGETS:
        raise ValueError(f"target ต้องเป็น {TARGETS}")
    meta, model = _load(target)
    g = meta["global_median"]
    full, kw2, kw1 = normalize_proc(case.get("procedure_name", "") or "")
    surg = _surgeon_key(case.get("surgeon_name", ""), meta)
    h = _hier(meta, full, kw2, kw1)

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    feat = {
        "hier": h,
        "surg_med": meta["surg_med"].get(surg, g),
        "surg_n": meta["surg_n"].get(surg, 0),
        "age": num(case.get("age")),
        "planned_hour": num(case.get("planned_hour")),
        "dow": num(case.get("dow")),
        "month": num(case.get("month")),
        "orroom": num(case.get("orroom", case.get("room_no"))),
        "division": num(case.get("division", case.get("division_code"))),
        "full_n": meta["full_n"].get(_pfull_lookup(meta, full), 0),
    }
    import numpy as np
    X = np.array([[feat[f] for f in _FEATS]], dtype=float)
    pred = float(h + model.predict(X)[0])
    return int(round(min(max(pred, 5), 1440)))


def predict_room_use(case: dict) -> int:
    return predict(case, "room_use")


def predict_surgery(case: dict) -> int:
    return predict(case, "surg_time")


if __name__ == "__main__":
    for c in [
        {"procedure_name": "EXCISION OF SEBACEOUS CYST AT SCALP", "surgeon_name": "-",
         "age": 45, "planned_hour": 10, "orroom": 4, "division": 75},
        {"procedure_name": "ESWL", "age": 60, "planned_hour": 9, "orroom": 3},
        {"procedure_name": "LAPAROSCOPIC CHOLECYSTECTOMY", "age": 55, "planned_hour": 13, "orroom": 4},
    ]:
        d = predict_detail(c, "room_use")
        print(f"{c['procedure_name'][:40]:42s} ห้อง={d['predicted_min']:4d} น. "
              f"ช่วง90%={d['interval90']} · ผ่าตัด={predict_surgery(c):4d} น.")
