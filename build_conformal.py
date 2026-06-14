"""
build_conformal.py — คาลิเบรต Split Conformal Prediction สำหรับช่วงทำนายเวลา
═══════════════════════════════════════════════════════════════════════
หลักการ (split conformal, absolute residual score):
  1. ใช้ชุดคาลิเบรตที่โมเดล "ไม่เคยเห็นตอนเทรน" = ปี พ.ศ. 2567 hold-out
     (validation_room_use.csv — สร้างโดย train_honest_model.py: โมเดล deploy
     ตัวเดียวกัน (honest_v1) เทรน ≤พ.ศ.2566 ทำนาย 2567 → q̂ ของโมเดลที่ใช้จริง)
  2. คะแนน nonconformity s_i = |actual_i − predicted_i|
  3. q̂ = ควอนไทล์อันดับ ⌈(n+1)(1−α)⌉/n ของ s (finite-sample correction)
  4. ช่วงทำนายของเคสใหม่ = [ŷ − q̂, ŷ + q̂] → การันตี coverage ≥ 1−α
     ภายใต้สมมติฐาน exchangeability (ข้อมูลอนุกรมเวลา = โดยประมาณ
     ต้องรายงาน empirical coverage บนข้อมูลปีถัดไปประกอบ)

ตรวจสอบตัวเอง (temporal sanity check):
  แบ่งชุดคาลิเบรตตามเวลา 60/40 → คาลิเบรตจากครึ่งแรก วัด coverage ครึ่งหลัง
  ถ้า coverage ใกล้ nominal แปลว่า exchangeability ใช้ได้ในข้อมูลชุดนี้

ผลลัพธ์ → models/honest_v1/conformal.json (ไม่มีข้อมูลผู้ป่วย/บุคลากร)
ใช้:  python build_conformal.py
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "models" / "honest_v1" / "validation_room_use.csv"
OUT = ROOT / "models" / "honest_v1" / "conformal.json"

ALPHAS = (0.20, 0.10, 0.05)          # → coverage 80% / 90% / 95%


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """ควอนไทล์แบบ finite-sample: อันดับ ⌈(n+1)(1−α)⌉ ของคะแนนเรียงน้อย→มาก"""
    n = len(scores)
    k = math.ceil((n + 1) * (1 - alpha))
    k = min(max(k, 1), n)
    return float(np.sort(scores)[k - 1])


def main():
    df = pd.read_csv(SRC)
    df["op_date"] = pd.to_datetime(df["op_date"], errors="coerce")
    df = df.dropna(subset=["op_date"]).sort_values("op_date").reset_index(drop=True)
    pred = df["ai_predicted_min"].astype(float).values
    actual = df["actual_duration_min"].astype(float).values
    scores = np.abs(actual - pred)
    n = len(scores)

    q = {f"{1 - a:.2f}": round(conformal_quantile(scores, a), 1) for a in ALPHAS}

    # temporal sanity check: คาลิเบรตครึ่งแรก (60%) → วัด coverage ครึ่งหลัง (40%)
    cut = int(n * 0.6)
    s_cal, s_test = scores[:cut], scores[cut:]
    chk = {}
    for a in ALPHAS:
        q_half = conformal_quantile(s_cal, a)
        chk[f"{1 - a:.2f}"] = {
            "q_from_first60pct": round(q_half, 1),
            "coverage_on_last40pct": round(float(np.mean(s_test <= q_half)), 3),
        }

    payload = {
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": "split conformal prediction (absolute residual score, "
                  "finite-sample quantile)",
        "room_use": {
            "calib_source": "validation_room_use.csv — hold-out ปี พ.ศ. 2567 "
                            "ทำนายด้วยโมเดล deploy ตัวเดียวกัน (honest_v1 เทรน ≤พ.ศ.2566, "
                            "XGB 800 ต้น) → split conformal แท้ (same model, out-of-sample)",
            "n_calib": int(n),
            "q": q,                                  # ครึ่งกว้างช่วง (นาที) ต่อระดับ coverage
            "headline": {
                "mae": round(float(scores.mean()), 1),
                "median_ae": round(float(np.median(scores)), 1),
                "within15_pct": round(float(np.mean(scores <= 15) * 100), 1),
                "within30_pct": round(float(np.mean(scores <= 30) * 100), 1),
            },
            "temporal_check": {
                "design": "calibrate 60% แรก (ตามเวลา) → วัด coverage 40% หลัง",
                "n_calib": int(cut), "n_test": int(n - cut),
                "results": chk,
            },
            "note": "ช่วงทำนาย = ŷ ± q · coverage การันตีภายใต้ exchangeability; "
                    "กับข้อมูลตามเวลาเป็นค่าประมาณ — ดู temporal_check และรายงาน "
                    "empirical coverage บนข้อมูลปีถัดไปประกอบ",
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK conformal.json — n={n}")
    print("  q (ครึ่งกว้างช่วง):", q)
    print("  temporal check:", {k: v["coverage_on_last40pct"] for k, v in chk.items()})


if __name__ == "__main__":
    main()
