"""
finetune_pipeline.py — ตัวอ่านไฟล์ HIS (schedule.csv / intraop.xls) สำหรับปุ่ม ③
=================================================================
⚠️ ETHICS LOCK (10 มิ.ย. 2026): ฟังก์ชัน fine-tune (auto_finetune /
prepare_finetune_data) ถูก "ถอดออก" จากไฟล์นี้แล้ว — เพราะการเทรน/fine-tune
ด้วยข้อมูลปี 2568-2569 อยู่นอกขอบเขต ethics approval (อนุมัติเฉพาะ พ.ศ. 2564-2567)

  - artifact ที่เคย fine-tune (v2-v7) ถูกย้ายไปกักกันที่ data/_quarantine_models_6869/
  - engine การเทรนยังอยู่ใน retrain_model.py แต่ติดกุญแจ (ดู OR_ETHICS_AMENDMENT_OK)
  - ได้รับ amendment เมื่อไหร่ → ดูวิธีคืนระบบใน docs/ETHICS_LOCK_2026-06-10.md

ที่เหลือในไฟล์นี้ = ตัว parse ไฟล์ HIS ล้วนๆ ซึ่งปุ่ม ③ (นำเข้า dashboard) ใช้อยู่:
  - _read_utf16_text / _norm_date / _hhmmss_to_min
  - _parse_schedule  : schedule.csv (UTF-16, quote ซ้อน) → features
  - _parse_intraop   : intraop.xls → เวลาจริง + ชื่อพยาบาล scrub/circ
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ============================================================
# Helpers
# ============================================================
def _hhmmss_to_min(v) -> Optional[int]:
    s = str(v).strip().split(".")[0]
    if not s.isdigit():
        return None
    s = s.zfill(6)
    h, m = int(s[:2]), int(s[2:4])
    return h * 60 + m if (h <= 23 and m <= 59) else None


def _norm_date(v) -> Optional[str]:
    d = pd.to_datetime(v, dayfirst=True, errors="coerce")
    return d.strftime("%Y-%m-%d") if pd.notna(d) else None


def _read_utf16_text(src) -> str:
    """อ่านไฟล์ schedule (UTF-16) จาก path หรือ buffer → string"""
    if hasattr(src, "read"):
        data = src.getvalue() if hasattr(src, "getvalue") else src.read()
        return data.decode("utf-16") if isinstance(data, (bytes, bytearray)) else data
    return Path(src).read_text(encoding="utf-16")


# ============================================================
# Parse แต่ละไฟล์
# ============================================================
def _parse_schedule(src) -> pd.DataFrame:
    """schedule.csv (HIS, UTF-16, quote ซ้อน) → features (proc/dx/age/surgeon/division/room)"""
    text = _read_utf16_text(src)
    rows = []
    for outer in csv.reader(io.StringIO(text)):
        inner = outer[0] if len(outer) == 1 else ",".join(outer)
        rows.append(next(csv.reader([inner])))
    out = []
    for r in rows[1:]:
        if len(r) < 29:
            continue
        age = pd.to_numeric(r[22], errors="coerce")
        out.append({
            "hn": r[0].strip(),
            "opedate_norm": _norm_date(r[19]),
            "orroom": pd.to_numeric(r[5], errors="coerce"),
            "icd9cm_name": r[24].strip(),
            "icd10_name": r[25].strip(),
            "surgstfnm": r[28].strip(),
            "division_sched": pd.to_numeric(r[3], errors="coerce"),
            "age": age if (pd.notna(age) and 0 <= age <= 120) else np.nan,
        })
    df = pd.DataFrame(out).dropna(subset=["hn", "opedate_norm"])
    return df.drop_duplicates(["hn", "opedate_norm", "orroom"])


def _parse_intraop(src) -> pd.DataFrame:
    """intraop.xls (HIS) → เวลาจริง (duration) + ห้อง + opesttime"""
    xl = pd.read_excel(src, engine="xlrd", dtype=str)
    d = pd.DataFrame()
    d["hn"] = xl["hn"].astype(str).str.strip()
    d["opedate_norm"] = pd.to_datetime(xl["opedate"], errors="coerce").dt.strftime("%Y-%m-%d")
    d["orroom"] = pd.to_numeric(xl["orroom"], errors="coerce")
    ti = xl["roomtimein"].map(_hhmmss_to_min)
    to = xl["roomtimeout"].map(_hhmmss_to_min)
    dur = to - ti
    d["duration_minutes"] = dur.where(dur >= 0, dur + 1440)   # ข้ามเที่ยงคืน
    d["roomtimein_min"] = ti
    d["roomtimeout_min"] = to
    d["opesttime"] = pd.to_numeric(xl["opesttime"], errors="coerce")
    # 🆕 ดึงชื่อพยาบาลด้วย (nursurgnm=scrub, nurcircunm=circ) — ไว้ backfill ขึ้น DB
    for _src, _dst in [("nursurgnm", "scrub_nurse"), ("nurcircunm", "circ_nurse")]:
        if _src in xl.columns:
            _s = xl[_src].astype(str).str.strip()
            d[_dst] = _s.where(~_s.str.upper().isin(["NAN", "NONE", ""]), None)
        else:
            d[_dst] = None
    return d[(d["duration_minutes"] >= 5) & (d["duration_minutes"] <= 1440)]
