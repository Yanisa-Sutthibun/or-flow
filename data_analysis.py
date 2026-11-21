# -*- coding: utf-8 -*-
"""
data_analysis.py : 🔬 แท็บ Data analysis ของระบบจริง (มุกกี้สั่ง 20 พ.ย. 2026)
════════════════════════════════════════════════════════════════════════════
หน้าวิเคราะห์ข้อมูลจากสถิติ สำหรับหัวหน้าห้องผ่าตัด

สิทธิ์ : ทุกคนเห็นแท็บ แต่เนื้อหาเปิดด้วย "รหัสเฉพาะ" ที่ตั้งใน Secrets ชื่อ analysis_code
  · 🔑 22 พ.ย. 2026 (มุกกี้สั่ง): ช่วงนี้รหัสผู้ดูแลระบบ (admin_pin) เปิดได้ด้วย
    และผู้ที่เข้าระบบด้วยรหัสผู้ดูแลอยู่แล้วเห็นเนื้อหาเลย ไม่ต้องกรอกซ้ำ
  · รหัสหน่วยงาน (app_password) เปิดไม่ได้
  · 🔒 fail-closed : ไม่ได้ตั้งทั้ง analysis_code และ admin_pin = หน้านี้ปิดสนิท
  · ปลดล็อกต่อ session (ปิดเบราว์เซอร์หรือออกจากระบบ = ล็อกใหม่) ใส่ผิดเกิน 5 ครั้ง = พักทั้ง session
  · ห้าม hardcode รหัสในไฟล์ อ่านจาก st.secrets ตอนรันเท่านั้น

เนื้อหา : พยาบาลรายบุคคล (21 พ.ย. 2026) ดูหัวข้อ 👩‍⚕️ ใน _render_body
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


def _admin_pin() -> str:
    try:
        from main_or_db import get_admin_pin
        return str(get_admin_pin() or '').strip()
    except Exception:
        return ''


def code_configured() -> bool:
    return bool(_code() or _admin_pin())


def check_code(entered) -> bool:
    """เทียบรหัสแบบ constant-time กับ analysis_code หรือ admin_pin · ไม่ตั้งรหัสหรือกรอกว่าง = ไม่ผ่านเสมอ"""
    got = str(entered or '').strip()
    if not got:
        return False
    ok = False
    for want in (_code(), _admin_pin()):
        if want and hmac.compare_digest(got.encode('utf-8'), want.encode('utf-8')):
            ok = True
    return ok


def is_unlocked() -> bool:
    if st.session_state.get('role') == 'admin' and st.session_state.get('authenticated'):
        return True
    return bool(code_configured() and st.session_state.get(_K_OPEN) is True)


def _render_gate():
    ss = st.session_state
    st.markdown(
        '<div style="font-size:22px;font-weight:700;color:#0f172a;">🔬 Data analysis</div>'
        '<div style="color:#64748b;font-size:var(--fs-meta);margin:4px 0 12px;">'
        'หน้าวิเคราะห์ข้อมูลสำหรับหัวหน้าห้องผ่าตัด เปิดด้วยรหัสเฉพาะของหน้านี้หรือรหัสผู้ดูแลระบบ</div>',
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


# ════════════════════════════════════════════════════════════════════════════
# 👩‍⚕️ พยาบาลรายบุคคล (มุกกี้สั่ง 21 พ.ย. 2026) : ใช้ภายในหน่วยงาน ไม่ใช้ในงานวิจัย
#    1. สุดยอด scrub / circulate : เข้าเคสมากที่สุด และรวมเวลานานที่สุด
#    2. น้องใหม่ตามระดับ Benner (Novice ไม่ถึง 1 ปี · Advanced beginner 1 ถึง 2 ปี)
#       อายุงานประมาณจาก "เคสแรกที่พบในฐานข้อมูล" ไม่ใช่วันเริ่มงานจริง
#    ชื่อแสดงแบบ ชื่อต้น + อักษรแรกนามสกุล (มุกกี้เคาะ 21 พ.ย. 2026 : คนในองค์กรรู้กันอยู่แล้ว)
#    ข้อมูล : main_or_db.get_nurse_stats() (ตาราง cases ที่มีชื่อ scrub / circulate)
# ════════════════════════════════════════════════════════════════════════════
import re as _re

_MIN_CASES = 30     # ตัดชื่อที่พบรวมไม่ถึงเท่านี้ (สะกดต่าง นักศึกษา คนจากหน่วยอื่น)
_PREF = _re.compile(r'^(?:(?:[ก-ฮ]{1,2}\.){2,4}(?:หญิง)?|นางสาว|นาง|นาย|น\.ส\.)\s*')


def full_key(raw) -> str:
    """ชื่อสำหรับจัดกลุ่ม : ตัดยศ/คำนำหน้าและช่องว่างเกิน (ยศเปลี่ยนข้ามปีก็ยังเป็นคนเดียวกัน)"""
    t = str(raw or '').replace('_x000D_', ' ').strip()
    if not t or _re.search(r'[A-Za-z]', t):
        return ''
    return _re.sub(r'\s+', ' ', _PREF.sub('', t)).strip()


def short_name(key: str) -> str:
    """ชื่อต้น + อักษรแรกนามสกุล เช่น 'สมใจ ใจดี' → 'สมใจ ใ.'"""
    parts = key.split(' ')
    if len(parts) < 2:
        return parts[0]
    last = parts[-1]
    return f"{parts[0]} {last if last.endswith('.') else last[0] + '.'}"   # ย่อแล้ว (มาจาก staff_map) คงไว้


def summarize(nurse_cases, year_ce: int, ref_date=None, min_cases: int = _MIN_CASES) -> dict:
    """logic ล้วน (ไม่แตะ streamlit) · nurse_cases = ผลจาก get_nurse_stats()['nurse_cases']"""
    import pandas as pd
    df = nurse_cases.copy()
    if df.empty:
        return {'rows': 0}
    df['key'] = df['nurse_name'].map(full_key)
    df = df[df['key'] != '']
    df['op_date'] = pd.to_datetime(df['op_date'], errors='coerce')
    df = df[df['op_date'].notna()]
    cnt = df.groupby('key').size()
    df = df[df['key'].isin(cnt[cnt >= min_cases].index)]
    if df.empty:
        return {'rows': 0}
    ref = pd.Timestamp(ref_date) if ref_date is not None else df['op_date'].max()
    first = df.groupby('key')['op_date'].min()
    y = df[df['op_date'].dt.year == year_ce]
    dur = pd.to_numeric(y['actual_duration_min'], errors='coerce')
    y = y.assign(dur=dur.where((dur > 0) & (dur <= 24 * 60)))
    top = {}
    for role in ('Scrub', 'Circulate'):
        g = y[y['role'] == role].groupby('key').agg(cases=('case_id', 'count'), mins=('dur', 'sum'))
        g['hours'] = (g['mins'] / 60).round(0)
        top[role] = {'cases': g.sort_values('cases', ascending=False).head(5),
                     'hours': g.sort_values('mins', ascending=False).head(5)}
    months = (ref - first).dt.days / 30.44
    new = []
    for k, m in months.sort_values().items():
        if m >= 24 or k not in set(y['key']):
            continue
        s = df[df['key'] == k]
        new.append({'key': k, 'name': short_name(k),
                    'level': 'Novice' if m < 12 else 'Advanced beginner',
                    'months': int(round(m)), 'first': first[k].strftime('%d/%m/') + str(first[k].year + 543),
                    'cases': len(s), 'scrub': int((s['role'] == 'Scrub').sum()),
                    'circ': int((s['role'] == 'Circulate').sum())})
    return {'rows': len(y), 'active': int(y['key'].nunique()), 'top': top, 'new': new, 'df': df}


@st.cache_data(ttl=900, show_spinner="กำลังโหลดข้อมูลพยาบาล…")
def _load_nurse_cases():
    from main_or_db import get_nurse_stats
    return get_nurse_stats()['nurse_cases']


def _hbar(g, col, unit, title):
    import plotly.express as px
    from main_or_admin import _story_bars, _story_head
    _story_head(title)
    d = g.reset_index().iloc[::-1]
    d['label'] = d['key'].map(short_name)
    fig = px.bar(d, x=col, y='label', orientation='h',
                 text=d[col].map(lambda v: f"{v:,.0f} {unit}"))
    _story_bars(fig, list(d[col]), '#1D6FE0', horizontal=True)
    fig.update_layout(height=230, margin=dict(l=0, r=40, t=0, b=0))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})


def _render_body():
    try:
        nc = _load_nurse_cases()
    except Exception as _ex:
        st.error("โหลดข้อมูลพยาบาลไม่สำเร็จ : ลองกด 🔄 รีเฟรช อีกครั้ง")
        print(f"[data_analysis] load fail: {_ex}")
        return
    if nc is None or nc.empty:
        st.info("ยังไม่มีข้อมูลชื่อพยาบาลในฐานข้อมูล")
        return
    import pandas as pd
    years = sorted(pd.to_datetime(nc['op_date'], errors='coerce').dt.year.dropna().astype(int).unique(), reverse=True)
    _y = st.selectbox("ปี", [y + 543 for y in years], index=0, key="da_year")
    R = summarize(nc, int(_y) - 543)
    if not R.get('rows'):
        st.info(f"ปี {_y} ยังไม่มีเคสที่บันทึกชื่อพยาบาล")
        return
    new = R['new']
    new_keys = {n['key'] for n in new}
    top_sc = R['top']['Scrub']['cases']
    n_new_top = sum(1 for k in top_sc.index if k in new_keys)

    # 3 วินาที : ตัวเลขหลัก
    c1, c2, c3 = st.columns(3)
    c1.metric("พยาบาลที่เข้าเคสในปีนี้", f"{R['active']} คน")
    c2.metric("น้องใหม่ (อายุงานไม่ถึง 2 ปี)", f"{len(new)} คน")
    c3.metric("น้องใหม่ที่ติด 5 อันดับ scrub", f"{n_new_top} จาก {len(top_sc)} คน")

    # 30 วินาที : สุดยอด scrub / circulate
    st.markdown("### 1 : สุดยอด Scrub และ Circulate")
    a, b = st.columns(2)
    for col, role, th in ((a, 'Scrub', 'scrub'), (b, 'Circulate', 'circulate')):
        T = R['top'][role]
        with col:
            if T['cases'].empty:
                st.caption(f"ยังไม่มีข้อมูล {th}")
                continue
            k1, v1 = T['cases'].index[0], int(T['cases'].iloc[0]['cases'])
            _hbar(T['cases'], 'cases', 'เคส', f"{short_name(k1)} {th} มากที่สุด {v1:,} เคส")
            k2, v2 = T['hours'].index[0], T['hours'].iloc[0]['hours']
            _hbar(T['hours'], 'hours', 'ชม.', f"{short_name(k2)} {th} รวมนานที่สุด {v2:,.0f} ชั่วโมง")

    # 300 วินาที : น้องใหม่รายคน
    st.markdown("### 2 : น้องใหม่ตามระดับ Benner")
    if not new:
        st.info("ปีนี้ไม่พบน้องใหม่ที่อายุงานไม่ถึง 2 ปี")
    else:
        tb = pd.DataFrame(new)[['name', 'level', 'months', 'cases', 'scrub', 'circ', 'first']]
        tb.columns = ['ชื่อ', 'ระดับ', 'อายุงาน (เดือน)', 'เคสทั้งหมด', 'scrub', 'circulate', 'เคสแรกที่พบ']
        st.dataframe(tb, hide_index=True, width='stretch')
        pick = st.selectbox("ดูรายละเอียดของ", [n['name'] for n in new], key="da_new_pick")
        n = next(x for x in new if x['name'] == pick)
        s = R['df'][R['df']['key'] == n['key']]
        from main_or_db import DIV_CODE_MAP
        def _div(v):
            try:
                return DIV_CODE_MAP.get(str(int(float(v))), 'อื่นๆ')
            except (TypeError, ValueError):
                return 'ไม่ระบุ'
        dv = s['division_code'].map(_div).value_counts().head(6)
        d1, d2 = st.columns(2)
        with d1:
            _hbar(pd.DataFrame({'key': dv.index, 'n': dv.values}).set_index('key'), 'n', 'เคส',
                  f"{n['name']} เข้าสาขา{dv.index[0]} มากที่สุด {int(dv.iloc[0]):,} เคส")
        with d2:
            pr = s['procedure_name'].fillna('').astype(str).str.strip()
            pr = pr[pr != ''].value_counts().head(10)
            st.markdown(f"**หัตถการที่เข้าบ่อย 10 อันดับ** (จากทั้งหมด {s['procedure_name'].nunique():,} ชนิด)")
            st.dataframe(pd.DataFrame({'หัตถการ': pr.index, 'เคส': pr.values}), hide_index=True, width='stretch')
    st.caption("ใช้วางแผนหมุนเวียนน้องใหม่ : ดูว่าใครยังเข้าสาขาไหนน้อย หรือได้ circulate น้อยเมื่อเทียบกับ scrub · "
               "นับ 1 เคสต่อพยาบาลทุกคนที่มีชื่อในช่อง scrub หรือ circulate · ชั่วโมง = เวลาเข้าห้องถึงออกห้อง · "
               f"ตัดชื่อที่พบรวมไม่ถึง {_MIN_CASES} เคส · ระดับ Benner ประมาณจากเคสแรกที่พบในข้อมูล ไม่ใช่วันเริ่มงานจริง")
