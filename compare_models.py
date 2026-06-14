"""
compare_models.py — Benchmark เปรียบเทียบโมเดลทำนายเวลา OR (สำหรับตอบกรรมการสอบ)
═══════════════════════════════════════════════════════════════════════
คำถามที่ต้องตอบ: "ทำไมเลือก hierarchical median + XGBoost residual?
                  ทำไมไม่ใช้ Random Forest / XGBoost ตรงๆ?"

ระเบียบวิธี (ขอบเขต ethics: ข้อมูล พ.ศ. 2564-2567):
  - Matched cohort: ใช้เฉพาะเคสที่เวลา "ครบ+สมเหตุสมผลทั้งสองนิยาม"
    → ทุกตาราง n เท่ากัน (room_use และ surg_time ใช้เคสชุดเดียวกัน)
  - Temporal split: เทรน พ.ศ. 2564-2566 → ทดสอบ พ.ศ. 2567 (ไม่มี random split)
  - encoding/median ทุกตัวคำนวณจาก "ชุดเทรนเท่านั้น" (กัน data leakage)
  - ทุกโมเดลเห็นข้อมูล (information) ชุดเดียวกัน — ต่างกันแค่อัลกอริทึม → เทียบแฟร์
  - seed = 42 ทุกตัว

โมเดลที่เทียบ (7 + 1 ภาคผนวก):
  1. Naive          : มัธยฐานรวมค่าเดียว (baseline ต่ำสุด)
  2. ProcMedian     : มัธยฐานต่อหัตถการ (ชื่อเต็ม; ไม่เจอ → ค่ากลางรวม)
  3. Hier           : มัธยฐานลำดับชั้น (ชื่อเต็ม→kw2→kw1→รวม, min_count=5)
  4. RandomForest   : RF บน features ชุดเต็ม (ทำนาย y ตรงๆ)
  5. XGBoost        : XGB บน features ชุดเดียวกัน (ทำนาย y ตรงๆ)
  6. Hier+RF resid  : RF เรียน "ส่วนต่างจาก hier"
  7. Hier+XGB resid : XGB เรียน "ส่วนต่างจาก hier"   ← โมเดลที่เลือก (honest_v1)
  A. ข้อ 7 + random split (ภาคผนวก) : สาธิตว่า random split ให้ตัวเลขสวยเกินจริง

ใช้:  python compare_models.py        (ผล markdown → stdout + docs/_model_comparison_raw.md)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from main_or_predictor import normalize_proc, normalize_surgeon

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "historical" / "main_or_history.csv"
OUT_RAW = ROOT / "docs" / "_model_comparison_raw.md"
MIN_COUNT = 5
SEED = 42

# feature ชุดเดียวกับ honest_v1 เป๊ะ (train_honest_model.FEATS) — ใช้กับโมเดล ML ทุกตัว
# เพื่อให้ "ข้อมูลที่เห็นเท่ากันหมด ต่างกันแค่อัลกอริทึม/สถาปัตยกรรม"
FEATS = ["hier", "surg_med", "surg_n", "age", "planned_hour", "dow", "month",
         "orroom", "division", "full_n"]


# ───────────────────────── data prep (เหมือน build_validation_set) ─────────────────────────
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


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA, dtype=str, low_memory=False)
    # 🔁 M-11: dedup แถวซ้ำด้วย case_key (เก็บแถวข้อมูลครบสุด) — แบบเดียวกับ main_or_predictor
    if "case_key" in df.columns:
        df["_c"] = df[["icd9cm_name", "icd10_name", "surgstfnm"]].notna().sum(axis=1)
        df = (df.sort_values(["case_key", "_c"], ascending=[True, False])
                .drop_duplicates("case_key").drop(columns="_c").reset_index(drop=True))
    df["dt"] = pd.to_datetime(df["opedate_norm"], errors="coerce")
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    ri = df["roomtimein"].map(_hhmm); ro = df["roomtimeout"].map(_hhmm)
    opst = df["opesttime"].map(_hhmm); opend = df["opendtime"].map(_hhmm)
    df["room_use"] = _dur(ri, ro)
    ok = (ri <= opst) & (opst <= opend) & (opend <= ro)
    df["surg_time"] = _dur(opst, opend).where(ok)
    df["planned_hour"] = (opst / 60).round()
    df["dow"] = df["dt"].dt.dayofweek
    df["month"] = df["dt"].dt.month
    df["orroom"] = pd.to_numeric(df.get("orroom_sched"), errors="coerce")
    df["division"] = pd.to_numeric(df["division_sched"], errors="coerce")
    nz = df["icd9cm_name"].fillna("").apply(normalize_proc)
    df["p_full"] = nz.apply(lambda x: x[0])
    df["p_kw2"] = nz.apply(lambda x: x[1])
    df["p_kw1"] = nz.apply(lambda x: x[2])
    df["surg"] = df["surgstfnm"].fillna("").apply(normalize_surgeon)
    return df


def metrics(y, p) -> dict:
    """เมตริกมาตรฐานงาน OR duration prediction: MAE, RMSE, R², MAPE
    + ตัวชี้วัดเชิงปฏิบัติ: MedAE, สัดส่วนคลาด ≤15/≤30 นาที"""
    y = np.asarray(y, float); p = np.asarray(p, float)
    e = np.abs(y - p)
    ss_res = float(((y - p) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"MAE": round(float(e.mean()), 1),
            "RMSE": round(float(np.sqrt(((y - p) ** 2).mean())), 1),
            "R²": round(1.0 - ss_res / ss_tot, 3),
            "MAPE": round(float((e / y).mean() * 100), 1),   # y ≥ 5 เสมอ (กรองแล้ว)
            "MedAE": round(float(np.median(e)), 1),
            "≤15": round(float((e <= 15).mean() * 100), 1),
            "≤30": round(float((e <= 30).mean() * 100), 1)}


# ───────────────────────── encoders (fit จาก train เท่านั้น) ─────────────────────────
class Enc:
    def __init__(self, tr: pd.DataFrame, target: str):
        self.g = float(tr[target].median())
        self.med = {lv: tr.groupby(lv)[target].median() for lv in ("p_full", "p_kw2", "p_kw1")}
        self.cnt = {lv: tr.groupby(lv).size() for lv in ("p_full", "p_kw2", "p_kw1")}
        self.surg_med = tr.groupby("surg")[target].median()
        self.surg_n = tr["surg"].value_counts()

    def hier(self, x: pd.DataFrame) -> np.ndarray:
        pred = np.full(len(x), self.g, float)
        for lv in ("p_kw1", "p_kw2", "p_full"):          # กว้าง → เฉพาะ (เฉพาะชนะ)
            c = x[lv].map(self.cnt[lv]).fillna(0).values
            mv = x[lv].map(self.med[lv]).values
            use = (c >= MIN_COUNT) & ~pd.isna(mv)
            pred[use] = mv[use]
        return pred

    def proc_median(self, x: pd.DataFrame) -> np.ndarray:
        mv = x["p_full"].map(self.med["p_full"]).values
        return np.where(pd.isna(mv), self.g, mv)

    def X(self, x: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(index=x.index)
        X["hier"] = self.hier(x)
        X["surg_med"] = x["surg"].map(self.surg_med).fillna(self.g)
        X["surg_n"] = x["surg"].map(self.surg_n).fillna(0)
        X["full_n"] = x["p_full"].map(self.cnt["p_full"]).fillna(0)
        for c in ("age", "planned_hour", "dow", "month", "orroom", "division"):
            X[c] = x[c]
        return X[FEATS]


def make_rf():
    from sklearn.ensemble import RandomForestRegressor
    return RandomForestRegressor(n_estimators=400, min_samples_leaf=5,
                                 random_state=SEED, n_jobs=-1)


def make_xgb():
    """🔒 CR-3: สเปคเดียวกับโมเดลที่ deploy จริง (train_honest_model.py / honest_v1):
    XGBoost 800 ต้น คงที่ ไม่ใช้ early stopping → ตารางเปรียบเทียบ = โมเดลที่ใช้งานจริง"""
    from xgboost import XGBRegressor
    return XGBRegressor(n_estimators=800, max_depth=3, learning_rate=0.02,
                        subsample=0.7, colsample_bytree=0.7, min_child_weight=30,
                        reg_lambda=5.0, reg_alpha=1.0, objective="reg:absoluteerror",
                        random_state=SEED, tree_method="hist", n_jobs=-1)


def _fit_es(model, Xtr, ytr, vmask):
    """fit แบบ build_validation_set: เทรนส่วน ≤2565 · early-stop ด้วยปี 2566"""
    model.fit(Xtr[~vmask], ytr[~vmask], eval_set=[(Xtr[vmask], ytr[vmask])],
              verbose=False)
    return model


def run_target(d: pd.DataFrame, target: str) -> tuple[list, dict]:
    """d = matched cohort ที่กรองแล้วจาก main() — ทั้งสอง target ใช้เคสชุดเดียวกัน"""
    tr = d[d["dt"].dt.year <= 2023].copy()
    te = d[d["dt"].dt.year == 2024].copy()
    y_tr, y_te = tr[target].values, te[target].values
    enc = Enc(tr, target)
    Xtr, Xte = enc.X(tr), enc.X(te)
    h_tr, h_te = enc.hier(tr), enc.hier(te)
    vmask = (tr["dt"].dt.year == 2023).values     # eval fold สำหรับ early stopping

    rows = []

    def add(name, pred, note=""):
        pred = np.clip(pred, 5, 1440)
        rows.append({"โมเดล": name, **metrics(y_te, pred), "หมายเหตุ": note})
        return pred

    add("1. Naive (มัธยฐานรวม)", np.full(len(te), enc.g))
    add("2. มัธยฐานต่อหัตถการ", enc.proc_median(te))
    add("3. มัธยฐานลำดับชั้น (hier)", h_te, "อธิบายง่าย ไม่ต้องเทรน")

    rf = make_rf(); rf.fit(Xtr, y_tr)
    rf_pred = add("4. Random Forest (ทำนาย y ตรงๆ)", rf.predict(Xte), "feature ชุดเดียวกับข้อ 7")

    xg = make_xgb(); xg.fit(Xtr, y_tr)
    add("5. XGBoost (ทำนาย y ตรงๆ)", xg.predict(Xte), "feature ชุดเดียวกับข้อ 7")

    rf_r = make_rf(); rf_r.fit(Xtr, y_tr - h_tr)
    add("6. hier + RF residual", h_te + rf_r.predict(Xte))

    xg_r = make_xgb(); xg_r.fit(Xtr, y_tr - h_tr)
    p_chosen = add("7. hier + XGBoost residual ★", h_te + xg_r.predict(Xte),
                   "โมเดลที่เลือก (honest_v1)")

    # ── ภาคผนวก: random split (สาธิต leakage จากการแบ่งผิดวิธี) ──
    rng = np.random.RandomState(SEED)
    idx = rng.permutation(len(d))
    cut = int(len(d) * 0.8)
    rtr, rte = d.iloc[idx[:cut]].copy(), d.iloc[idx[cut:]].copy()
    enc_r = Enc(rtr, target)
    h_rtr, h_rte = enc_r.hier(rtr), enc_r.hier(rte)
    from xgboost import XGBRegressor
    xg2 = XGBRegressor(n_estimators=800, max_depth=3, learning_rate=0.02,
                       subsample=0.7, colsample_bytree=0.7, min_child_weight=30,
                       reg_lambda=5.0, reg_alpha=1.0, objective="reg:absoluteerror",
                       random_state=SEED, tree_method="hist", n_jobs=-1)
    xg2.fit(enc_r.X(rtr), rtr[target].values - h_rtr)
    rows.append({"โมเดล": "A. โมเดลข้อ 7 แต่แบ่งแบบ random (ผิดวิธี)",
                 **metrics(rte[target].values,
                           np.clip(h_rte + xg2.predict(enc_r.X(rte)), 5, 1440)),
                 "หมายเหตุ": "เคสร่วมยุค/หัตถการเดียวกันรั่วข้าม train↔test → ตัวเลขสวยเกินจริง"})

    info = {
        "n_train": len(tr), "n_test": len(te),
        "train_years": sorted(tr["dt"].dt.year.unique().tolist()),
        "unseen_full": round(float((~te["p_full"].isin(set(tr["p_full"]))).mean() * 100), 1),
        "unseen_kw1": round(float((~te["p_kw1"].isin(set(tr["p_kw1"]))).mean() * 100), 1),
        "global_median": enc.g,
        "chosen_pred": p_chosen,
        "rf_pred": rf_pred, "y_test": y_te,
    }
    return rows, info


def fmt_table(rows) -> str:
    cols = ["โมเดล", "MAE", "RMSE", "R²", "MAPE", "MedAE", "≤15", "≤30", "หมายเหตุ"]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def main():
    df = load()
    # ── Matched cohort: ใช้เฉพาะเคสที่เวลา "ครบ+สมเหตุสมผลทั้งสองนิยาม" ──
    #    → n เท่ากันทุกตาราง (อธิบาย exclusion ประโยคเดียวจบ)
    dated = df[df["dt"].notna()]
    ok = (dated["room_use"].between(5, 1440) & dated["surg_time"].between(5, 1440))
    d = dated[ok].copy()
    for yr_label, n_all, n_ok in (
            ("เทรน 2564-2566", int((dated["dt"].dt.year <= 2023).sum()),
             int((d["dt"].dt.year <= 2023).sum())),
            ("ทดสอบ 2567", int((dated["dt"].dt.year == 2024).sum()),
             int((d["dt"].dt.year == 2024).sum()))):
        print(f"[matched cohort] {yr_label}: {n_all:,} เคส → คัดเวลาไม่ครบ/ขัดแย้งออก "
              f"{n_all - n_ok:,} ({(n_all - n_ok) / n_all * 100:.1f}%) → ใช้ {n_ok:,} เคส")

    report = ["# ผลเปรียบเทียบโมเดล (รันจริง seed=42 · เทรน 2564-2566 → ทดสอบ 2567)\n",
              "Matched cohort — ทุกตาราง n เท่ากัน (เคสที่เวลาครบ+สมเหตุสมผลทั้งสองนิยาม)\n"]
    for target, label in (("room_use", "เวลาครองห้องผ่าตัด (room-in → room-out)"),
                          ("surg_time", "เวลาผ่าตัดสุทธิ (ลงมีด → ปิดแผล)")):
        rows, info = run_target(d, target)
        report.append(f"\n## {label}\n")
        report.append(f"n_train={info['n_train']:,} · n_test={info['n_test']:,} · "
                      f"หัตถการชื่อเต็มที่ไม่เคยเห็นในเทรน = {info['unseen_full']}% "
                      f"(ระดับ kw1 เหลือ {info['unseen_kw1']}%)\n")
        report.append(fmt_table(rows))
        print(report[-3]); print(report[-2]); print(report[-1])
        # ── ΔMAE: Random Forest vs โมเดลข้อ 7 + bootstrap 95% CI (paired, 5000 รอบ) ──
        _y = np.asarray(info["y_test"], float)
        _d_rf = np.abs(_y - np.asarray(info["rf_pred"], float))
        _d_ch = np.abs(_y - np.asarray(info["chosen_pred"], float))
        _delta = float(_d_rf.mean() - _d_ch.mean())     # >0 = ข้อ7 แย่กว่า RF
        _rng = np.random.RandomState(SEED); _n = len(_y); _bs = np.empty(5000)
        for _b in range(5000):
            _i = _rng.randint(0, _n, _n)
            _bs[_b] = _d_rf[_i].mean() - _d_ch[_i].mean()
        _lo, _hi = np.percentile(_bs, [2.5, 97.5])
        _line = f"ΔMAE (RF − ข้อ7) = {_delta:.2f} นาที · 95% CI [{_lo:.2f}, {_hi:.2f}]"
        report.append("\n" + _line + "\n"); print("  " + _line)
    OUT_RAW.write_text("\n".join(report), encoding="utf-8")
    print(f"\nบันทึกผลดิบ → {OUT_RAW.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
