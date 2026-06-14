"""
logger_setup.py — logger กลางของแอป (เขียน error ลงไฟล์ + console)
═══════════════════════════════════════════════════════════════════════
เหตุผล: โค้ดเดิมมีหลายจุดที่ except แล้วเงียบ (error หาย ดีบักยาก) — module นี้
ให้ที่เก็บ log กลาง เพื่อให้ข้อผิดพลาดสำคัญ (โดยเฉพาะ DB) ถูกบันทึก ไม่หายเงียบ

ใช้:
    from logger_setup import get_logger
    log = get_logger("db")
    log.warning("...")           # เตือน
    log.exception("ล้มเหลว: ...") # error + stack trace

log เขียนที่ logs/orflow.log (หมุนไฟล์เมื่อโต > 2 MB เก็บ 3 ไฟล์)
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger("orflow")
    root.setLevel(logging.INFO)
    root.propagate = False
    try:
        _LOG_DIR.mkdir(exist_ok=True)
        fh = RotatingFileHandler(_LOG_DIR / "orflow.log", maxBytes=2_000_000,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT))
        root.addHandler(fh)
    except Exception:
        pass  # เขียนไฟล์ไม่ได้ (read-only fs) → ใช้ console อย่างเดียว
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
    root.addHandler(sh)
    _configured = True


def get_logger(name: str = "app") -> logging.Logger:
    """คืน logger ลูกของ 'orflow' (config ครั้งเดียว, idempotent)"""
    _configure()
    return logging.getLogger("orflow." + name)


if __name__ == "__main__":
    log = get_logger("test")
    log.info("logger setup OK")
    log.warning("ตัวอย่าง warning")
    try:
        1 / 0
    except ZeroDivisionError:
        log.exception("ตัวอย่าง error พร้อม stack trace")
    print("เขียน log ที่:", _LOG_DIR / "orflow.log")
