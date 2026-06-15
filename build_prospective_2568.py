"""
build_prospective_2568.py — ผลทำนาย "เวลาครองห้อง" ปี พ.ศ. 2568 (prospective)
═══════════════════════════════════════════════════════════════════════
ทำนายเคสจริงปี 2568 ด้วยโมเดล deploy ตัวปัจจุบัน (honest_v1) — PREDICTION-ONLY
  • ไม่ retrain / ไม่ recalibrate โมเดล (ใช้พารามิเตอร์เดิมที่เทรนจาก ≤พ.ศ.2566)
  • เทียบกับเวลาจริงที่บันทึกใน HIS (data/year68_69_completed.csv)

⚠️ ขอบเขตข้อมูลปี 2568:
  ไฟล์เคสเสร็จปี 68/69 บันทึกเฉพาะ "เวลาครองห้อง" (room-in → room-out)
  ไม่มีเวลาลงมีด/เย็บเสร็จ → จึงทำได้เฉพาะ target = room_use เท่านั้น
  (เวลาผ่าตัดสุทธิ/surg_time ของปี 2568 ไม่มี actual ให้เทียบ)

ผลลัพธ์ → models/honest_v1/validation_room_use_2568.csv
         (คอลัมน์: op_date, ai_predicted_min, actual_duration_min, op_type, procedure_name)
ใช้:  python build_prospective_2568.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

import or_time_model

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "data" / "year68_69_completed.csv"
OUT = ROOT / "models" / "honest_v1" / "validation_room_use_2568.csv"
TARGET_CE_YEAR = 2025          # พ.ศ. 2568


def _hour(s) -> int:
    """แปลง opesttime (HHMMSS) → ชั่วโมง; นอกช่วง 07–22 → ค่ากลาง 9"""
    s = str(s).strip().split(".")[0]
    if not s.isdigit():
        return 9
    h = int(s.zfill(6)[:2])
    return h if 7 <= h <= 22 else 9


def main() -> None:
    df = pd.read_csv(SRC, dtype=str, low_memory=False)
    df.columns = [c.lstrip("﻿") for c in df.columns]
    df["dt"] = pd.to_datetime(df["opedate_norm"], errors="coerce")
    df["actual"] = pd.to_numeric(df["duration_minutes"], errors="coerce")

    rows = []
    for _, r in df.iterrows():
        if r["dt"] is pd.NaT or r["dt"].year != TARGET_CE_YEAR:
            continue
        act = r["actual"]
        if not (act == act) or not (5 <= act <= 1440):   # กรองค่าผิดปกติ
            continue
        try:
            pred = or_time_model.predict_room_use({
                "procedure_name": (r.get("icd9cm_name") or "UNKNOWN"),
                "surgeon_name": (r.get("surgstfnm") or ""),
                "division": (r.get("division_sched") or "75"),
                "orroom": pd.to_numeric(r.get("orroom_sched"), errors="coerce"),
                "age": pd.to_numeric(r.get("age"), errors="coerce"),
                "planned_hour": _hour(r.get("opesttime")),
                "dow": int(r["dt"].dayofweek),
                "month": int(r["dt"].month),
            })
        except Exception:
            pred = None
        if pred is None or not np.isfinite(pred):
            continue
        rows.append({
            "op_date": r["dt"].strftime("%Y-%m-%d"),
            "ai_predicted_min": int(round(float(pred))),
            "actual_duration_min": int(round(float(act))),
            "op_type": "elective",
            "procedure_name": (r.get("icd9cm_name") or ""),
        })

    out = pd.DataFrame(rows)
    err = (out["ai_predicted_min"] - out["actual_duration_min"]).abs()
    print(f"n={len(out)} | MAE={err.mean():.1f} | median={err.median():.1f} | "
          f"within15={(err <= 15).mean() * 100:.0f}% | "
          f"within30={(err <= 30).mean() * 100:.0f}%")
    out.to_csv(OUT, index=False, encoding="utf-8")
    print("→", OUT)


if __name__ == "__main__":
    main()
