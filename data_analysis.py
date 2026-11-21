# -*- coding: utf-8 -*-
"""
data_analysis.py : 🔬 แท็บ Data analysis ของระบบจริง (มุกกี้สั่ง 20 พ.ย. 2026)
════════════════════════════════════════════════════════════════════════════
หน้าวิเคราะห์ข้อมูลจากสถิติ สำหรับหัวหน้าห้องผ่าตัด

สิทธิ์ : ทุกคนเห็นแท็บ แต่เนื้อหาเปิดด้วย "รหัสเฉพาะ" ที่ตั้งใน Secrets ชื่อ analysis_code
  · ไม่ใช่รหัสหน่วยงาน และไม่ใช่รหัสผู้ดูแลระบบ (สิทธิ์ผู้ดูแลระบบก็ไม่ได้เปิดให้เอง)
  · 🔒 fail-closed : ไม่ได้ตั้ง analysis_code = หน้านี้ปิดสนิท
  · ปลดล็อกต่อ session (ปิดเบราว์เซอร์หรือออกจากระบบ = ล็อกใหม่) ใส่ผิดเกิน 5 ครั้ง = พักทั้ง session
  · ห้าม hardcode รหัสในไฟล์ อ่านจาก st.secrets ตอนรันเท่านั้น

เนื้อหา : ยังเป็นโครงเปล่า รอมุกกี้กำหนดรายละเอียด (นัดคุย 21 พ.ย. 2026)
  งานกราฟในหน้านี้ให้ทำตามสกิล graph-storytelling (สรุป สวย สื่อ) :
    1. เขียน key message 1 ประโยคที่มีตัวเลขก่อนวาด แล้วใช้เป็นชื่อกราฟ
    2. เลือกชนิดกราฟจากคำถาม (สัดส่วน เปรียบเทียบ เปลี่ยนแปลง การกระจาย ความสัมพันธ์)
    3. หัว-ตัว-เท้า : พื้นเทา เน้นสีเดียวที่ประเด็น เรียงลำดับ ตัดกริด เท้าบอกว่าควรทำอะไรต่อ
    4. จัดหน้าแบบ 3-30-300 : ตัวชี้วัดหลักบนสุด แนวโน้มถัดมา รายละเอียดไว้ล่างสุด
  helper กราฟแท่งที่ทำตามหลักนี้แล้วอยู่ต้นไฟล์ main_or_admin.py (_story_bars, _story_axes,
  _story_bold_top, _story_head) ใช้ซ้ำได้ ไม่ต้องเขียนใหม่
"""
from __future__ import annotations

import hmac

import streamlit as st

_MAX_TRIES = 5
_K_OPEN = '_da_unlocked'
_K_FAIL = '_da_fail_n'


def _code() -> str:
    try:
        return str(st.secrets.get('analysis_code', '') or '').strip()
    except Exception:
        return ''


def code_configured() -> bool:
    return bool(_code())


def check_code(entered) -> bool:
    """เทียบรหัสแบบ constant-time · ไม่ตั้งรหัสหรือกรอกว่าง = ไม่ผ่านเสมอ"""
    want = _code()
    got = str(entered or '').strip()
    if not want or not got:
        return False
    return hmac.compare_digest(got.encode('utf-8'), want.encode('utf-8'))


def is_unlocked() -> bool:
    return bool(code_configured() and st.session_state.get(_K_OPEN) is True)


def _render_gate():
    ss = st.session_state
    st.markdown(
        '<div style="font-size:22px;font-weight:700;color:#0f172a;">🔬 Data analysis</div>'
        '<div style="color:#64748b;font-size:var(--fs-meta);margin:4px 0 12px;">'
        'หน้าวิเคราะห์ข้อมูลสำหรับหัวหน้าห้องผ่าตัด เปิดด้วยรหัสเฉพาะของหน้านี้</div>',
        unsafe_allow_html=True)
    if not code_configured():
        st.info("หน้านี้ยังไม่เปิดใช้งาน : ผู้วิจัยยังไม่ได้ตั้งรหัสของหน้านี้")
        return
    if int(ss.get(_K_FAIL, 0) or 0) >= _MAX_TRIES:
        st.error("กรอกรหัสไม่ถูกต้องหลายครั้ง : หน้านี้ถูกพักไว้ ออกจากระบบแล้วเข้าใหม่เพื่อลองอีกครั้ง")
        return
    _c, _x = st.columns([1.2, 2])
    with _c:
        with st.form("da_gate", clear_on_submit=True):
            # ช่องข้อความพรางเป็นจุดด้วย CSS : วิธีเดียวกับหน้า login กัน Chrome เสนอสร้างรหัสผ่าน
            st.markdown('<style>input[aria-label="รหัสหน้า Data analysis"]'
                        '{-webkit-text-security:disc;}</style>', unsafe_allow_html=True)
            pw = st.text_input("รหัสหน้า Data analysis", type="default", autocomplete="off",
                               placeholder="••••••", label_visibility='collapsed')
            if st.form_submit_button("เปิดหน้า", type="primary", width='stretch'):
                if check_code(pw):
                    ss[_K_OPEN], ss[_K_FAIL] = True, 0
                    st.rerun()
                else:
                    ss[_K_FAIL] = int(ss.get(_K_FAIL, 0) or 0) + 1
                    _left = _MAX_TRIES - ss[_K_FAIL]
                    st.error("รหัสไม่ถูกต้อง" + (f" (เหลืออีก {_left} ครั้ง)" if 0 < _left <= 2 else ""))


def page_data_analysis():
    """🔬 จุดเข้าเดียวของแท็บ · เนื้อหาวิเคราะห์เติมใน _render_body เท่านั้น (อยู่หลังด่านรหัสเสมอ)"""
    if not is_unlocked():
        _render_gate()
        return
    _h, _b = st.columns([5, 1], vertical_alignment="center")
    with _h:
        st.markdown('<div style="font-size:22px;font-weight:700;color:#0f172a;">'
                    '🔬 Data analysis</div>', unsafe_allow_html=True)
    with _b:
        if st.button("ล็อกหน้านี้", key="da_lock", width='stretch',
                     help="ปิดหน้านี้กลับ ต้องกรอกรหัสใหม่เมื่อเปิดครั้งถัดไป"):
            st.session_state[_K_OPEN] = False
            st.rerun()
    _render_body()


def _render_body():
    # 🚧 โครงเปล่า : รอรายละเอียดจากมุกกี้ (ดู docstring หัวไฟล์ก่อนเติมกราฟ)
    st.info("หน้านี้อยู่ระหว่างจัดทำ")
