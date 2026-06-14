"""
retrain_model.py — Continuous-learning / fine-tuning engine (v2)
================================================================
เครื่องมือปรับโมเดลทำนายเวลาผ่าตัด ออกแบบให้ปลอดภัยต่อวิทยานิพนธ์:

  • Locked test set    : กันชุดทดสอบ (เช่น 68–69) ออกก่อน — ไม่มีโมเดลไหนเอาไปเทรน
                          → เปรียบเทียบทุกโมเดลบนชุดเดียวกันอย่างแฟร์ (แก้ปัญหา leak ตอนเทียบ)
  • Fine-tuning        : ต่อยอด base v1 ด้วยข้อมูลใหม่ (continued boosting) — ใช้ feature
                          representation เดิมของ base เพื่อให้ tree ต่อกันได้
  • Full-retrain       : เทรนใหม่ทั้งหมดบนข้อมูลรวม (มักแม่นกว่าใน tabular) — เรียก "model update"
  • Champion/Challenger : promote เฉพาะเมื่อสั่งเอง — โมเดลที่รายงานในเล่ม (base v1) ยัง freeze ได้
  • Versioning/Registry : models/model_registry.json เก็บทุกเวอร์ชัน + method + ตัวที่ active

โมเดล/encoding ที่สร้าง "เข้ากันได้เป๊ะ" กับ main_or_predictor.SurgicalTimePredictor
→ promote แล้ว predictor โหลดใช้ได้ทันที

หลักการสำคัญ:
  - ข้อมูลตอน "ทำนาย" (ตารางที่ upload) ≠ ข้อมูลตอน "เทรน" — เคสจะเป็นข้อมูลเทรนได้ต่อเมื่อ
    "ผ่าตัดเสร็จ + มี duration_minutes จริง" แล้วเท่านั้น
  - การเทียบจะ "แฟร์จริง" ก็ต่อเมื่อ test set เป็นข้อมูลที่ base v1 "ไม่เคยเห็น" (เช่น 68–69)
  - ⚠ ก่อนใช้ข้อมูลปีใหม่เทรน/fine-tune จริง ควรยื่น amendment ขอบเขตข้อมูลกับคณะกรรมการจริยธรรมก่อน
"""
from __future__ import annotations

import json
import re
import shutil
import datetime as dt
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import joblib
from xgboost import XGBRegressor

# ใช้ normalization ตัวเดียวกับ predictor → encoding ตรงกันเป๊ะตอน inference
from main_or_predictor import normalize_proc, normalize_surgeon

# ============================================================
# Paths / constants
# ============================================================
ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"
DATA_FILE = ROOT / "data" / "historical" / "main_or_history.csv"
REGISTRY_FILE = MODEL_DIR / "model_registry.json"

# ลำดับ feature ต้องตรงกับ main_or_predictor._build_feature_row เป๊ะ
FEATURE_NAMES = [
    "age", "planned_hour", "dow", "month", "orroom", "division",
    "is_emergency", "is_first_case", "shift_bucket",
    "proc_kw_median", "proc_full_median", "dx_kw_median", "surg_median",
    "procsurg_kw_median", "proc_div_median", "proc_room_median",
    "proc_kw_n", "surg_n", "procsurg_n", "proc_kw_is_new",
]

# พารามิเตอร์ XGBoost สำหรับ full-retrain — ดึงจากโมเดล v1 เดิมเพื่อความต่อเนื่อง
XGB_PARAMS = dict(
    n_estimators=2000, max_depth=8, learning_rate=0.02,
    subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
    objective="reg:squarederror", random_state=42,
    tree_method="hist", n_jobs=-1,
)

# พารามิเตอร์สำหรับ fine-tune (continued boosting) — รอบน้อย + lr ต่ำ กันเอนเข้าข้อมูลใหม่มากไป
FT_PARAMS = dict(
    max_depth=6, subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
    objective="reg:squarederror", random_state=42, tree_method="hist", n_jobs=-1,
)
FT_DEFAULT_ROUNDS = 300
FT_DEFAULT_LR = 0.03

# กรอง duration ที่ผิดปกติออกก่อนเทรน (นาที)
DUR_MIN, DUR_MAX = 5.0, 1440.0


# ============================================================
# 🔒 ETHICS LOCK (10 มิ.ย. 2026)
# ============================================================
# ethics approval ครอบคลุมข้อมูลเทรนเฉพาะ พ.ศ. 2564-2567 (ค.ศ. 2021-2024)
# การเทรน/fine-tune ด้วยข้อมูลใหม่กว่านั้นต้องได้รับ amendment ก่อน
# ปลดล็อก (หลังได้ amendment): ตั้ง environment variable OR_ETHICS_AMENDMENT_OK=1
# รายละเอียด/วิธีคืนระบบ: docs/ETHICS_LOCK_2026-06-10.md
def _ethics_guard(action: str):
    import os as _os
    if _os.environ.get("OR_ETHICS_AMENDMENT_OK", "").strip() != "1":
        raise RuntimeError(
            f"🔒 ETHICS LOCK: '{action}' ถูกปิดใช้งาน — การเทรน/fine-tune โมเดล"
            "ด้วยข้อมูลนอกช่วง พ.ศ. 2564-2567 ต้องได้รับ amendment จาก"
            "คณะกรรมการจริยธรรมก่อน (ได้แล้วให้ตั้ง OR_ETHICS_AMENDMENT_OK=1 "
            "— ดู docs/ETHICS_LOCK_2026-06-10.md)")


# ============================================================
# Data loading + preparation
# ============================================================
def load_training_frame(path: Path = DATA_FILE,
                        extra: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """โหลด training store + (optional) ต่อเคสใหม่ที่จบแล้ว แล้ว dedup แบบเดียวกับ predictor"""
    df = pd.read_csv(path, low_memory=False)
    if extra is not None and len(extra) > 0:
        df = pd.concat([df, extra], ignore_index=True, sort=False)

    df["opedate"] = pd.to_datetime(df.get("opedate_norm"), errors="coerce")

    if "duration_minutes" not in df.columns:
        df["duration_minutes"] = np.nan
    need = df["duration_minutes"].isna()
    if need.any() and {"roomtimein_min", "roomtimeout_min"}.issubset(df.columns):
        df.loc[need, "duration_minutes"] = (
            pd.to_numeric(df.loc[need, "roomtimeout_min"], errors="coerce")
            - pd.to_numeric(df.loc[need, "roomtimein_min"], errors="coerce")
        )

    if "case_key" in df.columns:
        cols = [c for c in ["icd9cm_name", "icd10_name", "surgstfnm"] if c in df.columns]
        df["_c"] = df[cols].notna().sum(axis=1) if cols else 0
        df = (df.sort_values(["case_key", "_c"], ascending=[True, False])
                .drop_duplicates("case_key").reset_index(drop=True))
        df = df.drop(columns=["_c"])
    return df


def _dx_kw(series: pd.Series) -> pd.Series:
    """diagnosis keyword (2 token แรก) — normalize แบบเดียวกับ predictor (lower + collapse space)"""
    def f(x):
        if not isinstance(x, str):
            return "unknown"
        s = re.sub(r"\s+", " ", x.strip().lower())
        if not s:
            return "unknown"
        t = s.split()
        return " ".join(t[:2]) if len(t) >= 2 else t[0]
    return series.apply(f)


def prepare_features_frame(df: pd.DataFrame) -> pd.DataFrame:
    """แตกคอลัมน์ดิบ → helper columns ที่ใช้สร้าง feature + target; กรอง duration เสีย"""
    out = pd.DataFrame(index=df.index)
    out["opedate"] = df["opedate"]
    out["duration_minutes"] = pd.to_numeric(df["duration_minutes"], errors="coerce")

    # planned_hour จาก opesttime (เวลาที่ตั้งผ่า, รูปแบบ HHMMSS) — fallback roomtimein_min/60
    est = pd.to_numeric(df.get("opesttime"), errors="coerce")
    planned_hour = (est // 10000)
    rti = pd.to_numeric(df.get("roomtimein_min"), errors="coerce")
    planned_hour = planned_hour.where((planned_hour >= 0) & (planned_hour <= 23))
    planned_hour = planned_hour.fillna((rti // 60)).fillna(-1).astype(int)
    out["planned_hour"] = planned_hour

    out["age"] = pd.to_numeric(df.get("age"), errors="coerce").fillna(-1)
    out["dow"] = out["opedate"].dt.dayofweek.fillna(-1).astype(int)
    out["month"] = out["opedate"].dt.month.fillna(-1).astype(int)

    orroom = pd.to_numeric(df.get("orroom_sched"), errors="coerce")
    orroom = orroom.fillna(pd.to_numeric(df.get("orroom_intra"), errors="coerce"))
    out["orroom"] = orroom
    division = pd.to_numeric(df.get("division_sched"), errors="coerce")
    division = division.fillna(pd.to_numeric(df.get("division_intra"), errors="coerce"))
    out["division"] = division

    h = out["planned_hour"]
    shift = np.select(
        [(h >= 1) & (h <= 11), (h >= 12) & (h <= 15), (h >= 16) & (h <= 23)],
        [1, 2, 3], default=0,
    )
    out["shift_bucket"] = shift.astype(int)
    out["is_first_case"] = (((h >= 7) & (h <= 8)).astype(int))
    out["is_emergency"] = ((h == 0).astype(int))

    norms = df.get("icd9cm_name", pd.Series(index=df.index, dtype=object)).apply(normalize_proc)
    out["proc_full"] = norms.apply(lambda x: x[0])
    out["proc_kw2"] = norms.apply(lambda x: x[1])
    out["surgeon"] = df.get("surgstfnm", pd.Series(index=df.index, dtype=object)).apply(normalize_surgeon)
    out["dx_kw"] = _dx_kw(df.get("icd10_name", pd.Series(index=df.index, dtype=object)))

    out["procsurg_key"] = out["proc_kw2"] + "||" + out["surgeon"]
    out["procdiv_key"] = out["proc_kw2"] + "||" + out["division"].astype(str)
    out["procroom_key"] = out["proc_kw2"] + "||" + out["orroom"].astype(str)

    out = out[(out["duration_minutes"] >= DUR_MIN) & (out["duration_minutes"] <= DUR_MAX)]
    out = out.dropna(subset=["opedate"]).reset_index(drop=True)
    return out


# ============================================================
# Encoding (pipeline) — สร้างจาก "train split เท่านั้น" เพื่อกัน leak เข้า test/validation
# ============================================================
def fit_encodings(train: pd.DataFrame, min_count: int = 1) -> dict:
    d = train["duration_minutes"]
    gm = float(np.median(d))

    def med_by(key_col: str) -> dict:
        g = train.groupby(key_col)["duration_minutes"]
        med = g.median()
        if min_count > 1:
            med = med[g.size() >= min_count]
        return {k: float(v) for k, v in med.items()}

    def n_by(key_col: str) -> dict:
        return {k: int(v) for k, v in train.groupby(key_col).size().items()}

    return {
        "feature_names": list(FEATURE_NAMES),
        "global_median": gm,
        "proc_kw_med": med_by("proc_kw2"),
        "proc_full_med": med_by("proc_full"),
        "dx_kw_med": med_by("dx_kw"),
        "surg_med": med_by("surgeon"),
        "procsurg_kw_med": med_by("procsurg_key"),
        "proc_div_med": med_by("procdiv_key"),
        "proc_room_med": med_by("procroom_key"),
        "proc_kw_n": n_by("proc_kw2"),
        "surg_n": n_by("surgeon"),
        "procsurg_kw_n": n_by("procsurg_key"),
    }


def build_X(df: pd.DataFrame, pipe: dict) -> pd.DataFrame:
    """สร้าง feature matrix (ลำดับตาม FEATURE_NAMES) จาก encodings ที่ให้มา"""
    gm = pipe["global_median"]
    X = pd.DataFrame(index=df.index)
    X["age"] = df["age"]
    X["planned_hour"] = df["planned_hour"]
    X["dow"] = df["dow"]
    X["month"] = df["month"]
    X["orroom"] = df["orroom"]
    X["division"] = df["division"]
    X["is_emergency"] = df["is_emergency"]
    X["is_first_case"] = df["is_first_case"]
    X["shift_bucket"] = df["shift_bucket"]
    X["proc_kw_median"] = df["proc_kw2"].map(pipe["proc_kw_med"]).fillna(gm)
    X["proc_full_median"] = df["proc_full"].map(pipe["proc_full_med"]).fillna(gm)
    X["dx_kw_median"] = df["dx_kw"].map(pipe["dx_kw_med"]).fillna(gm)
    X["surg_median"] = df["surgeon"].map(pipe["surg_med"]).fillna(gm)
    X["procsurg_kw_median"] = df["procsurg_key"].map(pipe["procsurg_kw_med"]).fillna(gm)
    X["proc_div_median"] = df["procdiv_key"].map(pipe["proc_div_med"]).fillna(gm)
    X["proc_room_median"] = df["procroom_key"].map(pipe["proc_room_med"]).fillna(gm)
    X["proc_kw_n"] = df["proc_kw2"].map(pipe["proc_kw_n"]).fillna(0)
    X["surg_n"] = df["surgeon"].map(pipe["surg_n"]).fillna(0)
    X["procsurg_n"] = df["procsurg_key"].map(pipe["procsurg_kw_n"]).fillna(0)
    X["proc_kw_is_new"] = (~df["proc_kw2"].isin(pipe["proc_kw_n"])).astype(int)
    return X[FEATURE_NAMES]


# ============================================================
# Metrics + evaluation
# ============================================================
def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.clip(np.asarray(y_pred, dtype=float), 0, None)
    err = np.abs(y_true - y_pred)
    mask = y_true > 0
    mape = float(np.mean(err[mask] / y_true[mask]) * 100) if mask.any() else float("nan")
    return {
        "n": int(len(y_true)),
        "mae": round(float(np.mean(err)), 2),
        "rmse": round(float(np.sqrt(np.mean((y_true - y_pred) ** 2))), 2),
        "mape": round(mape, 2),
        "within_15min": round(float(np.mean(err <= 15) * 100), 1),
        "within_30min": round(float(np.mean(err <= 30) * 100), 1),
    }


def evaluate(model, pipe: dict, val: pd.DataFrame) -> dict:
    """ทำนาย val ด้วย (model, pipe) ของใครของมัน → คืน metrics บนหน่วยนาทีจริง"""
    X = build_X(val, pipe)
    pred = np.expm1(model.predict(X))
    return _metrics(val["duration_minutes"].values, pred)


def time_split(feat: pd.DataFrame, val_frac: float = 0.2,
               holdout_from_year: Optional[int] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """แบ่งตามเวลา: เก่า=train, ใหม่ล่าสุด=validation"""
    feat = feat.sort_values("opedate").reset_index(drop=True)
    if holdout_from_year is not None:
        train = feat[feat["opedate"].dt.year < holdout_from_year]
        val = feat[feat["opedate"].dt.year >= holdout_from_year]
    else:
        cut = int(len(feat) * (1 - val_frac))
        train, val = feat.iloc[:cut], feat.iloc[cut:]
    return train.reset_index(drop=True), val.reset_index(drop=True)


def carve_test_set(feat: pd.DataFrame, test_from_year: Optional[int] = None,
                   test_frac: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """กันชุดทดสอบ (locked) ออกก่อน — ใช้สำหรับ experiment ที่ต้องเทียบหลายโมเดลอย่างแฟร์
    return (devel, test) โดย test = ข้อมูลใหม่สุด ที่จะไม่ถูกเอาไปเทรนเลย"""
    feat = feat.sort_values("opedate").reset_index(drop=True)
    if test_from_year is not None:
        test = feat[feat["opedate"].dt.year >= test_from_year]
        devel = feat[feat["opedate"].dt.year < test_from_year]
    else:
        cut = int(len(feat) * (1 - test_frac))
        devel, test = feat.iloc[:cut], feat.iloc[cut:]
    return devel.reset_index(drop=True), test.reset_index(drop=True)


# ============================================================
# Model fitting
# ============================================================
def _fit_full_model(train: pd.DataFrame, min_count: int = 1) -> tuple[XGBRegressor, dict]:
    """Full retrain: encoding ใหม่ + เทรน XGBoost ใหม่ทั้งหมดจาก train"""
    pipe = fit_encodings(train, min_count=min_count)
    X = build_X(train, pipe)
    y = np.log1p(train["duration_minutes"].values)
    model = XGBRegressor(**XGB_PARAMS)
    model.fit(X, y)
    return model, pipe


def _finetune_model(devel: pd.DataFrame, base_model: XGBRegressor, base_pipe: dict,
                    ft_rounds: int = FT_DEFAULT_ROUNDS,
                    ft_lr: float = FT_DEFAULT_LR) -> tuple[XGBRegressor, dict]:
    """Fine-tune (continued boosting): ต่อ tree เพิ่มบน base ด้วยข้อมูล devel
    สำคัญ: ใช้ encoding ของ base (representation เดิม) เพื่อให้ tree ที่ต่อกันสอดคล้องกัน"""
    _ethics_guard("fine-tune")
    X = build_X(devel, base_pipe)
    y = np.log1p(devel["duration_minutes"].values)
    ft = XGBRegressor(n_estimators=ft_rounds, learning_rate=ft_lr, **FT_PARAMS)
    ft.fit(X, y, xgb_model=base_model.get_booster())
    # base v1 ถูกเทรนด้วย early stopping (best_iteration เก่าติดมา) → predict จะตัด tree ที่ต่อใหม่ทิ้ง
    # reset ให้ predict ใช้ tree "ทั้งหมด"
    bst = ft.get_booster()
    bst.best_iteration = bst.num_boosted_rounds() - 1
    return ft, base_pipe   # fine-tune ใช้ pipeline เดิมของ base


# ============================================================
# Registry
# ============================================================
def _load_registry() -> dict:
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"active_version": 1, "versions": {
        "1": {"created": "baseline", "method": "base",
              "note": "โมเดลตั้งต้น v1 (ethics-approved 64-67)"}}}


def _save_registry(reg: dict) -> None:
    MODEL_DIR.mkdir(exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_active_version() -> int:
    return int(_load_registry().get("active_version", 1))


def get_active_model_files() -> tuple[str, str, str]:
    """คืนชื่อไฟล์ (model, pipeline, clusters) ของเวอร์ชันที่ active — fallback v1"""
    v = get_active_version()
    m, p, c = f"main_or_model_v{v}.pkl", f"main_or_pipeline_v{v}.pkl", f"main_or_clusters_v{v}.pkl"
    if (MODEL_DIR / m).exists() and (MODEL_DIR / p).exists():
        if not (MODEL_DIR / c).exists():
            c = "main_or_clusters_v1.pkl"
        return m, p, c
    return "main_or_model_v1.pkl", "main_or_pipeline_v1.pkl", "main_or_clusters_v1.pkl"


def _next_version(reg: dict) -> int:
    nums = [int(k) for k in reg.get("versions", {}).keys() if str(k).isdigit()]
    return (max(nums) + 1) if nums else 2


def list_versions() -> dict:
    return _load_registry()


def promote(version: int) -> dict:
    """ตั้งเวอร์ชันที่ระบุให้เป็น active (champion ใหม่)"""
    reg = _load_registry()
    if str(version) not in reg.get("versions", {}):
        raise ValueError(f"ไม่พบเวอร์ชัน v{version} ใน registry")
    reg["active_version"] = int(version)
    reg["versions"][str(version)]["promoted_at"] = _now()
    _save_registry(reg)
    return reg


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _save_version(reg: dict, version: int, model, pipe: dict, meta: dict) -> None:
    """เซฟ model/pipeline/clusters เป็นเวอร์ชัน N + ลงทะเบียน meta"""
    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_DIR / f"main_or_model_v{version}.pkl")
    joblib.dump(pipe, MODEL_DIR / f"main_or_pipeline_v{version}.pkl")
    src_clusters = MODEL_DIR / "main_or_clusters_v1.pkl"
    if src_clusters.exists():
        shutil.copy(src_clusters, MODEL_DIR / f"main_or_clusters_v{version}.pkl")
    reg.setdefault("versions", {})[str(version)] = meta


# ============================================================
# Full-retrain (challenger เดี่ยว) — คงไว้ใช้กับปุ่ม Retrain ปกติ
# ============================================================
def retrain(path: Path = DATA_FILE,
            extra: Optional[pd.DataFrame] = None,
            val_frac: float = 0.2,
            holdout_from_year: Optional[int] = None,
            min_count: int = 1,
            note: str = "") -> dict:
    """เทรน challenger (full-retrain) + เทียบกับ champion ปัจจุบันบน validation เดียวกัน"""
    _ethics_guard("full-retrain")
    raw = load_training_frame(path, extra=extra)
    feat = prepare_features_frame(raw)
    if len(feat) < 200:
        raise ValueError(f"ข้อมูลพร้อมเทรนน้อยเกินไป ({len(feat)} แถว) — ต้องการอย่างน้อย 200")

    train, val = time_split(feat, val_frac=val_frac, holdout_from_year=holdout_from_year)
    if len(val) < 20:
        raise ValueError(f"validation set เล็กเกินไป ({len(val)} แถว)")

    model, pipe = _fit_full_model(train, min_count=min_count)
    challenger_metrics = evaluate(model, pipe, val)

    champion_metrics = None
    try:
        cm, cp, _ = get_active_model_files()
        champion_metrics = evaluate(joblib.load(MODEL_DIR / cm), joblib.load(MODEL_DIR / cp), val)
    except Exception as e:
        champion_metrics = {"error": str(e)}

    reg = _load_registry()
    version = _next_version(reg)
    train_years = sorted(train["opedate"].dt.year.dropna().unique().tolist())
    val_years = sorted(val["opedate"].dt.year.dropna().unique().tolist())
    _save_version(reg, version, model, pipe, {
        "created": _now(), "method": "full_retrain", "note": note,
        "n_train": int(len(train)), "n_val": int(len(val)),
        "train_years": train_years, "val_years": val_years,
        "metrics_val": challenger_metrics,
        "champion_compared": get_active_version(),
        "champion_metrics_val": champion_metrics,
    })
    _save_registry(reg)

    recommend = False
    reason = "ไม่มี champion ให้เทียบ — ตรวจสอบ metrics ด้วยตนเองก่อน promote"
    if champion_metrics and "mae" in champion_metrics:
        d = challenger_metrics["mae"] - champion_metrics["mae"]
        recommend = d <= 0
        reason = (f"challenger {'ดีขึ้น' if recommend else 'แย่ลง'}: "
                  f"MAE {champion_metrics['mae']}→{challenger_metrics['mae']} นาที")

    return {
        "version": version, "active_version": get_active_version(),
        "n_total": int(len(feat)), "n_train": int(len(train)), "n_val": int(len(val)),
        "train_years": train_years, "val_years": val_years,
        "challenger": challenger_metrics, "champion": champion_metrics,
        "recommend_promote": recommend, "reason": reason,
    }


# ============================================================
# Experiment: base vs fine-tune vs full-retrain บน "locked test set"
# ============================================================
def run_experiment(path: Path = DATA_FILE,
                   extra: Optional[pd.DataFrame] = None,
                   test_from_year: Optional[int] = None,
                   test_frac: float = 0.2,
                   ft_rounds: int = FT_DEFAULT_ROUNDS,
                   ft_lr: float = FT_DEFAULT_LR,
                   min_count: int = 1,
                   note: str = "") -> dict:
    """
    เทียบ 3 โมเดลบน "ชุดทดสอบเดียวกันที่ไม่มีใครเทรน":
      • base       = champion ปัจจุบัน (v1) — ไม่เทรนเพิ่ม
      • fine-tune  = ต่อยอด base ด้วย devel (continued boosting)
      • full       = retrain ใหม่ทั้งหมดบน devel
    เซฟ fine-tune และ full เป็นเวอร์ชันใหม่ (ยังไม่ promote) — คืนตารางผลให้ตัดสินใจ

    test_from_year : ปีที่เริ่มเป็น test (เช่น 2025 = ปี 68) — ถ้า None ใช้ test_frac (ใหม่สุด)
    หมายเหตุ: จะ "แฟร์เต็มที่" เมื่อ test เป็นข้อมูลที่ base v1 ไม่เคยเห็น (เช่น 68–69)
    """
    _ethics_guard("run_experiment (base vs fine-tune vs full-retrain)")
    raw = load_training_frame(path, extra=extra)
    feat = prepare_features_frame(raw)
    devel, test = carve_test_set(feat, test_from_year=test_from_year, test_frac=test_frac)
    if len(test) < 20:
        raise ValueError(f"test set เล็กเกินไป ({len(test)} แถว)")
    if len(devel) < 200:
        raise ValueError(f"devel set เล็กเกินไป ({len(devel)} แถว)")

    # base = champion ปัจจุบัน
    bm, bp, _ = get_active_model_files()
    base_model = joblib.load(MODEL_DIR / bm)
    base_pipe = joblib.load(MODEL_DIR / bp)
    base_metrics = evaluate(base_model, base_pipe, test)
    base_version = get_active_version()

    # fine-tune base ด้วย devel
    ft_model, ft_pipe = _finetune_model(devel, base_model, base_pipe, ft_rounds, ft_lr)
    ft_metrics = evaluate(ft_model, ft_pipe, test)

    # full retrain บน devel
    full_model, full_pipe = _fit_full_model(devel, min_count=min_count)
    full_metrics = evaluate(full_model, full_pipe, test)

    # เซฟ fine-tune + full เป็นเวอร์ชันใหม่ (ไม่แตะ base)
    reg = _load_registry()
    devel_years = sorted(devel["opedate"].dt.year.dropna().unique().tolist())
    test_years = sorted(test["opedate"].dt.year.dropna().unique().tolist())
    common = {"created": _now(), "note": note,
              "n_devel": int(len(devel)), "n_test": int(len(test)),
              "devel_years": devel_years, "test_years": test_years,
              "base_metrics_test": base_metrics}

    v_ft = _next_version(reg)
    _save_version(reg, v_ft, ft_model, ft_pipe, {
        **common, "method": "finetune", "base_version": base_version,
        "ft_rounds": ft_rounds, "ft_lr": ft_lr, "metrics_test": ft_metrics})
    v_full = _next_version(reg)   # อ่านใหม่หลังเพิ่ม v_ft
    _save_version(reg, v_full, full_model, full_pipe, {
        **common, "method": "full_retrain", "metrics_test": full_metrics})
    _save_registry(reg)

    # หาตัวที่ดีสุด (MAE ต่ำสุด)
    cands = [("base", base_version, base_metrics),
             ("finetune", v_ft, ft_metrics),
             ("full_retrain", v_full, full_metrics)]
    best = min(cands, key=lambda x: x[2]["mae"])
    best_method, best_version, best_metrics = best
    improved = best_method != "base"
    if improved:
        reason = (f"'{best_method}' (v{best_version}) แม่นสุด: MAE {best_metrics['mae']} "
                  f"นาที (base {base_metrics['mae']}) → แนะนำ promote v{best_version}")
    else:
        reason = (f"base v{base_version} ยังแม่นสุด (MAE {base_metrics['mae']}) "
                  f"→ แนะนำคงตัวเดิม (test อาจยังไม่ใช่ข้อมูลใหม่จริง)")

    return {
        "test_from_year": test_from_year, "test_frac": test_frac,
        "n_devel": int(len(devel)), "n_test": int(len(test)),
        "devel_years": devel_years, "test_years": test_years,
        "base": {"version": base_version, "metrics": base_metrics},
        "finetune": {"version": v_ft, "metrics": ft_metrics, "ft_rounds": ft_rounds, "ft_lr": ft_lr},
        "full_retrain": {"version": v_full, "metrics": full_metrics},
        "best_method": best_method, "best_version": best_version,
        "recommend_promote": improved, "reason": reason,
    }


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Retrain / fine-tune surgical-time model")
    ap.add_argument("--mode", choices=["retrain", "experiment"], default="experiment")
    ap.add_argument("--test-from-year", type=int, default=None,
                    help="ปีที่เริ่มเป็น test set (เช่น 2025) — สำหรับ mode=experiment")
    ap.add_argument("--test-frac", type=float, default=0.2)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--holdout-year", type=int, default=None)
    ap.add_argument("--ft-rounds", type=int, default=FT_DEFAULT_ROUNDS)
    ap.add_argument("--ft-lr", type=float, default=FT_DEFAULT_LR)
    ap.add_argument("--note", type=str, default="cli")
    args = ap.parse_args()

    if args.mode == "experiment":
        res = run_experiment(test_from_year=args.test_from_year, test_frac=args.test_frac,
                             ft_rounds=args.ft_rounds, ft_lr=args.ft_lr, note=args.note)
    else:
        res = retrain(val_frac=args.val_frac, holdout_from_year=args.holdout_year, note=args.note)
    print(json.dumps(res, ensure_ascii=False, indent=2))
