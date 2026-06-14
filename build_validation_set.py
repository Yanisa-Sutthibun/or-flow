"""
build_validation_set.py — ⛔ DEPRECATED (CR-3, 11 มิ.ย. 2026)
═══════════════════════════════════════════════════════════════════════
⛔ เลิกใช้แล้ว! สคริปต์นี้เทรนโมเดล "คนละสเปค" กับตัว deploy (3000 ต้น + early stop)
   แล้วเขียนทับ validation_room_use.csv → ทำให้ conformal q̂ ไม่ตรงกับโมเดลที่ใช้จริง
   (= ต้นเหตุ CR-3) ✅ ใช้ `python train_honest_model.py` แทน — มันสร้าง validation csv
   จาก "โมเดล deploy ตัวเดียวกัน" (≤พ.ศ.2566, 800 ต้น) ให้เอง

(เก็บไฟล์ไว้อ้างอิงประวัติ — ถ้าจำเป็นต้องรันจริง ตั้ง env ALLOW_LEGACY_VALIDATION=1)
───────────────────────────────────────────────────────────────────────
เดิม: เทรน (hier + XGBoost residual) ด้วยปี 2021-2023 → ทำนายปี 2024 (held-out)
แล้วเซฟ (ทำนาย vs จริง) ลง models/honest_v1/validation_room_use.csv

ทำให้หน้า "ความแม่น AI" ในแอป แสดงตัวเลขเดียวกับในเล่ม (MAE ≈ 42 นาที, out-of-sample)
ไม่มีชื่อแพทย์/ผู้ป่วยในไฟล์ (PDPA-safe)

ใช้:  python build_validation_set.py
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from main_or_predictor import normalize_proc, normalize_surgeon

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "models" / "honest_v1"
DATA = ROOT / "data" / "historical" / "main_or_history.csv"
MIN_COUNT = 5
FEATS = ["hier", "surg_med", "surg_n", "age", "planned_hour", "dow", "month",
         "orroom", "division", "full_n"]


def _hhmm(s):
    s = str(s).strip().split(".")[0]
    if not s.isdigit():
        return np.nan
    s = s.zfill(6); h, m = int(s[:2]), int(s[2:4])
    return h * 60 + m if (h <= 23 and m <= 59) else np.nan


def _dur(a, b):
    d = b - a
    return d.where(d >= 0, d + 1440)


def main():
    df = pd.read_csv(DATA, dtype=str, low_memory=False)
    df["dt"] = pd.to_datetime(df["opedate_norm"], errors="coerce")
    df["age_n"] = pd.to_numeric(df["age"], errors="coerce")
    ri = df["roomtimein"].map(_hhmm); ro = df["roomtimeout"].map(_hhmm)
    opst = df["opesttime"].map(_hhmm)
    df["room_use"] = _dur(ri, ro)
    df["planned_hour"] = (opst / 60).round()
    df["dow"] = df["dt"].dt.dayofweek; df["month"] = df["dt"].dt.month
    df["orroom"] = pd.to_numeric(df.get("orroom_sched"), errors="coerce")
    df["division"] = pd.to_numeric(df["division_sched"], errors="coerce")
    nz = df["icd9cm_name"].fillna("").apply(normalize_proc)
    df["p_full"] = nz.apply(lambda x: x[0]); df["p_kw2"] = nz.apply(lambda x: x[1])
    df["p_kw1"] = nz.apply(lambda x: x[2])
    df["surg"] = df["surgstfnm"].fillna("").apply(normalize_surgeon)

    target = "room_use"
    d = df[df[target].between(5, 1440) & df["dt"].notna()].copy()
    tr = d[d["dt"].dt.year <= 2023].copy()
    te = d[d["dt"].dt.year == 2024].copy()
    g = float(tr[target].median())

    med = {lv: tr.groupby(lv)[target].median() for lv in ["p_full", "p_kw2", "p_kw1"]}
    cnt = {lv: tr.groupby(lv).size() for lv in ["p_full", "p_kw2", "p_kw1"]}

    def hier(x):
        pred = np.full(len(x), g, float)
        for lv in ["p_kw1", "p_kw2", "p_full"]:
            c = x[lv].map(cnt[lv]).fillna(0).values
            mv = x[lv].map(med[lv]).values
            use = (c >= MIN_COUNT) & ~pd.isna(mv)
            pred[use] = mv[use]
        return pred

    surg_med = tr.groupby("surg")[target].median()
    surg_n = tr["surg"].value_counts()

    def build(x):
        X = pd.DataFrame(index=x.index)
        X["hier"] = hier(x)
        X["surg_med"] = x["surg"].map(surg_med).fillna(g)
        X["surg_n"] = x["surg"].map(surg_n).fillna(0)
        X["age"] = x["age_n"]; X["planned_hour"] = x["planned_hour"]
        X["dow"] = x["dow"]; X["month"] = x["month"]
        X["orroom"] = x["orroom"]; X["division"] = x["division"]
        X["full_n"] = x["p_full"].map(cnt["p_full"]).fillna(0)
        return X[FEATS]

    h_tr = hier(tr)
    vmask = (tr["dt"].dt.year == 2023).values
    m = XGBRegressor(n_estimators=3000, max_depth=3, learning_rate=0.02, subsample=0.7,
                     colsample_bytree=0.7, min_child_weight=30, reg_lambda=5.0, reg_alpha=1.0,
                     objective="reg:absoluteerror", random_state=42, tree_method="hist",
                     n_jobs=-1, early_stopping_rounds=80, eval_metric="mae")
    Xtr = build(tr)
    m.fit(Xtr[~vmask], (tr[target].values - h_tr)[~vmask],
          eval_set=[(Xtr[vmask], (tr[target].values - h_tr)[vmask])], verbose=False)
    pred = hier(te) + m.predict(build(te))
    pred = np.clip(np.round(pred), 5, 1440).astype(int)
    actual = te[target].values
    mae = float(np.abs(pred - actual).mean())

    out = pd.DataFrame({
        "ai_predicted_min": pred,
        "actual_duration_min": actual.astype(int),
        "procedure_name": te["icd9cm_name"].fillna("UNKNOWN").values,
        "op_type": "elective",          # ทั้งชุดถือเป็น elective (กันถูกกรองออก)
        "op_date": te["opedate_norm"].values,
    })
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "validation_room_use.csv", index=False, encoding="utf-8-sig")
    print(f"OK validation_room_use.csv: n={len(out)} · MAE={mae:.1f} นาที (out-of-sample 2024)")
    print(f"   within15={np.mean(np.abs(pred-actual)<=15)*100:.0f}% · within30={np.mean(np.abs(pred-actual)<=30)*100:.0f}%")


if __name__ == "__main__":
    import os
    if os.environ.get("ALLOW_LEGACY_VALIDATION") != "1":
        raise SystemExit(
            "⛔ DEPRECATED (CR-3): สคริปต์นี้สร้าง validation_room_use.csv จากโมเดล "
            "คนละสเปคกับตัว deploy (3000 ต้น + early stop) → ใช้แล้ว conformal จะไม่ตรง "
            "โมเดลจริงอีก. ใช้ `python train_honest_model.py` แทน. "
            "ถ้าจำเป็นจริง ๆ: ALLOW_LEGACY_VALIDATION=1 python build_validation_set.py")
    main()
