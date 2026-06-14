"""
mask_model_artifacts.py — แปลงชื่อแพทย์จริงในไฟล์โมเดล → รหัส SURG_xxx (one-shot)
═══════════════════════════════════════════════════════════════════════
ปัญหา: models/honest_v1/hier_*.json (git-tracked) มีชื่อแพทย์จริงเป็น key
       ของ surg_med / surg_n → ขัดนโยบาย masking (PDPA บุคลากร)

วิธีแก้: เปลี่ยน key เป็นรหัส SURG_xxx (ชุดเดียวกับ staff_mapping.csv ที่ใช้
       mask บน Supabase) — "ค่า" median/count ไม่แตะเลย → คำทำนายเท่าเดิม 100%
       (or_time_model._surgeon_key ทำหน้าที่แปลง ชื่อ→รหัส ตอน predict)

ความปลอดภัย:
  - สำรองไฟล์เดิมไว้ที่ data/_backup_model_names/<timestamp>/ (data/ ถูก gitignore)
  - ห้ามรันบนเครื่องที่ไม่มี staff_mapping.csv (จะ assign รหัสชุดใหม่ซ้อน)
  - ตรวจหลังแปลง: ไม่เหลืออักษรไทยใน key + จำนวน/ค่า ครบเท่าเดิม

ใช้:  python mask_model_artifacts.py
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from staff_unmask import assign_codes, _load_mapping

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models" / "honest_v1"
FILES = ["hier_room_use.json", "hier_surg_time.json"]
BACKUP_DIR = ROOT / "data" / "_backup_model_names" / datetime.now().strftime("%Y%m%d_%H%M%S")

_CODE_RE = re.compile(r"^SURG_\d{2,5}$")
_THAI_RE = re.compile(r"[฀-๿]")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def build_name2code(names) -> dict:
    """ชื่อ (normalized แบบเดียวกับโมเดล) → SURG_xxx
    ใช้รหัสเดิมจาก staff_mapping.csv ก่อน (เทียบแบบ normalize) —
    ชื่อที่ไม่เคยมี ค่อย assign รหัสใหม่ผ่าน assign_codes (เขียนลง mapping)"""
    mapping = _load_mapping()                     # {code: original_name}
    if not mapping:
        raise SystemExit("❌ ไม่พบ staff_mapping.csv — ห้ามรันบนเครื่องนี้ "
                         "(จะสร้างรหัสชุดใหม่ชนกับของจริง)")
    norm2code = {}
    for code, orig in mapping.items():
        if code.startswith("SURG_"):
            norm2code.setdefault(_norm(orig), code)

    out, missing = {}, []
    for nm in names:
        c = norm2code.get(_norm(nm))
        if c:
            out[nm] = c
        else:
            missing.append(nm)
    if missing:
        newly = assign_codes(missing, "SURG")     # เขียนชื่อใหม่ลง mapping (local เท่านั้น)
        out.update(newly)
    return out


def mask_file(path: Path) -> dict:
    meta = json.loads(path.read_text(encoding="utf-8"))
    names = set(meta.get("surg_med", {})) | set(meta.get("surg_n", {}))
    already = {n for n in names if _CODE_RE.match(n)}
    todo = sorted(names - already)
    if not todo:
        return {"file": path.name, "status": "already masked", "n": len(names)}

    n2c = build_name2code(todo)
    before_med = dict(meta["surg_med"])
    before_n = dict(meta["surg_n"])
    meta["surg_med"] = {n2c.get(k, k): v for k, v in meta["surg_med"].items()}
    meta["surg_n"] = {n2c.get(k, k): v for k, v in meta["surg_n"].items()}
    meta["surg_keys_masked"] = True               # ป้ายบอก predict-time resolver

    # ── ตรวจความถูกต้องก่อนเขียนทับ ──
    assert len(meta["surg_med"]) == len(before_med), "จำนวน surg_med ไม่เท่าเดิม (ชื่อชนกัน?)"
    assert len(meta["surg_n"]) == len(before_n), "จำนวน surg_n ไม่เท่าเดิม (ชื่อชนกัน?)"
    for k, v in before_med.items():
        assert meta["surg_med"][n2c.get(k, k)] == v, f"ค่า median เพี้ยนที่ {n2c.get(k, k)}"
    leftover = [k for k in meta["surg_med"] if _THAI_RE.search(k)]
    assert not leftover, f"ยังเหลือ key ภาษาไทย {len(leftover)} ตัว"

    path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"file": path.name, "status": "masked", "n": len(names),
            "new_codes_assigned": len([n for n in todo if _norm(n) not in
                                       {_norm(o) for c, o in _load_mapping().items()
                                        if c.startswith('SURG_')}])}


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        src = MODEL_DIR / f
        shutil.copy2(src, BACKUP_DIR / f)
    print(f"🗄  สำรองไฟล์เดิม → {BACKUP_DIR.relative_to(ROOT)} (โฟลเดอร์นี้ไม่ขึ้น git)")
    for f in FILES:
        r = mask_file(MODEL_DIR / f)
        print(f"✅ {r['file']}: {r['status']} (แพทย์ {r['n']} คน)")
    print("เสร็จ — ตรวจซ้ำ: python -c \"import json,re;"
          "d=json.load(open('models/honest_v1/hier_room_use.json',encoding='utf-8'));"
          "print(all(not re.search(r'[\\u0e00-\\u0e7f]',k) for k in d['surg_med']))\"")


if __name__ == "__main__":
    main()
