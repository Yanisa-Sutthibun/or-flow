"""
presence.py — 🟢 แถบ "ตอนนี้ใครออนไลน์อยู่บ้าง" (11 ส.ค. 2026)
═══════════════════════════════════════════════════════════════════════
ทำไมถึงมี: อาจารย์ที่ปรึกษาและผู้ทรงคุณวุฒิเปิดแอปแล้วต้องเห็นทันทีว่า OR Flow
"ถูกใช้งานจริงอยู่ตอนนี้" ไม่ใช่ระบบที่ทำส่งแล้ววางไว้เฉย ๆ

หลักคิดที่เคาะกับมุคกี้ (11 ส.ค. 2026):
  • บอกเป็น "กลุ่มของจอ/เครื่อง + จำนวน" เท่านั้น : ไม่ระบุห้อง ไม่ระบุตัวบุคคล
    (อาจารย์/ผู้ทรงเข้าใช้จากข้างนอก ระบุตำแหน่งไม่ได้อยู่แล้ว อย่าโม้ในสิ่งที่ไม่รู้)
  • ⛔ ไม่อ่าน ไม่เก็บ IP เด็ดขาด — ทุกเครื่องในโรงพยาบาลออกเน็ตผ่าน NAT เดียวกัน
    IP จึงแยกเครื่องไม่ได้จริง แถมเป็นข้อมูลส่วนบุคคลตาม PDPA (ได้ไม่คุ้มเสีย)
  • กลุ่มที่แยกได้ = "ประตูที่เครื่องนั้นเดินเข้ามา" ซึ่งระบบรู้อยู่แล้วจาก token/รหัส
    (ดูลำดับการดักใน main_or_app.main) ไม่ต้องเดาจากเครือข่าย

สิ่งที่เก็บลงตาราง presence_beat มีแค่ 3 ช่อง: คีย์เครื่อง · กลุ่ม · เวลาที่ส่งสัญญาณ
ไม่มีชื่อ ไม่มี HN ไม่มีเคส ไม่มี IP · แถวหมดอายุแล้วถูกกวาดทิ้งอัตโนมัติ

⚠️ คีย์ของจอประจำห้องเป็น "room:<เลขห้อง>" เพื่อกันนับซ้ำเมื่อจอกด refresh
   (1 ห้อง = 1 จอ ตามนิยาม) เลขห้องนี้ใช้ภายในเพื่อ dedupe เท่านั้น
   ไม่เคยถูกนำมาแสดงผล และเลขห้องไม่ใช่ข้อมูลส่วนบุคคล
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

from logger_setup import get_logger

log = get_logger("presence")

_BKK = timezone(timedelta(hours=7))

# ⏱️ ยังนับว่า "ออนไลน์" ถ้าส่งสัญญาณเข้ามาภายในกี่วินาที
#    บอร์ดเด้งเองทุก 30 วิ (fragment run_every=30) → 120 วิ = พลาดได้ 3 รอบยังไม่หลุด
_TTL_SEC = 120
# ⏱️ เขียน DB ถี่สุดกี่วินาทีต่อเครื่อง (กันเขียนรัว ๆ ตอนกดปุ่มถี่)
_BEAT_EVERY_SEC = 20
# ⏱️ แคชผลนับไว้กี่วินาที (กันอ่าน DB ซ้ำเมื่อ rerun ติด ๆ กัน)
_COUNT_CACHE_SEC = 10
# 🧹 กวาดแถวที่ตายแล้วทิ้งเมื่อเก่ากว่ากี่วินาที (ตารางนี้จึงเล็กอยู่เสมอ)
#    ไม่ขัดกติกา "ห้ามลบแถว Supabase ด้วยมือ" — นี่คือแถว heartbeat ที่หมดอายุ
#    ตามการออกแบบ ไม่ใช่ข้อมูลวิจัย/ผู้ป่วย (ทำแบบเดียวกับ board_state 7 วัน)
_SWEEP_AFTER_SEC = 3600

# 🏷️ กลุ่มที่ระบบแยกออกได้ (จากประตูที่เครื่องนั้นเดินเข้ามา): room · family · staff · admin
#    11 ส.ค. 2026 มุคกี้เคาะ: "เอาแค่ยอดรวม" → ไม่แสดงแยกกลุ่มบนแถบ
#    แต่ยังบันทึกคอลัมน์ kind ไว้เหมือนเดิม (ต้นทุนเท่าเดิม) เผื่ออยากแยกทีหลัง


def _now_str() -> str:
    """เวลาไทยรูปแบบเรียงตามตัวอักษรได้ — เทียบ TTL ด้วย string comparison ตรง ๆ
    (เลี่ยงฟังก์ชันวันเวลาที่ SQLite กับ PostgreSQL เขียนไม่เหมือนกัน)"""
    return datetime.now(_BKK).strftime('%Y-%m-%d %H:%M:%S')


def _cutoff_str(sec: int) -> str:
    return (datetime.now(_BKK) - timedelta(seconds=sec)).strftime('%Y-%m-%d %H:%M:%S')


def _session_id() -> str:
    """id ประจำ session ของ streamlit — ใช้แยกว่าเป็นคนละเครื่อง/คนละแท็บ
    ⚠️ ค่านี้เปลี่ยนเมื่อ refresh หน้า → เครื่องที่เพิ่งกด F5 อาจถูกนับเกิน 1
    ได้ไม่เกิน _TTL_SEC (2 นาที) แล้วแถวเก่าจะหมดอายุไปเอง : ยอมรับได้
    (จะให้แม่นกว่านี้ต้องฝัง id ถาวรใน localStorage = ต้องทำ custom component)"""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        _ctx = get_script_run_ctx()
        _sid = getattr(_ctx, 'session_id', None)
        if _sid:
            return str(_sid)
    except Exception:
        pass
    return 'unknown'


def _kind_now() -> str:
    """เครื่องนี้อยู่กลุ่มไหน — อ่านจาก role ที่ main() ตั้งไว้ตอนผ่านด่านเข้า"""
    _role = st.session_state.get('role')
    if _role == 'room':
        return 'room'
    if _role == 'admin':
        return 'admin'
    return 'staff'


def _ensure_table(conn) -> None:
    """สร้างตารางถ้ายังไม่มี — ทำเองที่นี่ไม่ฝากไว้กับ init_db
    เหตุผล: จอญาติ (?view=family) ออกจาก main() ด้วย st.stop() ก่อนถึง init_db
    ถ้าฝากไว้กับ init_db จอญาติจะไม่มีวันมีตารางให้เขียน"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS presence_beat (
            beat_key TEXT PRIMARY KEY,
            kind     TEXT,
            beat_at  TEXT
        )
    """)
    conn.commit()
    # 🔒 Postgres: เปิด RLS ให้เข้าชุดกับทุกตารางใน schema (ดู supabase/schema_postgres.sql)
    #    ไม่สร้าง policy = anon key แตะไม่ได้ · แอปต่อด้วย service_role ซึ่ง bypass อยู่แล้ว
    #    ทำที่นี่ด้วยเพราะตารางนี้เกิดตอน runtime (จอญาติออกก่อนถึง init_db)
    try:
        from db_connection import IS_POSTGRES
        if IS_POSTGRES:
            conn.execute("ALTER TABLE presence_beat ENABLE ROW LEVEL SECURITY")
            conn.commit()
    except Exception as e:
        log.warning(f"เปิด RLS ให้ presence_beat ไม่สำเร็จ ({type(e).__name__}): {e}")


def beat(kind: str = '') -> None:
    """💓 ส่งสัญญาณว่า "เครื่องนี้ยังเปิดอยู่" — เรียกจากทุกจุดที่เด้งเองทุก 30 วิ
    ล้มเหลวเมื่อไรก็เงียบ (ฟีเจอร์นี้ห้ามทำให้บอร์ดพัง) แต่ log ไว้ ไม่หายเงียบ"""
    _kind = kind or _kind_now()

    # คีย์ต่อเครื่อง: จอห้อง = ต่อห้อง (กันนับซ้ำตอน refresh) · ที่เหลือ = ต่อ session
    if _kind == 'room':
        _room = st.session_state.get('room_scope')
        _key = f"room:{_room}" if _room is not None else f"room:{_session_id()}"
    else:
        _key = f"{_kind}:{_session_id()}"

    # ⏱️ throttle: เขียนอย่างมาก 1 ครั้งต่อ _BEAT_EVERY_SEC ต่อเครื่อง
    import time as _t
    _last = float(st.session_state.get('_presence_last_beat') or 0.0)
    if _last and (_t.monotonic() - _last) < _BEAT_EVERY_SEC:
        return

    try:
        from main_or_db import db_session
        with db_session() as conn:
            if not st.session_state.get('_presence_table_ok'):
                _ensure_table(conn)
                st.session_state['_presence_table_ok'] = True
            conn.execute(
                "INSERT INTO presence_beat (beat_key, kind, beat_at) VALUES (?, ?, ?) "
                "ON CONFLICT (beat_key) DO UPDATE SET "
                "kind = EXCLUDED.kind, beat_at = EXCLUDED.beat_at",
                (_key, _kind, _now_str()))
            # 🧹 กวาดแถวตายทิ้งพร้อมกันเลย (ตารางเล็กมาก คิวรีนี้แทบไม่มีต้นทุน)
            conn.execute("DELETE FROM presence_beat WHERE beat_at < ?",
                         (_cutoff_str(_SWEEP_AFTER_SEC),))
            conn.commit()
        st.session_state['_presence_last_beat'] = _t.monotonic()
    except Exception as e:
        # เขียนไม่ได้ = แค่ไม่ถูกนับ ไม่กระทบการใช้งาน · ตั้งเวลาไว้กันรัวซ้ำ
        st.session_state['_presence_last_beat'] = _t.monotonic()
        st.session_state.pop('_presence_table_ok', None)
        log.warning(f"เขียน heartbeat ไม่สำเร็จ ({type(e).__name__}): {e}")


def counts() -> dict:
    """นับเครื่องที่ยังออนไลน์ แยกตามกลุ่ม → {'room': 4, 'staff': 2, ...}
    อ่านไม่ได้ = คืน dict ว่าง แล้วฝั่งแสดงผลจะไม่วาดแถบเลย (ไม่ขึ้นเลขมั่ว)"""
    import time as _t
    _cached = st.session_state.get('_presence_counts')
    _at = float(st.session_state.get('_presence_counts_at') or 0.0)
    if _cached is not None and (_t.monotonic() - _at) < _COUNT_CACHE_SEC:
        return _cached

    _out: dict = {}
    try:
        from main_or_db import db_session
        with db_session() as conn:
            if not st.session_state.get('_presence_table_ok'):
                _ensure_table(conn)
                st.session_state['_presence_table_ok'] = True
            rows = conn.execute(
                "SELECT kind, COUNT(*) FROM presence_beat "
                "WHERE beat_at >= ? GROUP BY kind",
                (_cutoff_str(_TTL_SEC),)).fetchall()
        for r in (rows or []):
            _out[str(r[0] or '')] = int(r[1] or 0)
    except Exception as e:
        st.session_state.pop('_presence_table_ok', None)
        log.warning(f"อ่าน heartbeat ไม่สำเร็จ ({type(e).__name__}): {e}")
        _out = {}

    st.session_state['_presence_counts'] = _out
    st.session_state['_presence_counts_at'] = _t.monotonic()
    return _out


def others_online() -> int:
    """มี "เครื่องอื่น" เปิด OR Flow ค้างอยู่กี่เครื่องตอนนี้ (ไม่นับเครื่องที่ถาม)
    ใช้ถามยืนยันก่อนกดปุ่มที่กระทบทุกจอ เช่น สวิตช์ 🎬/⏹️ โหมดสาธิตบนแอป DEMO
    (มุคกี้สั่ง 12 ส.ค. 2026: ไม่มีใครออนไลน์ = กดได้เลย · มีคนอยู่ = ต้องยืนยันก่อน)

    ⚠️ ต้องเรียก beat() มาก่อนในรอบนี้ ไม่งั้นเครื่องตัวเองไม่ถูกนับ ยอดจะเกินจริง 1
    ⚠️ อ่านไม่ได้ = คืน 0 (ถือว่าไม่มีใคร) ตั้งใจให้ "ไม่ขวางการใช้งาน":
       ฟีเจอร์นี้ห้ามทำให้บอร์ดพัง และถ้าอ่าน DB ไม่ได้ บอร์ดก็ไม่ได้ซิงก์ไปหา
       เครื่องอื่นอยู่แล้ว การกดปุ่มจึงไม่กระทบใคร"""
    return max(0, sum(counts().values()) - 1)


def chips_html() -> str:
    """แถบย่อ: ชิปเดียวต่อท้ายชิปเดิมในหัวแอป — เอาแค่ยอดรวม (มุคกี้เคาะ 11 ส.ค. 2026)
    คืน '' เมื่ออ่านไม่ได้/ยังไม่มีใครออนไลน์ → หัวแอปหน้าตาเหมือนเดิมเป๊ะ
    (ไม่มีทางขึ้น "0 คน" เพราะคนที่กำลังเปิดหน้าอยู่ก็ถูกนับด้วยแล้ว)

    🎨 11 ส.ค. 2026 (มุคกี้เคาะจาก docs/wireframe_online_chip.html — แบบ A):
       ถอด "แถบสีเขียวทึบ" ออก ให้หน้าตาเหมือนชิปอื่นบนหัวแอปเป๊ะ (พื้น brand-50
       ตัวหนังสือเทา) เหลือ 🟢 นำหน้าข้อความแบบเดียวกับชิป 🎓 🤖 📅
       เอาเมาส์จ่อ → tooltip อธิบายว่าเลขนี้คืออะไร (attribute title ล้วน ๆ ไม่ง้อ JS)
       ⚠️ นับเป็น "เครื่อง/จอ" ไม่ใช่จำนวนคน — ใช้คำว่าเครื่องทั้งบนชิปและใน tooltip
          (1 คนเปิด 2 จอ = นับ 2) อย่าเปลี่ยนเป็น "ท่าน/คน" จะกลายเป็นโม้ในสิ่งที่ไม่รู้

    ⚠️ ต้องเรียก beat() ก่อน counts() เสมอ ไม่งั้นเครื่องตัวเองจะหายไปจากยอด
    """
    _total = sum(counts().values())
    if _total <= 0:
        return ''
    _tip = (f"ตอนนี้มี {_total} เครื่องที่กำลังเปิดใช้งาน OR Flow อยู่ "
            "(นับจอที่ส่งสัญญาณเข้ามาภายใน 2 นาทีล่าสุด)")
    return (f'<span class="or-chip" title="{_tip}" aria-label="{_tip}" '
            f'style="cursor:help;">🟢 ออนไลน์ {_total} เครื่อง</span>')
