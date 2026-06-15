"""
build_prospective_2568.py — ผลทำนายปี พ.ศ. 2568 (prospective) ทั้ง 2 target
═══════════════════════════════════════════════════════════════════════
ทำนายเคสจริงปี 2568 ด้วยโมเดล deploy ตัวปัจจุบัน (honest_v1) — PREDICTION-ONLY
  • ไม่ retrain / ไม่ recalibrate (ใช้พารามิเตอร์เดิมที่เทรนจาก ≤พ.ศ.2566)
  • เทียบกับเวลาจริงที่บันทึกใน HIS

แหล่งข้อมูล (ปี 2568):
  • data/year68_69_completed.csv      → ฐานเคส + age + opesttime + เวลาครองห้อง
  • data/year68/intraopปี68.xls       → เติม opendtime (เวลาผ่าเสร็จ) เพื่อคำนวณเวลาผ่าตัดสุทธิ
    (ถ้าไฟล์ intraop ไม่อยู่ใน repo → จะสร้างเฉพาะ room_use)

target:
  • room_use  = roomtimeout − roomtimein            (เวลาครองห้อง)
  • surg_time = opendtime − opesttime  (ต้อง roomin ≤ opst ≤ opend ≤ roomout)

ผลลัพธ์ → models/honest_v1/validation_room_use_2568.csv
         models/honest_v1/validation_surg_time_2568.csv
  คอลัมน์: op_date, ai_predicted_min, actual_duration_min, op_type, procedure_name
ใช้:  python build_prospective_2568.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

import or_time_model

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "models" / "honest_v1"
COMPLETED = ROOT / "data" / "year68_69_completed.csv"
# ไฟล์ intraop ปี 68 (มี opendtime) — วางไว้ที่ data/year68/ ; ถ้าไม่มีจะข้าม surg_time
INTRAOP68 = next((p for p in [ROOT / "data" / "year68" / "intraopปี68.xls",
                              ROOT / "data" / "intraopปี68.xls"] if p.exists()), None)
TARGET_CE_YEAR = 2025          # พ.ศ. 2568


def _hhmm(s) -> float:
    s = str(s).strip().split(".")[0]
    if not s.isdigit():
        return np.nan
    s = s.zfill(6)
    h, m = int(s[:2]), int(s[2:4])
    return h * 60 + m if (h <= 23 and m <= 59) else np.nan


def main() -> None:
    comp = pd.read_csv(COMPLETED, dtype=str, low_memory=False)
    comp.columns = [c.lstrip("﻿") for c in comp.columns]
    comp["dt"] = pd.to_datetime(comp["opedate_norm"], errors="coerce")
    comp = comp[comp["dt"].dt.year == TARGET_CE_YEAR].copy()
    comp["hn"] = comp["case_key"].str.split("_").str[0]
    comp["room"] = comp["case_key"].str.split("_").str[2]
    comp["key"] = comp["hn"] + "|" + comp["opedate_norm"] + "|" + comp["room"]

    # เติม opendtime จาก intraop ปี 68 (จับคู่ด้วย hn|วันที่|ห้อง — match 100%)
    if INTRAOP68 is not None:
        intr = pd.read_excel(INTRAOP68)
        intr["hn"] = intr["hn"].astype(str).str.split(".").str[0]
        intr["date"] = pd.to_datetime(intr["opedate"], errors="coerce").dt.strftime("%Y-%m-%d")
        intr["room"] = pd.to_numeric(intr["orroom"], errors="coerce").astype("Int64").astype(str)
        intr["key"] = intr["hn"] + "|" + intr["date"] + "|" + intr["room"]
        comp["opendtime"] = comp["key"].map(intr.groupby("key")["opendtime"].first())
    else:
        comp["opendtime"] = np.nan

    rows = {"room_use": [], "surg_time": []}
    for _, r in comp.iterrows():
        dt = r["dt"]
        opst = _hhmm(r.get("opesttime"))
        case = {
            "procedure_name": (r.get("icd9cm_name") or "UNKNOWN"),
            "surgeon_name": (r.get("surgstfnm") or ""),
            "division": (r.get("division_sched") or "75"),
            "orroom": pd.to_numeric(r.get("orroom_sched"), errors="coerce"),
            "age": pd.to_numeric(r.get("age"), errors="coerce"),
            "planned_hour": int(opst // 60) if opst == opst else 9,
            "dow": int(dt.dayofweek), "month": int(dt.month),
        }
        # room_use
        act_r = pd.to_numeric(r.get("duration_minutes"), errors="coerce")
        if act_r == act_r and 5 <= act_r <= 1440:
            try:
                pr = or_time_model.predict_room_use(case)
            except Exception:
                pr = None
            if pr is not None and np.isfinite(pr):
                rows["room_use"].append(_row(dt, pr, act_r, r))
        # surg_time
        ri = pd.to_numeric(r.get("roomtimein_min"), errors="coerce")
        ro = pd.to_numeric(r.get("roomtimeout_min"), errors="coerce")
        opend = _hhmm(r.get("opendtime"))
        if all(v == v for v in [ri, ro, opst, opend]):
            st = opend - opst
            st = st + 1440 if st < 0 else st
            if (ri <= opst <= opend <= ro) and 5 <= st <= 1440:
                try:
                    ps = or_time_model.predict(case, "surg_time")
                except Exception:
                    ps = None
                if ps is not None and np.isfinite(ps):
                    rows["surg_time"].append(_row(dt, ps, st, r))

    for name, rws in rows.items():
        if not rws:
            print(f"{name}: ไม่มีข้อมูล (ข้าม)")
            continue
        out = pd.DataFrame(rws)
        e = (out["ai_predicted_min"] - out["actual_duration_min"]).abs()
        print(f"{name}: n={len(out)} | MAE={e.mean():.1f} | median={e.median():.1f} | "
              f"within15={(e <= 15).mean() * 100:.0f}%")
        out.to_csv(OUT / f"validation_{name}_2568.csv", index=False, encoding="utf-8")


def _row(dt, pred, act, r) -> dict:
    return {"op_date": dt.strftime("%Y-%m-%d"),
            "ai_predicted_min": int(round(float(pred))),
            "actual_duration_min": int(round(float(act))),
            "op_type": "elective",
            "procedure_name": (r.get("icd9cm_name") or "")}


if __name__ == "__main__":
    main()
