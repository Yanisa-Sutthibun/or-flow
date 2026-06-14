"""
build_conformal.py — คาลิเบรต Split Conformal Prediction สำหรับช่วงทำนายเวลา
═══════════════════════════════════════════════════════════════════════
สร้างช่วงทำนาย (prediction interval) ทั้ง 2 target:
  - room_use  : เวลาครองห้องผ่าตัด (validation_room_use.csv)
  - surg_time : เวลาผ่าตัดสุทธิ   (validation_surg_time.csv)

หลักการ (split conformal, absolute residual score):
  1. ใช้ชุด hold-out ปี พ.ศ. 2567 (โมเดล deploy honest_v1 เทรน ≤พ.ศ.2566 ทำนาย 2567)
  2. คะแนน nonconformity s_i = |actual_i − predicted_i|
  3. q̂ = ควอนไทล์อันดับ ⌈(n+1)(1−α)⌉/n ของ s (finite-sample correction)
  4. ช่วงทำนาย = [ŷ − q̂, ŷ + q̂] → coverage ≥ 1−α ภายใต้ exchangeability
ตรวจสอบตัวเอง (temporal): คาลิเบรต 60% แรก → วัด coverage 40% หลัง
ผลลัพธ์ → models/honest_v1/conformal.json (ไม่มีข้อมูลผู้ป่วย/บุคลากร)
ใช้:  python build_conformal.py
"""
from __future__ import annotations
import json, math
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent
MDIR = ROOT / "models" / "honest_v1"
OUT = MDIR / "conformal.json"
ALPHAS = (0.20, 0.10, 0.05)            # → coverage 80% / 90% / 95%
TARGETS = ("room_use", "surg_time")


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    n = len(scores)
    k = min(max(math.ceil((n + 1) * (1 - alpha)), 1), n)
    return float(np.sort(scores)[k - 1])


def build_target(target: str) -> dict:
    df = pd.read_csv(MDIR / f"validation_{target}.csv")
    df["op_date"] = pd.to_datetime(df["op_date"], errors="coerce")
    df = df.dropna(subset=["op_date"]).sort_values("op_date").reset_index(drop=True)
    scores = np.abs(df["actual_duration_min"].astype(float).values
                    - df["ai_predicted_min"].astype(float).values)
    n = len(scores)
    q = {f"{1 - a:.2f}": round(conformal_quantile(scores, a), 1) for a in ALPHAS}
    cut = int(n * 0.6)
    s_cal, s_test = scores[:cut], scores[cut:]
    chk = {}
    for a in ALPHAS:
        qh = conformal_quantile(s_cal, a)
        chk[f"{1 - a:.2f}"] = {"q_from_first60pct": round(qh, 1),
                               "coverage_on_last40pct": round(float(np.mean(s_test <= qh)), 3)}
    return {
        "calib_source": f"validation_{target}.csv — hold-out ปี พ.ศ. 2567 "
                        "(honest_v1 เทรน ≤พ.ศ.2566) → split conformal แท้ (same model, out-of-sample)",
        "n_calib": int(n), "q": q,
        "headline": {"mae": round(float(scores.mean()), 1),
                     "median_ae": round(float(np.median(scores)), 1),
                     "within15_pct": round(float(np.mean(scores <= 15) * 100), 1),
                     "within30_pct": round(float(np.mean(scores <= 30) * 100), 1)},
        "temporal_check": {"design": "calibrate 60% แรก (ตามเวลา) → วัด coverage 40% หลัง",
                           "n_calib": int(cut), "n_test": int(n - cut), "results": chk},
        "note": "ช่วงทำนาย = ŷ ± q · coverage การันตีภายใต้ exchangeability; "
                "กับข้อมูลตามเวลาเป็นค่าประมาณ — ดู temporal_check ประกอบ",
    }


def main():
    payload = {"created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "method": "split conformal prediction (absolute residual score, finite-sample quantile)"}
    for t in TARGETS:
        payload[t] = build_target(t)
        h = payload[t]
        print(f"OK {t}: n={h['n_calib']} | q90={h['q']['0.90']} | "
              f"MAE={h['headline']['mae']} | temporal cov90="
              f"{h['temporal_check']['results']['0.90']['coverage_on_last40pct']}")
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("→", OUT)


if __name__ == "__main__":
    main()
