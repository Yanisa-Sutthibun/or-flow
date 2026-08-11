# -*- coding: utf-8 -*-
"""
tests/st_stub.py — streamlit ปลอมสำหรับทดสอบ logic โดยไม่ต้องรันแอปจริง
════════════════════════════════════════════════════════════════════════════
ต่อยอด pattern ที่ใช้กันในโปรเจกต์นี้อยู่แล้ว (mock sys.modules['streamlit']
+ class SS(dict) แทน session_state) แต่ยกมาไว้ที่เดียว ให้ไฟล์เทสต์ทุกไฟล์เรียกใช้

ครอบเฉพาะเท่าที่ logic ฝั่ง state machine / merge / auth ต้องใช้:
ทุกฟังก์ชันวาดหน้าจอเป็น no-op ที่ "จำสิ่งที่ถูกเรียก" ไว้ให้ตรวจย้อนหลังได้
(เช่น ตรวจว่ามี st.error ขึ้นจริงตอนบอร์ดกลางออฟไลน์)
"""
from __future__ import annotations

import sys
import types


class SS(dict):
    """session_state ปลอม — เข้าถึงได้ทั้งแบบ dict และแบบ attribute เหมือนของจริง"""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class _Ctx:
    """context manager ปลอม — ใช้แทน st.container()/st.form()/columns()
    เรียกเป็นฟังก์ชันได้ด้วย เพื่อรองรับ decorator แบบมีวงเล็บ
    (@st.cache_resource(show_spinner=False) / @st.fragment(run_every=30))"""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __call__(self, *a, **_k):
        if len(a) == 1 and callable(a[0]):
            return a[0]          # ใช้เป็น decorator → คืนฟังก์ชันเดิม
        return self

    def __getattr__(self, _name):
        return _noop


def _noop(*a, **_k):
    if len(a) == 1 and callable(a[0]) and not _k:
        return a[0]              # decorator แบบไม่มีวงเล็บ (@st.fragment)
    return _Ctx()


def _columns(spec=2, **_k):
    """คืนจำนวนคอลัมน์ให้ตรงกับที่โค้ดขอ — ไม่งั้น unpack ไม่ได้"""
    try:
        n = spec if isinstance(spec, int) else len(spec)
    except TypeError:
        n = 2
    return [_Ctx() for _ in range(max(1, n))]


def _tabs(labels=(), **_k):
    return [_Ctx() for _ in range(max(1, len(labels) or 1))]


def make_streamlit():
    """สร้าง module streamlit ปลอม 1 ตัว (สดใหม่ทุกครั้ง)"""
    st = types.ModuleType('streamlit')
    st.session_state = SS()
    st.calls = {'error': [], 'warning': [], 'info': [], 'success': [],
                'markdown': [], 'caption': [], 'stop': 0, 'rerun': 0}

    def _rec(kind):
        def _f(msg='', *_a, **_k):
            st.calls[kind].append(str(msg))
            return _Ctx()
        return _f

    for _k in ('error', 'warning', 'info', 'success', 'markdown', 'caption'):
        setattr(st, _k, _rec(_k))

    def _stop(*_a, **_k):
        st.calls['stop'] += 1

    def _rerun(*_a, **_k):
        st.calls['rerun'] += 1

    st.stop = _stop
    st.rerun = _rerun
    st.secrets = {}
    # ทุกอย่างที่เหลือ (st.columns, st.button, st.form, ...) = no-op ที่ไม่พัง
    st.__getattr__ = lambda _n: _noop
    for _n in ('container', 'form', 'expander', 'popover',
               'button', 'form_submit_button', 'text_input', 'number_input',
               'selectbox', 'radio', 'checkbox', 'metric', 'dataframe',
               'plotly_chart', 'divider', 'write', 'toast', 'title', 'header',
               'subheader', 'spinner', 'empty', 'sidebar', 'fragment',
               'cache_data', 'cache_resource', 'set_page_config'):
        setattr(st, _n, _noop)
    st.columns = _columns
    st.tabs = _tabs
    st.query_params = {}
    return st


def install(extra_modules=True):
    """ยัด streamlit ปลอมเข้า sys.modules — เรียกก่อน import โมดูลของแอป
    คืน module streamlit ปลอมไว้ให้ตรวจ st.session_state / st.calls"""
    st = make_streamlit()
    sys.modules['streamlit'] = st
    if extra_modules:
        comp = types.ModuleType('streamlit.components')
        v1 = types.ModuleType('streamlit.components.v1')
        v1.html = _noop
        v1.iframe = _noop
        comp.v1 = v1
        st.components = comp
        sys.modules['streamlit.components'] = comp
        sys.modules['streamlit.components.v1'] = v1
    return st
