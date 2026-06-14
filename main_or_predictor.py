"""
src/predictor.py — Production prediction API (v2)
==================================================
NEW: multi-level evidence — แสดงเคสคล้ายกันจากแคบไปกว้าง

แทนที่จะ return "n_similar = 5" เดียว, ตอนนี้ return list ของ evidence:
  - exact procedure name match (cases?)
  - fuzzy cluster match (cases?)
  - keyword (2-token) match (cases?)
  - keyword (1-token) match (cases?)
  - surgeon-only (cases?)
  - division-only (cases?)
  → user เห็นภาพ "เคสที่คล้ายกันมาก vs คล้ายกันน้อย" หลายระดับ
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from rapidfuzz import process, fuzz

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"
DATA_FILE = ROOT / "data" / "historical" / "main_or_history.csv"

DEFAULT_MODEL = "main_or_model_v1.pkl"
DEFAULT_PIPELINE = "main_or_pipeline_v1.pkl"
DEFAULT_CLUSTERS = "main_or_clusters_v1.pkl"


def _resolve_active_files() -> tuple[str, str, str]:
    """อ่านเวอร์ชัน active จาก models/model_registry.json (ถ้ามี) — ไม่มี/พังก็ fallback v1
    ทำให้ retrain_model.promote(N) สลับโมเดล production ได้โดยไม่ต้องแก้ไฟล์นี้"""
    model, pipe, clusters = DEFAULT_MODEL, DEFAULT_PIPELINE, DEFAULT_CLUSTERS
    try:
        import json
        reg = json.loads((MODEL_DIR / "model_registry.json").read_text(encoding="utf-8"))
        v = int(reg.get("active_version", 1))
        m, p, c = f"main_or_model_v{v}.pkl", f"main_or_pipeline_v{v}.pkl", f"main_or_clusters_v{v}.pkl"
        if (MODEL_DIR / m).exists() and (MODEL_DIR / p).exists():
            model, pipe = m, p
            clusters = c if (MODEL_DIR / c).exists() else DEFAULT_CLUSTERS
    except Exception:
        pass
    return model, pipe, clusters


# ============================================================
# Text normalization
# ============================================================
def normalize_proc(s: str) -> tuple[str, str, str]:
    """Return (full_norm, kw2_first_2_tokens, kw1_first_token)"""
    if not isinstance(s, str):
        return "unknown", "unknown", "unknown"
    s = re.sub(r"[\.,;:()\[\]/\\\-+]+", " ", s.strip().lower())
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return "unknown", "unknown", "unknown"
    t = s.split()
    kw2 = " ".join(t[:2]) if len(t) >= 2 else t[0]
    kw1 = t[0]
    return s, kw2, kw1


def normalize_surgeon(s: str) -> str:
    if not isinstance(s, str):
        return "unknown"
    return re.sub(r"\s+", " ", s.strip().lower())


# ============================================================
# Output classes
# ============================================================
@dataclass
class EvidenceLevel:
    """One level of matching evidence — broad/narrow"""
    level_name: str           # e.g. "procedure × surgeon (exact)"
    granularity: str          # narrow | medium | broad
    n_cases: int
    median: float
    q1: float
    q3: float
    mean: float
    min_val: float
    max_val: float
    has_signal: bool          # True if n_cases >= 3

    def to_dict(self):
        return asdict(self)


@dataclass
class PredictionResult:
    predicted_minutes: float
    predicted_range: tuple[float, float]
    confidence_level: str
    evidence_levels: list[EvidenceLevel] = field(default_factory=list)
    best_evidence: Optional[EvidenceLevel] = None
    fuzzy_procedure: Optional[dict] = None
    fuzzy_surgeon: Optional[dict] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self):
        d = {
            "predicted_minutes": self.predicted_minutes,
            "predicted_range": list(self.predicted_range),
            "confidence_level": self.confidence_level,
            "evidence_levels": [e.to_dict() for e in self.evidence_levels],
            "best_evidence": self.best_evidence.to_dict() if self.best_evidence else None,
            "fuzzy_procedure": self.fuzzy_procedure,
            "fuzzy_surgeon": self.fuzzy_surgeon,
            "notes": self.notes,
        }
        return d


# ============================================================
# The predictor
# ============================================================
class SurgicalTimePredictor:
    def __init__(self, model, pipeline: dict, train_df: pd.DataFrame, clusters: Optional[dict] = None):
        self.model = model
        self.pipe = pipeline
        self.train = train_df.reset_index(drop=True).copy()
        self.clusters = clusters or {}

        # build vocab for fuzzy
        self.proc_kw_vocab: list[str] = sorted(self.pipe["proc_kw_med"].keys())
        self.proc_full_vocab: list[str] = sorted(self.pipe["proc_full_med"].keys())
        self.surgeon_vocab: list[str] = sorted(self.pipe["surg_med"].keys())

        # pre-compute training helpers (อาศัย normalized procedure)
        norms = self.train["icd9cm_name"].apply(normalize_proc)
        self.train["_proc_full"] = norms.apply(lambda x: x[0])
        self.train["_proc_kw2"] = norms.apply(lambda x: x[1])
        self.train["_proc_kw1"] = norms.apply(lambda x: x[2])
        self.train["_surgeon"] = self.train["surgstfnm"].fillna("unknown").astype(str).str.strip().str.lower()
        self.train["_division"] = pd.to_numeric(self.train["division_sched"], errors="coerce")

        # Add cluster id from cluster data (if available)
        name_to_cluster = self.clusters.get("name_to_cluster", {})
        self.train["_cluster_id"] = self.train["_proc_full"].map(name_to_cluster).fillna(-1).astype(int)

    @classmethod
    def load_default(cls, train_data: Path = DATA_FILE) -> "SurgicalTimePredictor":
        model_f, pipe_f, clusters_f = _resolve_active_files()
        model = joblib.load(MODEL_DIR / model_f)
        pipe = joblib.load(MODEL_DIR / pipe_f)
        try:
            clusters = joblib.load(MODEL_DIR / clusters_f)
        except FileNotFoundError:
            clusters = {}
        df = pd.read_csv(train_data, low_memory=False)
        df["opedate"] = pd.to_datetime(df["opedate_norm"], errors="coerce")
        df["_c"] = df[["icd9cm_name", "icd10_name", "surgstfnm"]].notna().sum(axis=1)
        df = df.sort_values(["case_key", "_c"], ascending=[True, False]).drop_duplicates("case_key").reset_index(drop=True)
        train = df[df["opedate"].dt.year < 2024].reset_index(drop=True)
        return cls(model, pipe, train, clusters)

    # --------------------------------------------------------
    # Fuzzy matching
    # --------------------------------------------------------
    def fuzzy_match_procedure(self, query: str, threshold: int = 75) -> Optional[dict]:
        if not isinstance(query, str) or not query.strip():
            return None
        norm, kw2, _ = normalize_proc(query)
        best_full = process.extractOne(norm, self.proc_full_vocab, scorer=fuzz.token_set_ratio)
        best_kw = process.extractOne(kw2, self.proc_kw_vocab, scorer=fuzz.token_set_ratio)
        if best_full and best_full[1] >= threshold:
            return {"level": "full_procedure", "input": query,
                    "matched_name": best_full[0], "similarity": int(best_full[1])}
        if best_kw and best_kw[1] >= threshold:
            return {"level": "keyword", "input": query,
                    "matched_name": best_kw[0], "similarity": int(best_kw[1])}
        return None

    def fuzzy_match_surgeon(self, query: str, threshold: int = 80) -> Optional[dict]:
        if not isinstance(query, str) or not query.strip():
            return None
        q = normalize_surgeon(query)
        best = process.extractOne(q, self.surgeon_vocab, scorer=fuzz.WRatio)
        if best and best[1] >= threshold:
            return {"input": query, "matched_name": best[0], "similarity": int(best[1])}
        return None

    # --------------------------------------------------------
    # Multi-level evidence
    # --------------------------------------------------------
    def _summarize(self, df: pd.DataFrame, name: str, granularity: str) -> EvidenceLevel:
        durations = df["duration_minutes"].dropna().values
        n = len(durations)
        if n == 0:
            return EvidenceLevel(name, granularity, 0, 0, 0, 0, 0, 0, 0, has_signal=False)
        return EvidenceLevel(
            level_name=name,
            granularity=granularity,
            n_cases=int(n),
            median=round(float(np.median(durations)), 1),
            q1=round(float(np.percentile(durations, 25)), 1),
            q3=round(float(np.percentile(durations, 75)), 1),
            mean=round(float(durations.mean()), 1),
            min_val=round(float(durations.min()), 1),
            max_val=round(float(durations.max()), 1),
            has_signal=n >= 3,
        )

    def collect_evidence_levels(
        self,
        proc_full: str,
        proc_kw2: str,
        proc_kw1: str,
        surgeon: str,
        division: Optional[int],
    ) -> list[EvidenceLevel]:
        """Build cascading evidence: narrow → broad"""
        levels = []
        tr = self.train

        # 1) Exact procedure × surgeon (narrowest)
        m = (tr["_proc_full"] == proc_full) & (tr["_surgeon"] == surgeon)
        levels.append(self._summarize(tr[m], "หัตถการตรงเป๊ะ × แพทย์เดียวกัน", "narrow"))

        # 2) Cluster (fuzzy group) × surgeon
        cluster_id = self.clusters.get("name_to_cluster", {}).get(proc_full, -1)
        if cluster_id >= 0:
            m = (tr["_cluster_id"] == cluster_id) & (tr["_surgeon"] == surgeon)
            levels.append(self._summarize(tr[m], "หัตถการกลุ่มเดียวกัน × แพทย์เดียวกัน", "narrow"))

        # 3) kw2 × surgeon
        m = (tr["_proc_kw2"] == proc_kw2) & (tr["_surgeon"] == surgeon)
        levels.append(self._summarize(tr[m], "หัตถการคำหลักเหมือน × แพทย์เดียวกัน", "narrow"))

        # 4) Exact procedure only
        m = tr["_proc_full"] == proc_full
        levels.append(self._summarize(tr[m], "หัตถการตรงเป๊ะ (ทุกแพทย์)", "medium"))

        # 5) Cluster only
        if cluster_id >= 0:
            m = tr["_cluster_id"] == cluster_id
            levels.append(self._summarize(tr[m], "หัตถการกลุ่มเดียวกัน (ทุกแพทย์)", "medium"))

        # 6) kw2 only
        m = tr["_proc_kw2"] == proc_kw2
        levels.append(self._summarize(tr[m], "หัตถการคำหลักเหมือน (ทุกแพทย์)", "medium"))

        # 7) kw1 only (กว้างขึ้น)
        m = tr["_proc_kw1"] == proc_kw1
        levels.append(self._summarize(tr[m], "หัตถการคำแรกเหมือน", "broad"))

        # 8) Surgeon × division
        if division is not None:
            m = (tr["_surgeon"] == surgeon) & (tr["_division"] == division)
            levels.append(self._summarize(tr[m], "แพทย์เดียวกัน × แผนกเดียวกัน", "broad"))

        # 9) Surgeon only
        m = tr["_surgeon"] == surgeon
        levels.append(self._summarize(tr[m], "แพทย์เดียวกัน (ทุกหัตถการ)", "broad"))

        # 10) Division only
        if division is not None:
            m = tr["_division"] == division
            levels.append(self._summarize(tr[m], "แผนกเดียวกัน (ทุกแพทย์)", "broad"))

        return levels

    # --------------------------------------------------------
    # Build feature row
    # --------------------------------------------------------
    def _build_feature_row(
        self, proc_full, proc_kw, surgeon, division, orroom, age,
        planned_hour, opedate: Optional[pd.Timestamp], diagnosis_name="",
    ) -> pd.DataFrame:
        gm = self.pipe["global_median"]
        dx = re.sub(r"\s+", " ", str(diagnosis_name).strip().lower()) if diagnosis_name else "unknown"
        dx_kw = " ".join(dx.split()[:2]) if dx else "unknown"

        shift_bucket = 0
        if 1 <= planned_hour <= 11:
            shift_bucket = 1
        elif 12 <= planned_hour <= 15:
            shift_bucket = 2
        elif 16 <= planned_hour <= 23:
            shift_bucket = 3
        is_first = 1 if 7 <= planned_hour <= 8 else 0
        is_emerg = 1 if planned_hour == 0 else 0

        row = {
            "age": age,
            "planned_hour": planned_hour,
            "dow": opedate.dayofweek if opedate is not None else -1,
            "month": opedate.month if opedate is not None else -1,
            "orroom": orroom,
            "division": division,
            "is_emergency": is_emerg,
            "is_first_case": is_first,
            "shift_bucket": shift_bucket,
            "proc_kw_median": self.pipe["proc_kw_med"].get(proc_kw, gm),
            "proc_full_median": self.pipe["proc_full_med"].get(proc_full, gm),
            "dx_kw_median": self.pipe["dx_kw_med"].get(dx_kw, gm),
            "surg_median": self.pipe["surg_med"].get(surgeon, gm),
            "procsurg_kw_median": self.pipe["procsurg_kw_med"].get(f"{proc_kw}||{surgeon}", gm),
            "proc_div_median": self.pipe["proc_div_med"].get(f"{proc_kw}||{division}", gm),
            "proc_room_median": self.pipe["proc_room_med"].get(f"{proc_kw}||{orroom}", gm),
            "proc_kw_n": self.pipe["proc_kw_n"].get(proc_kw, 0),
            "surg_n": self.pipe["surg_n"].get(surgeon, 0),
            "procsurg_n": self.pipe["procsurg_kw_n"].get(f"{proc_kw}||{surgeon}", 0),
            "proc_kw_is_new": 1 if proc_kw not in self.pipe["proc_kw_n"] else 0,
        }
        return pd.DataFrame([row])[self.pipe["feature_names"]]

    # --------------------------------------------------------
    # Main predict
    # --------------------------------------------------------
    def predict(
        self,
        procedure_name: str,
        surgeon_name: str,
        division: int,
        orroom: int,
        age: float,
        planned_hour: int,
        opedate: str,
        diagnosis_name: str = "",
        fuzzy_threshold_proc: int = 75,
        fuzzy_threshold_surg: int = 80,
    ) -> PredictionResult:
        notes = []

        # 1. Normalize + fuzzy correct procedure
        proc_full, proc_kw2, proc_kw1 = normalize_proc(procedure_name)
        fuzzy_proc = None
        if proc_kw2 not in self.pipe["proc_kw_n"]:
            fuzzy_proc = self.fuzzy_match_procedure(procedure_name, threshold=fuzzy_threshold_proc)
            if fuzzy_proc:
                if fuzzy_proc["level"] == "full_procedure":
                    proc_full = fuzzy_proc["matched_name"]
                    _, proc_kw2, proc_kw1 = normalize_proc(proc_full)
                else:
                    proc_kw2 = fuzzy_proc["matched_name"]
                    proc_kw1 = proc_kw2.split()[0] if proc_kw2 else "unknown"
                notes.append(f"แก้ไขชื่อหัตถการอัตโนมัติ: '{procedure_name}' → '{fuzzy_proc['matched_name']}' ({fuzzy_proc['similarity']}% similar)")
            else:
                notes.append(f"⚠ หัตถการ '{procedure_name}' ไม่เคยพบในข้อมูล และไม่มีคำใกล้เคียง — ทำนายจากข้อมูลกว้าง")

        # 2. Fuzzy correct surgeon
        surgeon = normalize_surgeon(surgeon_name)
        fuzzy_surg = None
        if surgeon not in self.pipe["surg_n"]:
            fuzzy_surg = self.fuzzy_match_surgeon(surgeon_name, threshold=fuzzy_threshold_surg)
            if fuzzy_surg:
                surgeon = fuzzy_surg["matched_name"]
                notes.append(f"surgeon corrected: '{surgeon_name}' -> '{fuzzy_surg['matched_name']}' ({fuzzy_surg['similarity']}%)")
            else:
                notes.append(f"WARN surgeon '{surgeon_name}' not in vocab")

        # 3. Predict ML
        opedate_ts = pd.Timestamp(opedate) if opedate else None
        X = self._build_feature_row(
            proc_full, proc_kw2, surgeon, division, orroom, age,
            planned_hour, opedate_ts, diagnosis_name,
        )
        pred_log = self.model.predict(X)[0]
        pred = float(np.expm1(pred_log))

        # 4. Collect evidence
        levels = self.collect_evidence_levels(proc_full, proc_kw2, proc_kw1, surgeon, division)

        # 5. Best evidence = narrowest level with n >= 3
        best_evidence = None
        for ev in levels:
            if ev.has_signal:
                best_evidence = ev
                break

        # 6. Range
        if best_evidence and best_evidence.n_cases >= 5:
            pred_range = (max(0.0, best_evidence.q1), best_evidence.q3)
        else:
            pred_range = (max(0.0, pred - 30), pred + 30)

        # 7. Confidence
        if best_evidence is None:
            confidence = "very_low"
        elif best_evidence.granularity == "narrow" and best_evidence.n_cases >= 10:
            confidence = "high"
        elif best_evidence.granularity in ("narrow", "medium") and best_evidence.n_cases >= 5:
            confidence = "medium"
        elif best_evidence.n_cases >= 3:
            confidence = "low"
        else:
            confidence = "very_low"

        return PredictionResult(
            predicted_minutes=round(pred, 1),
            predicted_range=(round(pred_range[0], 1), round(pred_range[1], 1)),
            confidence_level=confidence,
            evidence_levels=levels,
            best_evidence=best_evidence,
            fuzzy_procedure=fuzzy_proc,
            fuzzy_surgeon=fuzzy_surg,
            notes=notes,
        )


# ============================================================
# (active-version resolution added for retrain_model versioning)
# ============================================================
