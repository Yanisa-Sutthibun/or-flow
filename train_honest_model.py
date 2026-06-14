"""
train_honest_model.py — เทรน + เซฟโมเดล honest (hier median + XGBoost residual)
═══════════════════════════════════════════════════════════════════════
สร้าง artifacts ใน models/honest_v1/ ทั้ง 2 target (room_use, surg_time)
🔒 CR-3: เทรน "เฉพาะ พ.ศ. 2564–2566 (ค.ศ. ≤2023)" — กันปี 2567 leak
   ปี 2567 (ค.ศ. 2024) ถูกกันไว้เป็น hold-out → ทดสอบ + คาลิเบรต conformal
   ด้วย "โมเดลตัวนี้เอง" → โมเดลที่ deploy = ที่ประเมิน = ที่คาลิเบรตช่วง ±นาที

ผล + ช่วง conformal มาจากการทำนาย hold-out 2567 ด้วยโมเดลนี้:
  → models/honest_v1/validation_room_use.csv → build_conformal.py
  ดู docs/CR3_HONEST_MODEL_FIX_2026-06-11.md

ใช้:  python train_honest_model.py
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from xgboost import XGBRegressor

from main_or_predictor import normalize_proc, normalize_surgeon

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "models" / "honest_v1"
DATA = ROOT / "data" / "historical" / "main_or_history.csv"
MIN_COUNT = 5
FEATS = ["hier", "surg_med", "surg_n", "age", "planned_hour", "dow", "month",
         "orroom", "division", "full_n"]
TRAIN_MAX_CE = 2023   # 🔒 เทรนถึง ค.ศ. 2023 = พ.ศ. 2566 (ไม่เกินนี้)
HOLDOUT_CE = 2024     # 🎯 กันไว้ทดสอบ/คาลิเบรต = ค.ศ. 2024 = พ.ศ. 2567


def _hhmm(s):
    s = str(s).strip().split(".")[0]
    if not s.isdigit():
        return np.nan
    s = s.zfill(6)
    h, m = int(s[:2]), int(s[2:4])
    return h * 60 + m if (h <= 23 and m <= 59) else np.nan


def _dur(a, b):
    d = b - a
    return d.where(d >= 0, d + 1440)


def _load() -> pd.DataFrame:
    df = pd.read_csv(DATA, dtype=str, low_memory=False)
    # 🔁 M-11: dedup แถวซ้ำด้วย case_key (เก็บแถวข้อมูลครบสุด) — แบบเดียวกับ main_or_predictor
    if "case_key" in df.columns:
        df["_c"] = df[["icd9cm_name", "icd10_name", "surgstfnm"]].notna().sum(axis=1)
        df = (df.sort_values(["case_key", "_c"], ascending=[True, False])
                .drop_duplicates("case_key").drop(columns="_c").reset_index(drop=True))
    df["dt"] = pd.to_datetime(df["opedate_norm"], errors="coerce")
    df["age_n"] = pd.to_numeric(df["age"], errors="coerce")
    ri = df["roomtimein"].map(_hhmm); ro = df["roomtimeout"].map(_hhmm)
    opst = df["opesttime"].map(_hhmm); opend = df["opendtime"].map(_hhmm)
    df["room_use"] = _dur(ri, ro)
    ok = (ri <= opst) & (opst <= opend) & (opend <= ro)
    df["surg_time"] = _dur(opst, opend).where(ok)
    df["planned_hour"] = (opst / 60).round()
    df["dow"] = df["dt"].dt.dayofweek; df["month"] = df["dt"].dt.month
    df["orroom"] = pd.to_numeric(df.get("orroom_sched"), errors="coerce")
    df["division"] = pd.to_numeric(df["division_sched"], errors="coerce")
    nz = df["icd9cm_name"].fillna("").apply(normalize_proc)
    df["p_full"] = nz.apply(lambda x: x[0]); df["p_kw2"] = nz.apply(lambda x: x[1])
    df["p_kw1"] = nz.apply(lambda x: x[2])
    df["surg"] = df["surgstfnm"].fillna("").apply(normalize_surgeon)
    return df


def _hier_pred(x, tables, g):
    pred = np.full(len(x), g, float)
    for lv in ["p_kw1", "p_kw2", "p_full"]:   # กว้าง → เฉพาะ (เฉพาะชนะถ้าข้อมูลพอ)
        med = {k: v[0] for k, v in tables[lv].items()}
        cnt = {k: v[1] for k, v in tables[lv].items()}
        c = x[lv].map(cnt).fillna(0).values
        mv = x[lv].map(med).values
        use = (c >= MIN_COUNT) & ~pd.isna(mv)
        pred[use] = mv[use]
    return pred


def _features(d, h, _n2c, surg_med, surg_n, full_n, g):
    """สร้างเมทริกซ์ฟีเจอร์ (ลำดับตาม FEATS) — ใช้ทั้งตอนเทรน และตอนทำนาย hold-out
    ให้เหมือนกันเป๊ะ เพื่อให้ residual ที่ใช้คาลิเบรต = ของโมเดล deploy ตัวจริง (CR-3)"""
    X = pd.DataFrame(index=d.index)
    X["hier"] = h
    X["surg_med"] = d["surg"].map(_n2c).map(surg_med).fillna(
        d["surg"].map(surg_med)).fillna(g)
    X["surg_n"] = d["surg"].map(_n2c).map(surg_n).fillna(
        d["surg"].map(surg_n)).fillna(0)
    X["age"] = d["age_n"]; X["planned_hour"] = d["planned_hour"]
    X["dow"] = d["dow"]; X["month"] = d["month"]
    X["orroom"] = d["orroom"]; X["division"] = d["division"]
    X["full_n"] = d["p_full"].map(full_n).fillna(0)
    return X[FEATS]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = _load()
    # 🔒 CR-3: เทรนเฉพาะ ≤2566 (ค.ศ.≤2023) · กัน 2567 (ค.ศ.2024) ไว้ hold-out
    df_tr = df[df["dt"].dt.year <= TRAIN_MAX_CE].copy()
    df_te = df[df["dt"].dt.year == HOLDOUT_CE].copy()
    print(f"train ≤{TRAIN_MAX_CE} (พ.ศ.≤2566): {len(df_tr)} แถว · "
          f"hold-out {HOLDOUT_CE} (พ.ศ.2567): {len(df_te)} แถว")
    summary = {}
    for target in ["room_use", "surg_time"]:
        d = df_tr[df_tr[target].between(5, 1440) & df_tr["dt"].notna()].copy()
        g = float(d[target].median())
        tables = {lv: {k: [float(v), int(d.groupby(lv).size()[k])]
                       for k, v in d.groupby(lv)[target].median().items()}
                  for lv in ["p_full", "p_kw2", "p_kw1"]}
        surg_med = d.groupby("surg")[target].median().to_dict()
        surg_n = d["surg"].value_counts().to_dict()
        full_n = d["p_full"].value_counts().to_dict()

        # 🔒 mask key ชื่อแพทย์ → SURG_xxx ก่อนเขียน artifact (PDPA บุคลากร)
        #    การเทรนยังใช้ชื่อจริง (ผ่าน d["surg"]) — เฉพาะ "key ในไฟล์" ที่ถูกแปลง
        #    predict-time: or_time_model._surgeon_key แปลงชื่อ→รหัสให้เอง
        from mask_model_artifacts import build_name2code
        _n2c = build_name2code(sorted(set(surg_med) | set(surg_n)))
        surg_med = {_n2c.get(k, k): v for k, v in surg_med.items()}
        surg_n = {_n2c.get(k, k): v for k, v in surg_n.items()}

        json.dump({"target": target, "global_median": g, "min_count": MIN_COUNT,
                   "levels": tables, "surg_keys_masked": True,
                   "surg_med": {k: float(v) for k, v in surg_med.items()},
                   "surg_n": {k: int(v) for k, v in surg_n.items()},
                   "full_n": {k: int(v) for k, v in full_n.items()}, "feats": FEATS},
                  open(OUT / f"hier_{target}.json", "w", encoding="utf-8"), ensure_ascii=False)
        h = _hier_pred(d, tables, g)
        X = _features(d, h, _n2c, surg_med, surg_n, full_n, g)
        m = XGBRegressor(n_estimators=800, max_depth=3, learning_rate=0.02,
                         subsample=0.7, colsample_bytree=0.7, min_child_weight=30,
                         reg_lambda=5.0, reg_alpha=1.0, objective="reg:absoluteerror",
                         random_state=42, tree_method="hist", n_jobs=-1)
        m.fit(X, d[target].values - h)
        joblib.dump(m, OUT / f"resid_{target}.pkl")
        summary[target] = {"n_train": len(d), "global_median": round(g, 1)}
        print(f"OK {target}: train {len(d)} เคส (≤{TRAIN_MAX_CE}) -> hier_{target}.json + resid_{target}.pkl")

        # 🎯 CR-3: ทำนาย hold-out 2567 ด้วย "โมเดลตัวนี้เอง" → ชุดคาลิเบรต conformal + ผลทดสอบ
        te = df_te[df_te[target].between(5, 1440) & df_te["dt"].notna()].copy()
        if len(te):
            h_te = _hier_pred(te, tables, g)
            pred_te = h_te + m.predict(_features(te, h_te, _n2c, surg_med, surg_n, full_n, g))
            pred_te = np.clip(pred_te, 5, 1440)          # ให้ตรงกับ serving (pred_clip)
            ae = np.abs(pred_te - te[target].values)
            summary[target]["test_2567"] = {
                "n_test": int(len(te)), "mae": round(float(ae.mean()), 1),
                "median_ae": round(float(np.median(ae)), 1)}
            print(f"   hold-out 2567: n={len(te)} · MAE={ae.mean():.1f} · medAE={np.median(ae):.1f}")
            pd.DataFrame({"op_date": te["dt"].dt.date.astype(str),
                          "ai_predicted_min": np.round(pred_te, 1),
                          "actual_duration_min": te[target].values,
                          # 🏷️ เพิ่มชื่อหัตถการ → ใช้ทำ baseline "ค่าเฉลี่ยต่อหัตถการ" ในแท็บ AI
                          "procedure_name": te["icd9cm_name"].fillna("UNKNOWN").values}
                         ).to_csv(OUT / f"validation_{target}.csv", index=False)
    json.dump(summary, open(OUT / "meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("artifacts ->", OUT)


if __name__ == "__main__":
    main()
