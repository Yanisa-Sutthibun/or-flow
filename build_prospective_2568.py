"""
build_prospective_2568.py — ผลทำนาย prospective ปี พ.ศ. 2568 และ 2569 (ทั้ง 2 target)
═══════════════════════════════════════════════════════════════════════
ทำนายเคสจริงปี 2568–2569 ด้วยโมเดล deploy ตัวปัจจุบัน (honest_v1) — PREDICTION-ONLY
  • ไม่ retrain / ไม่ recalibrate (ใช้พารามิเตอร์เดิมที่เทรนจาก ≤พ.ศ.2566)
  • เป็นการแสดง generalization ของเครื่องมือบนข้อมูลปีถัดมา (ไม่ใช่การพัฒนาโมเดลใหม่)
  • เทียบกับเวลาจริงที่บันทึกใน HIS

แหล่งข้อมูล:
  • data/year68_69_completed.csv      → ฐานเคส + age + opesttime + เวลาครองห้อง (ทั้ง 2568, 2569)
  • data/year68/intraopปี68.xls       → เติม opendtime (เวลาผ่าเสร็จ) ของปี 2568
  • data/year69/intraopปี69.xls       → เติม opendtime ของปี 2569
    (ถ้าไฟล์ intraop ปีใดไม่อยู่ → สร้างเฉพาะ room_use ของปีนั้น)

target:
  • room_use  = roomtimeout − roomtimein            (เวลาครองห้อง)
  • surg_time = opendtime − opesttime  (ต้อง roomin ≤ opst ≤ opend ≤ roomout)

ผลลัพธ์ → models/honest_v1/validation_{room_use|surg_time}_{2568|2569}.csv
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
# (ค.ศ. ที่ใช้กรอง, พ.ศ. สำหรับชื่อไฟล์, path ไฟล์ intraop ที่มี opendtime)
YEARS = [
    (2025, 2568, ROOT / "data" / "year68" / "intraopปี68.xls"),
    (2026, 2569, ROOT / "data" / "year69" / "intraopปี69.xls"),
]


def _hhmm(s) -> float:
    s = str(s).strip().split(".")[0]
    if not s.isdigit():
        return np.nan
    s = s.zfill(6)
    h, m = int(s[:2]), int(s[2:4])
    return h * 60 + m if (h <= 23 and m <= 59) else np.nan


def _row(dt, pred, act, r) -> dict:
    return {"op_date": dt.strftime("%Y-%m-%d"),
            "ai_predicted_min": int(round(float(pred))),
            "actual_duration_min": int(round(float(act))),
            "op_type": "elective",
            "procedure_name": (r.get("icd9cm_name") or "")}


def main() -> None:
    comp = pd.read_csv(COMPLETED, dtype=str, low_memory=False)
    comp.columns = [c.lstrip("﻿") for c in comp.columns]
    comp["dt"] = pd.to_datetime(comp["opedate_norm"], errors="coerce")
    comp["hn"] = comp["case_key"].str.split("_").str[0]
    comp["room"] = comp["case_key"].str.split("_").str[2]
    comp["key"] = comp["hn"] + "|" + comp["opedate_norm"] + "|" + comp["room"]

    for ce_year, be_year, intraop in YEARS:
        sub = comp[comp["dt"].dt.year == ce_year].copy()
        if sub.empty:
            print(f"{be_year}: ไม่มีเคสใน completed (ข้าม)")
            continue
        # เติม opendtime จาก intraop ปีนั้น (จับคู่ hn|วันที่|ห้อง — match 100%)
        if intraop.exists():
            intr = pd.read_excel(intraop)
            intr["hn"] = intr["hn"].astype(str).str.split(".").str[0]
            intr["date"] = pd.to_datetime(intr["opedate"], errors="coerce").dt.strftime("%Y-%m-%d")
            intr["room"] = pd.to_numeric(intr["orroom"], errors="coerce").astype("Int64").astype(str)
            intr["key"] = intr["hn"] + "|" + intr["date"] + "|" + intr["room"]
            sub["opendtime"] = sub["key"].map(intr.groupby("key")["opendtime"].first())
        else:
            sub["opendtime"] = np.nan

        rows = {"room_use": [], "surg_time": []}
        for _, r in sub.iterrows():
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
            act_r = pd.to_numeric(r.get("duration_minutes"), errors="coerce")
            if act_r == act_r and 5 <= act_r <= 1440:
                try:
                    pr = or_time_model.predict_room_use(case)
                except Exception:
                    pr = None
                if pr is not None and np.isfinite(pr):
                    rows["room_use"].append(_row(dt, pr, act_r, r))
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

        for tgt, rws in rows.items():
            if not rws:
                print(f"{be_year} {tgt}: ไม่มีข้อมูล (ข้าม)")
                continue
            out = pd.DataFrame(rws)
            e = (out["ai_predicted_min"] - out["actual_duration_min"]).abs()
            print(f"{be_year} {tgt}: n={len(out)} | MAE={e.mean():.1f} | "
                  f"median={e.median():.1f} | within15={(e <= 15).mean() * 100:.0f}%")
            out.to_csv(OUT / f"validation_{tgt}_{be_year}.csv", index=False, encoding="utf-8")


if __name__ == "__main__":
    main()
