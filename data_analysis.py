# -*- coding: utf-8 -*-
"""
data_analysis.py : 🔍 แท็บ Data analysis ของระบบจริง (มุกกี้สั่ง 20 พ.ย. 2026)
════════════════════════════════════════════════════════════════════════════
หน้าวิเคราะห์ข้อมูลจากสถิติ สำหรับหัวหน้าห้องผ่าตัด

สิทธิ์ : ทุกคนเห็นแท็บ แต่เนื้อหาเปิดด้วย "รหัสเฉพาะ" ที่ตั้งใน Secrets ชื่อ analysis_code
  · 🔑 22 พ.ย. 2026 (มุกกี้สั่ง): ช่วงนี้รหัสผู้ดูแลระบบ (admin_pin) เปิดได้ด้วย
    และผู้ที่เข้าระบบด้วยรหัสผู้ดูแลอยู่แล้วเห็นเนื้อหาเลย ไม่ต้องกรอกซ้ำ
  · รหัสหน่วยงาน (app_password) เปิดไม่ได้
  · 🔒 fail-closed : ไม่ได้ตั้งทั้ง analysis_code และ admin_pin = หน้านี้ปิดสนิท
  · ปลดล็อกต่อ session (ปิดเบราว์เซอร์หรือออกจากระบบ = ล็อกใหม่) ใส่ผิดเกิน 5 ครั้ง = พักทั้ง session
  · ห้าม hardcode รหัสในไฟล์ อ่านจาก st.secrets ตอนรันเท่านั้น

เนื้อหา : หน้ารวม 3 การ์ด (22 พ.ย. 2026) Nurse of the Year · Novice · แนวโน้มการทำงาน ดูหัวข้อ 🃏
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
        '<div style="font-size:22px;font-weight:700;color:#0f172a;">🔍 Data analysis</div>'
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
    """🔍 จุดเข้าเดียวของแท็บ · เนื้อหาวิเคราะห์เติมใน _render_body เท่านั้น (อยู่หลังด่านรหัสเสมอ)"""
    if not is_unlocked():
        _render_gate()
        return
    _h, _b = st.columns([5, 1], vertical_alignment="center")
    with _h:
        st.markdown('<div style="font-size:22px;font-weight:700;color:#0f172a;">'
                    '🔍 Data analysis</div>', unsafe_allow_html=True)
    with _b:
        if st.button("ล็อกหน้านี้", key="da_lock", width='stretch',
                     help="ปิดหน้านี้กลับ ต้องกรอกรหัสใหม่เมื่อเปิดครั้งถัดไป"):
            st.session_state[_K_OPEN] = False
            st.rerun()
    _render_body()


# ════════════════════════════════════════════════════════════════════════════
# 🃏 เนื้อหา 3 การ์ด (มุกกี้เคาะ mock-up 21 พ.ย. 2026 · ลงโค้ด 22 พ.ย. 2026)
#    ใช้ภายในหน่วยงาน ไม่ใช้ในงานวิจัย · นับตามปีงบประมาณ (ปีงบ 2569 = 1 ต.ค. 68 ถึง 30 ก.ย. 69)
#    1. Nurse of the Year : คะแนนรวมจำนวนเคส + ชั่วโมง น้ำหนักเท่ากัน แยก scrub / circulate
#    2. Novice : น้องใหม่ตามแนวคิด Novice to Expert ของ Patricia Benner
#       = เคสแรกที่พบอยู่ในปีงบนั้น และไม่เคยพบในข้อมูลก่อนหน้า (นับเฉพาะ Novice)
#    3. แนวโน้มการทำงาน + เจาะลึกกำลังคนพยาบาล : แสดงตัวเลขตามที่ปรากฏ (มุกกี้สั่ง 21 พ.ย. 2026)
#    ชื่อแสดงแบบ ชื่อต้น + อักษรแรกนามสกุล (มุกกี้เคาะ 21 พ.ย. 2026 : คนในองค์กรรู้กันอยู่แล้ว)
#    ⛔ logic ส่วนนี้ห้าม import streamlit (ทดสอบได้ด้วย python เปล่า)
# ════════════════════════════════════════════════════════════════════════════
import re as _re

_MIN_CASES = 30     # ตัดชื่อที่พบในปีงบไม่ถึงเท่านี้ (สะกดต่าง นักศึกษา คนจากหน่วยอื่น)
_CAPABLE = 10       # เข้าสาขานั้นอย่างน้อยเท่านี้ ถือว่าเข้าสาขานั้นได้
_LATE_MIN = 16 * 60 + 30
# 🎖️ 22 พ.ย. 2026 (มุกกี้สั่ง ตัดยศกับคำนำหน้าออกให้หมด): เพิ่ม "ว่าที่" (พบ 15,121 ครั้งในไฟล์ intraop 64-69)
#    และยอมให้มีช่องว่างระหว่างยศ เช่น "ว่าที่ พ.ต.ต. หญิง"
_PREF = _re.compile(r'^(?:ว่าที่\s*)?(?:(?:[ก-ฮ]{1,2}\.\s*){2,4}(?:หญิง)?|นางสาว|นาง|นาย|น\.ส\.)?\s*')
TH_MON = ('ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.')
FY_MONTHS = (10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9)


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


def fy_of(ts) -> int:
    """ปีงบประมาณ (พ.ศ.) : ต.ค. ขึ้นปีงบใหม่"""
    return int(ts.year + 543 + (1 if ts.month >= 10 else 0))


def fy_range_text(fy: int) -> str:
    return f'1 ต.ค. {str(fy - 1)[-2:]} ถึง 30 ก.ย. {str(fy)[-2:]}'


def _dt(v):
    import pandas as pd
    t = pd.to_datetime(v, errors='coerce')
    return t


def prep(raw, div_map=None):
    """raw = แถวเคสจากตาราง cases (unmask แล้ว) → (C ระดับเคส, L ระดับพยาบาลต่อเคส)
    C : case_id date fy dur div start_min end_min late · L : key role case_id date fy dur div proc"""
    import pandas as pd
    import numpy as np
    df = raw.copy()
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    df['date'] = pd.to_datetime(df['op_date'], errors='coerce')
    df = df[df['date'].notna()].copy()
    df['fy'] = df['date'].map(fy_of)
    dur = pd.to_numeric(df.get('actual_duration_min'), errors='coerce')
    df['dur'] = dur.where((dur > 0) & (dur <= 24 * 60))
    dm = div_map or {}

    def _div(v):
        try:
            return dm.get(str(int(float(v))), 'อื่น ๆ')
        except (TypeError, ValueError):
            return 'ไม่ระบุ'
    df['div'] = df['division_code'].map(_div)
    st_ = _dt(df.get('in_or_at')) if 'in_or_at' in df else pd.Series(pd.NaT, index=df.index)
    en_ = _dt(df.get('op_end_at')) if 'op_end_at' in df else pd.Series(pd.NaT, index=df.index)
    df['start_min'] = st_.dt.hour * 60 + st_.dt.minute
    df['end_min'] = en_.dt.hour * 60 + en_.dt.minute
    cross = (en_.dt.normalize() > df['date'].dt.normalize()) | (en_ < st_)
    late = (df['end_min'] > _LATE_MIN) | cross.fillna(False)
    df['late'] = np.where(en_.notna(), late, np.nan)
    C = df[['case_id', 'date', 'fy', 'dur', 'div', 'start_min', 'end_min', 'late']].reset_index(drop=True)
    rows = []
    for r in df.itertuples(index=False):
        for role, col in (('scrub', 'scrub_nurse'), ('circ', 'circ_nurse')):
            for nm in str(getattr(r, col) or '').split(','):
                k = full_key(nm)
                if k:
                    rows.append((k, role, r.case_id, r.date, r.fy, r.dur, r.div,
                                 str(getattr(r, 'procedure_name', '') or '').strip()))
    L = pd.DataFrame(rows, columns=['key', 'role', 'case_id', 'date', 'fy', 'dur', 'div', 'proc'])
    if not L.empty:
        L = L.drop_duplicates(['key', 'role', 'case_id'])
    return C, L


def active_keys(L, fy, min_cases=_MIN_CASES):
    y = L[L['fy'] == fy]
    n = y.groupby('key').size()
    return set(n[n >= min_cases].index)


def nurse_of_year(L, fy, min_cases=_MIN_CASES, top=3):
    """คะแนน = (เคส ÷ เคสสูงสุด + ชั่วโมง ÷ ชั่วโมงสูงสุด) ÷ 2 × 100 เทียบในปีงบและบทบาทเดียวกัน"""
    out = {}
    act = active_keys(L, fy, min_cases)
    y = L[(L['fy'] == fy) & (L['key'].isin(act))]
    for role in ('scrub', 'circ'):
        g = y[y['role'] == role].groupby('key').agg(cases=('case_id', 'size'), mins=('dur', 'sum'))
        if g.empty:
            out[role] = []
            continue
        g['hours'] = g['mins'] / 60
        mc, mh = g['cases'].max(), max(g['hours'].max(), 1e-9)
        g['score'] = ((g['cases'] / mc + g['hours'] / mh) / 2 * 100).round(0)
        g = g.sort_values(['score', 'cases'], ascending=False)
        out[role] = [dict(key=k, cases=int(r.cases), hours=float(r.hours), score=int(r.score),
                          most_cases=bool(r.cases == mc), most_hours=bool(r.hours >= mh - 1e-9))
                     for k, r in g.head(top).iterrows()]
    return out


def novices(L, fy, min_cases=_MIN_CASES):
    """Novice ของปีงบ = เคสแรกที่พบอยู่ในปีงบนั้น ไม่เคยพบก่อนหน้า และมีเคสรวมอย่างน้อย min_cases
    ปีงบแรกสุดของข้อมูลหาไม่ได้ (ไม่รู้ว่าก่อนหน้านั้นเคยมีหรือไม่) คืน []"""
    if L.empty or fy <= int(L['fy'].min()):
        return []
    first = L.groupby('key')['date'].min()
    last_date = L['date'].max()
    keys = [k for k, d in first.items() if fy_of(d) == fy]
    out = []
    for k in keys:
        s = L[L['key'] == k]
        if len(s) < min_cases:
            continue
        pr = s['proc'][s['proc'] != ''].value_counts()
        out.append(dict(key=k, cases=len(s), scrub=int((s['role'] == 'scrub').sum()),
                        circ=int((s['role'] == 'circ').sum()), hours=float(s['dur'].sum() / 60),
                        first=first[k], months=int(round((last_date - first[k]).days / 30.44)),
                        divs=s['div'].value_counts(), procs=pr.head(10), nprocs=int(pr.size)))
    return sorted(out, key=lambda x: -x['cases'])


def _fy_month_index(ts):
    return FY_MONTHS.index(ts.month)


def trends(C, L, fy, nov_keys=()):
    """แนวโน้มปีงบ fy เทียบเดือนเดียวกันของปีงบก่อน (เทียบเฉพาะเดือนที่มีข้อมูลทั้งสองปี)"""
    import numpy as np
    c1, c0 = C[C['fy'] == fy], C[C['fy'] == fy - 1]
    m1 = c1['date'].map(_fy_month_index).value_counts().reindex(range(12), fill_value=0)
    m0 = c0['date'].map(_fy_month_index).value_counts().reindex(range(12), fill_value=0)
    common = [i for i in range(12) if m1[i] > 0 and m0[i] > 0]
    cm1 = c1[c1['date'].map(_fy_month_index).isin(common)]
    cm0 = c0[c0['date'].map(_fy_month_index).isin(common)]
    R = dict(n=len(c1), months_now=[int(v) for v in m1], months_prev=[int(v) for v in m0], common=common,
             n_common_now=len(cm1), n_common_prev=len(cm0),
             dur_now=float(cm1['dur'].mean()) if len(cm1) else np.nan,
             dur_prev=float(cm0['dur'].mean()) if len(cm0) else np.nan,
             late_now=float(cm1['late'].dropna().mean() * 100) if cm1['late'].notna().any() else np.nan,
             late_prev=float(cm0['late'].dropna().mean() * 100) if cm0['late'].notna().any() else np.nan)
    # สาขา : เทียบเดือนเดียวกัน
    dv1, dv0 = cm1['div'].value_counts(), cm0['div'].value_counts()
    divs = []
    for d in set(dv1.index) | set(dv0.index):
        a, b = int(dv1.get(d, 0)), int(dv0.get(d, 0))
        if a + b >= 100 and b > 0 and d not in ('ไม่ระบุ', 'อื่น ๆ'):
            divs.append(dict(div=d, now=a, prev=b, pct=(a - b) / b * 100))
    R['divs'] = sorted(divs, key=lambda x: -x['pct'])
    # ภาระงานต่อคนต่อเดือน
    wl = []
    for f in (fy - 1, fy):
        y = L[L['fy'] == f]
        y = y[y['date'].map(_fy_month_index).isin(common)]
        if y.empty:
            wl.append([None] * 12)
            continue
        mi = y['date'].map(_fy_month_index)
        per = y.groupby(mi).size() / y.groupby(mi)['key'].nunique()
        wl.append([float(per[i]) if i in per.index else None for i in range(12)])
    R['workload_prev'], R['workload_now'] = wl
    # น้องใหม่ : เคสเฉลี่ยต่อคนต่อเดือน นับจากเดือนแรก
    ramp = []
    if nov_keys:
        s = L[L['key'].isin(set(nov_keys))].copy()
        s['ym'] = s['date'].dt.year * 12 + s['date'].dt.month
        s['k0'] = s.groupby('key')['ym'].transform('min')
        s['mi'] = s['ym'] - s['k0']
        last_ym = L['date'].max().year * 12 + L['date'].max().month
        span = int(min(last_ym - s.groupby('key')['ym'].min()))
        for i in range(span + 1):
            t = s[s['mi'] == i]
            n = len(nov_keys)
            ramp.append(dict(m=i + 1, scrub=float((t['role'] == 'scrub').sum() / n),
                             circ=float((t['role'] == 'circ').sum() / n)))
    R['ramp'] = ramp
    return R


def deep(C, L, fy, nov_keys=(), min_cases=_MIN_CASES):
    """เจาะลึกกำลังคนพยาบาลปีงบ fy : ตัวเลขตามที่ปรากฏ"""
    import numpy as np
    c = C[C['fy'] == fy]
    act = active_keys(L, fy, min_cases)
    y = L[(L['fy'] == fy) & (L['key'].isin(act))]
    R = dict(n=len(c), n_active=len(act))
    # ชั่วโมงเข้าห้อง × วัน
    cs = c[c['start_min'].notna()]
    R['n_timed'] = len(cs)
    heat = np.zeros((7, 24), dtype=int)
    for wd, h in zip(cs['date'].dt.weekday, (cs['start_min'] // 60).astype(int)):
        heat[wd, h] += 1
    R['heat'] = heat
    R['after16'] = int((cs['start_min'] >= 16 * 60).sum())
    # พยาบาล × สาขา
    mx = y.groupby(['key', 'div']).size().unstack(fill_value=0)
    if not mx.empty:
        dtot = c['div'].value_counts()
        cols = [d for d in dtot.index if dtot[d] >= 30 and d in mx.columns and d not in ('ไม่ระบุ', 'อื่น ๆ')]
        mx = mx.reindex(columns=cols, fill_value=0)
        mx = mx.loc[mx.sum(axis=1).sort_values(ascending=False).index]
    R['mx'] = mx
    R['capable'] = {d: int((mx[d] >= _CAPABLE).sum()) for d in mx.columns} if not mx.empty else {}
    # รายคน : เคสจบเย็น · จำนวนเคส · สัดส่วน scrub
    lt = c.set_index('case_id')['late']
    yy = y.assign(late=y['case_id'].map(lt))
    per = yy.groupby('key').agg(cases=('case_id', 'size'), late=('late', lambda v: float(np.nansum(v.astype(float)))),
                                timed=('late', lambda v: int(v.notna().sum())),
                                scrub=('role', lambda v: int((v == 'scrub').sum())))
    if not per.empty:
        per['late_pct'] = np.where(per['timed'] > 0, per['late'] / per['timed'].clip(lower=1) * 100, np.nan)
        per['scrub_pct'] = per['scrub'] / per['cases'] * 100
    R['per'] = per
    R['late_all'] = float(yy['late'].dropna().astype(float).mean() * 100) if yy['late'].notna().any() else np.nan
    # น้องใหม่จับคู่กับใคร (scrub กับ circulate ในเคสเดียวกัน)
    nv = set(nov_keys)
    L9 = L[L['fy'] == fy]
    sc = L9[L9['role'] == 'scrub'][['case_id', 'key']].rename(columns={'key': 's'})
    cc = L9[L9['role'] == 'circ'][['case_id', 'key']].rename(columns={'key': 'c'})
    pp = sc.merge(cc, on='case_id')
    pp = pp[pp['s'] != pp['c']]
    pairs = []
    for k in nv:
        import pandas as pd
        part = pd.concat([pp[pp['s'] == k]['c'], pp[pp['c'] == k]['s']])
        if part.empty:
            continue
        vc = part.value_counts()
        pairs.append(dict(key=k, n_pairs=int(len(part)), n_partners=int(vc.size),
                          top_share=float(vc.iloc[0] / len(part) * 100),
                          with_novice=float(part.isin(nv).mean() * 100),
                          top3=[(str(a), int(b)) for a, b in vc.head(3).items()]))
    R['pairs'] = sorted(pairs, key=lambda x: -x['with_novice'])
    return R


# ════════════════════════════════════════════════════════════════════════════
# 🖼️ ส่วนแสดงผล (HTML ล้วน ตาม mock-up · ⛔ ห้ามมีบรรทัดว่างใน string ที่ส่งเข้า st.markdown)
# ════════════════════════════════════════════════════════════════════════════
import html as _html

_ACC = '#1D6FE0'      # สีเน้นเดียวของทุกกราฟ (ตาม mock-up)
_BASE = '#C9D6E3'
_NEW = '#0B7A6C'      # น้องใหม่
_WARN = '#E07B39'
_K_VIEW = '_da_view'
_WD = ('จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.', 'อา.')
_WDF = ('จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์')
_CSS = ('<style>.da-card{background:#FFFFFF;border:1px solid #E3E9EF;border-radius:16px;padding:20px 22px;'
        'margin:0 0 16px;display:flex;flex-direction:column;gap:12px;color:#12212E}'
        '.da-t{font-size:17px;font-weight:700}.da-s{font-size:13px;color:#5B6B7B}'
        '.da-f{font-size:13px;color:#3E4C59;border-top:1px solid #EEF2F6;padding-top:10px}'
        '.da-kpi{background:#FFFFFF;border:1px solid #E3E9EF;border-radius:14px;padding:14px 16px;margin:0 0 16px;min-height:118px}'
        '.da-kpi b{display:block;font-size:30px;line-height:1.2}.da-kpi span{font-size:13px;color:#5B6B7B}'
        '.da-sec{font-size:22px;font-weight:700;margin:18px 0 8px;color:#12212E}'
        '.da-hub{background:#FFFFFF;border:1px solid #E3E9EF;border-radius:18px;padding:20px;min-height:430px;'
        'display:flex;flex-direction:column;gap:10px;color:#12212E}'
        '.da-hub .px{background:#F1F6FB;border-radius:14px;display:flex;justify-content:center;padding:14px 0}'
        '.da-tag{font-size:12px;font-weight:700;color:#1658B8}.da-ht{font-size:20px;font-weight:700}'
        '.da-hd{font-size:14px;color:#3E4C59;line-height:1.6}'
        '.da-hl{font-size:13px;background:#F5F8FB;border-radius:10px;padding:8px 10px;color:#12212E}</style>')


def _e(s) -> str:
    return _html.escape(str(s))


def _nm(k) -> str:
    return _e(short_name(k))


def _md(h: str):
    st.markdown(h.replace('\n', ''), unsafe_allow_html=True)


def _card(title, sub, body, foot='', minh=0) -> str:
    """minh = ความสูงขั้นต่ำ (px) ใช้กับการ์ดที่วางคู่กันในแถวเดียว ให้สูงเท่ากัน (มุกกี้สั่ง 22 พ.ย. 2026 ดูสมดุลการ์ด)"""
    _st = f' style="min-height:{minh}px"' if minh else ''
    return (f'<div class="da-card"{_st}><div><div class="da-t">{title}</div><div class="da-s">{sub}</div></div>'
            f'{body}' + (f'<div class="da-f">{foot}</div>' if foot else '') + '</div>')


def _hbars(rows, label_w=150, val_w=170, accent_first=True) -> str:
    """rows = [(label_html, value, value_text, color|None)] · เรียงมาแล้ว"""
    if not rows:
        return ''
    mx = max(float(r[1] or 0) for r in rows) or 1
    out = []
    for i, (lab, v, vt, col) in enumerate(rows):
        c = col or (_ACC if (i == 0 and accent_first) else _BASE)
        out.append(f'<div style="display:grid;grid-template-columns:{label_w}px minmax(0,1fr) {val_w}px;'
                   f'align-items:center;gap:10px"><div style="font-size:13px">{lab}</div>'
                   f'<div><div style="width:{max(float(v or 0) / mx * 100, 0.5):.1f}%;height:16px;border-radius:6px;'
                   f'background:{c}"></div></div><div style="font-size:13px;text-align:right">{vt}</div></div>')
    return '<div style="display:flex;flex-direction:column;gap:6px">' + ''.join(out) + '</div>'


def _kpis(items):
    cols = st.columns(len(items))
    for col, (lab, val, unit) in zip(cols, items):
        col.markdown(f'<div class="da-kpi"><span>{lab}</span><b>{val}</b><span>{unit}</span></div>',
                     unsafe_allow_html=True)


def _fmt(v, d=0):
    try:
        import math
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return '-'
    except Exception:
        pass
    return f'{v:,.{d}f}'


# ---------- โหลดข้อมูล ----------
@st.cache_data(ttl=900, show_spinner="กำลังโหลดข้อมูลจากฐานข้อมูล…")
def _load():
    import pandas as pd
    # 📊 ข้อมูลจริงชุดเดียวกับหน้าสถิติย้อนหลัง (ตาราง cases · สถานะเคสที่จบแล้วชุดเดียวกัน) ไม่มีข้อมูลสมมติปน
    from main_or_db import get_conn, DIV_CODE_MAP, _DONE_STATUSES
    from staff_unmask import apply_to_dataframe
    conn = get_conn()
    try:
        raw = pd.read_sql_query(
            "SELECT case_id, op_date, procedure_name, division_code, scrub_nurse, circ_nurse, "
            "actual_duration_min, in_or_at, op_end_at FROM cases "
            f"WHERE status IN {_DONE_STATUSES} "
            "AND (scrub_nurse IS NOT NULL OR circ_nurse IS NOT NULL)", conn)
    finally:
        conn.close()
    raw = apply_to_dataframe(raw)
    return prep(raw, DIV_CODE_MAP)


def _fy_list(C):
    return sorted(C['fy'].unique().tolist(), reverse=True)


def _default_fy(C):
    """ปีงบล่าสุดที่มีข้อมูลอย่างน้อย 6 เดือน (ปีงบที่เพิ่งเริ่มยังไม่ถือเป็นค่าเริ่มต้น)"""
    for f in _fy_list(C):
        if C[C['fy'] == f]['date'].dt.month.nunique() >= 6:
            return f
    return _fy_list(C)[0]


def _fy_note(C, fy) -> str:
    c = C[C['fy'] == fy]
    nm = c['date'].dt.to_period('M').nunique()
    if nm >= 12:
        return f'ปีงบ {fy}'
    last = c['date'].max()
    return f'ปีงบ {fy} : มีข้อมูล {nm} เดือน ถึง {last.day} {TH_MON[last.month - 1]} {str(last.year + 543)[-2:]}'


def _pick_fy(C, key, label='ปีงบประมาณ'):
    fys = _fy_list(C)
    d = _default_fy(C)
    _c, _x = st.columns([1, 3])
    with _c:
        return st.selectbox(label, fys, index=fys.index(d), key=key, format_func=lambda f: f'ปีงบ {f}')


# ---------- หน้ารวมการ์ด ----------
def _view_hub(C, L):
    from da_sprites import NOY, NOV, TR
    fy = _default_fy(C)
    noy = nurse_of_year(L, fy)
    nv = novices(L, fy)
    tr = trends(C, L, fy)
    cap = deep(C, L, fy)['capable']
    sc = noy.get('scrub') or []
    ci = noy.get('circ') or []
    hl1 = (f'Scrub ปีงบ {fy} : {_nm(sc[0]["key"])}<br>Circulate ปีงบ {fy} : {_nm(ci[0]["key"])}'
           if sc and ci else f'ปีงบ {fy} ยังไม่มีข้อมูลพอ')
    hl2 = f'Novice ปีงบ {fy} : {len(nv)} คน<br>กดชื่อเพื่อดูสาขาและหัตถการรายคน'
    chg = ((tr['n_common_now'] - tr['n_common_prev']) / tr['n_common_prev'] * 100) if tr['n_common_prev'] else None
    few = sorted(cap.items(), key=lambda kv: kv[1])[:1]
    hl3 = f'ปีงบ {fy} มี {tr["n"]:,} เคส' + (f' : เดือนเดียวกันกับปีก่อน {chg:+.0f}%' if chg is not None else '')
    if few:
        hl3 += f'<br>สาขา{_e(few[0][0]).replace("ศัลยกรรม", "")} มีคนเข้าได้ {few[0][1]} คน'
    cards = [
        ('noy', NOY, 'การ์ด 1', 'Nurse of the Year',
         'ที่สุดของพยาบาลห้องผ่าตัด ตัดสินจากคะแนนรวมของจำนวนเคสและชั่วโมง', hl1, 'ดู Nurse of the Year'),
        ('nov', NOV, 'การ์ด 2', 'Novice : น้องใหม่',
         'น้องใหม่ตามแนวคิด Novice to Expert ของ Patricia Benner ทำเคสอะไร สาขาไหนไปบ้าง', hl2, 'ดู Novice'),
        ('tr', TR, 'การ์ด 3', 'แนวโน้มการทำงาน',
         'แนวโน้มเทียบปีต่อปี และเจาะลึกกำลังคนพยาบาล : ช่วงเวลาที่งานหนาแน่น พยาบาล × สาขา เคสจบเย็น '
         'การกระจายงาน สมดุล scrub กับ circulate และทีมคู่ของน้องใหม่', hl3, 'ดูแนวโน้ม'),
    ]
    cols = st.columns(3)
    for col, (v, svg, tag, title, desc, hl, btn) in zip(cols, cards):
        with col:
            _md(f'<div class="da-hub"><div class="px">{svg}</div><div class="da-tag">{tag}</div>'
                f'<div class="da-ht">{title}</div><div class="da-hd">{desc}</div><div class="da-hl">{hl}</div></div>')
            if st.button(btn, key=f'da_go_{v}', width='stretch', type='primary'):
                st.session_state[_K_VIEW] = v
                st.rerun()


def _back():
    if st.button('← กลับหน้ารวมการ์ด', key='da_back'):
        st.session_state[_K_VIEW] = 'hub'
        st.rerun()


# ---------- การ์ด 1 : Nurse of the Year ----------
def _winner_card(fy, role, rows, note) -> str:
    th = 'Scrub' if role == 'scrub' else 'Circulate'
    if not rows:
        return _card(f'{th} nurse of the year', note, '<div class="da-s">ยังไม่มีข้อมูลพอ</div>', minh=290)
    w = rows[0]
    badges = ''.join(f'<span style="font-size:12px;background:#EEF4FF;color:#1658B8;border-radius:999px;'
                     f'padding:3px 10px;margin-right:6px">{t}</span>'
                     for t, ok in (('เคสมากที่สุด', w['most_cases']), ('รวมนานที่สุด', w['most_hours'])) if ok)
    rest = ''.join(f'<div style="display:flex;justify-content:space-between;font-size:13px;padding:6px 0;'
                   f'border-top:1px solid #EEF2F6"><span>อันดับ {i + 2} : {_nm(r["key"])} : {r["cases"]:,} เคส · '
                   f'{r["hours"]:,.0f} ชม.</span><b>{r["score"]}</b></div>' for i, r in enumerate(rows[1:]))
    rest += ''.join(f'<div style="font-size:13px;padding:6px 0;border-top:1px solid #EEF2F6;color:#94A3B8">'
                    f'อันดับ {i + 2} : -</div>' for i in range(len(rows) - 1, 2))
    body = (f'<div style="display:flex;justify-content:space-between;align-items:flex-end;gap:12px">'
            f'<div><div style="font-size:26px;font-weight:700">{_nm(w["key"])}</div>'
            f'<div style="font-size:14px;color:#3E4C59">{w["cases"]:,} เคส · {w["hours"]:,.0f} ชั่วโมง</div>'
            f'<div style="margin-top:6px">{badges}</div></div>'
            f'<div style="text-align:right"><div style="font-size:30px;font-weight:700;color:{_ACC}">{w["score"]}</div>'
            f'<div class="da-s">คะแนน</div></div></div>{rest}')
    return _card(f'{th} nurse of the year', note, body, minh=290)


def _view_noy(C, L):
    _back()
    fy = _pick_fy(C, 'da_fy_noy')
    pair = [f for f in (fy - 1, fy) if f in set(C['fy'])]
    _md(f'<div style="margin:4px 0 8px">'
        f'<div><div class="da-sec" style="margin:0">Nurse of the Year</div>'
        f'<div class="da-s">ปีงบ {fy} = {fy_range_text(fy)} · ตัดสินจากคะแนนรวมของจำนวนเคสและชั่วโมง น้ำหนักเท่ากัน</div></div></div>')
    _kpis([(f'เคสปีงบ {fy}', f'{int((C["fy"] == fy).sum()):,}', 'เคส'),
           (f'พยาบาลที่เข้าเคสปีงบ {fy}', f'{len(active_keys(L, fy))}', 'คน'),
           (f'Novice ปีงบ {fy}', f'{len(novices(L, fy))}', 'คน')])
    # 🃏 22 พ.ย. 2026 (มุกกี้สั่ง ดูสมดุลการ์ด): แต่ละปีงบเป็น 1 แถว scrub | circulate คู่กัน สูงเท่ากัน · ปีที่เลือกขึ้นก่อน
    for f in sorted(pair, reverse=True):
        res = nurse_of_year(L, f)
        cols = st.columns(2)
        for col, role in zip(cols, ('scrub', 'circ')):
            with col:
                _md(_winner_card(f, role, res[role], _fy_note(C, f)))
    _md('<div class="da-s" style="line-height:1.7">คะแนน = (จำนวนเคส ÷ จำนวนเคสสูงสุดของปีงบนั้น + ชั่วโมงรวม ÷ '
        'ชั่วโมงสูงสุดของปีงบนั้น) ÷ 2 × 100 : เต็ม 100 เทียบเฉพาะในปีงบและบทบาทเดียวกัน · นับ 1 เคสต่อพยาบาล'
        'ทุกคนที่มีชื่อในช่อง scrub หรือ circulate · ชั่วโมง = เวลาเข้าห้องถึงออกห้อง · '
        f'ตัดชื่อที่พบในปีงบไม่ถึง {_MIN_CASES} เคส</div>')


# ---------- การ์ด 2 : Novice ----------
def _view_nov(C, L):
    _back()
    fy = _pick_fy(C, 'da_fy_nov')
    nv = novices(L, fy)
    _md(f'<div style="margin:4px 0 8px">'
        f'<div><div class="da-sec" style="margin:0">Novice : น้องใหม่ปีงบ {fy}</div>'
        f'<div class="da-s">ตามแนวคิด Novice to Expert ของ Patricia Benner : เคสแรกที่พบอยู่ในปีงบ {fy} '
        f'และไม่เคยพบในข้อมูลก่อนหน้า</div></div></div>')
    if not nv:
        st.info(f'ปีงบ {fy} ไม่พบน้องใหม่ที่เข้าเคสอย่างน้อย {_MIN_CASES} เคส')
        return
    top_div = {}
    for n in nv:
        if len(n['divs']):
            top_div[n['divs'].index[0]] = top_div.get(n['divs'].index[0], 0) + 1
    td = max(top_div.items(), key=lambda kv: kv[1]) if top_div else None
    more_circ = sum(1 for n in nv if n['circ'] > n['scrub'])
    title = (f'น้อง {len(nv)} คนเข้าเคสไปแล้วคนละ {min(n["cases"] for n in nv):,} ถึง {max(n["cases"] for n in nv):,} เคส'
             + (f' : สาขาที่เข้ามากที่สุดคือ {_e(td[0])} ({td[1]} จาก {len(nv)} คน)' if td else '')
             + (f' · มี {more_circ} คนที่ได้ circulate มากกว่า scrub' if more_circ else ''))
    mx = max(n['cases'] for n in nv)
    rows = ''.join(
        f'<div style="display:grid;grid-template-columns:130px minmax(0,1fr) 70px;align-items:center;gap:10px">'
        f'<div style="font-size:13px">{_nm(n["key"])}</div><div style="display:flex;width:{n["cases"] / mx * 100:.0f}%">'
        f'<div style="flex:{n["scrub"]};height:16px;background:{_ACC};border-radius:6px 0 0 6px"></div>'
        f'<div style="flex:{n["circ"]};height:16px;background:{_BASE};border-radius:0 6px 6px 0"></div></div>'
        f'<div style="font-size:13px;text-align:right">{n["cases"]:,}</div></div>' for n in nv)
    leg = (f'<div class="da-s"><span style="display:inline-block;width:10px;height:10px;background:{_ACC};'
           f'border-radius:2px"></span> scrub &nbsp; <span style="display:inline-block;width:10px;height:10px;'
           f'background:{_BASE};border-radius:2px"></span> circulate</div>')
    _md(_card(title, 'จำนวนเคสต่อคน แยก scrub กับ circulate', leg +
              f'<div style="display:flex;flex-direction:column;gap:6px">{rows}</div>'))
    pick = st.selectbox('ดูรายละเอียดของ', [n['key'] for n in nv], format_func=short_name, key='da_nov_pick')
    n = next(x for x in nv if x['key'] == pick)
    f0 = n['first']
    _kpis([('เคสทั้งหมด', f'{n["cases"]:,}', 'เคส'), ('scrub', f'{n["scrub"]:,}', 'เคส'),
           ('circulate', f'{n["circ"]:,}', 'เคส'), ('ชั่วโมงในห้อง', f'{n["hours"]:,.0f}', 'ชั่วโมง')])
    a, b = st.columns(2)
    with a:
        dv = n['divs'].head(8)
        _md(_card(f'{_nm(n["key"])} เข้าสาขา{_e(dv.index[0]).replace("ศัลยกรรม", "")} มากที่สุด {int(dv.iloc[0]):,} เคส',
                  f'เคสแรกที่พบในข้อมูล : {f0.day} {TH_MON[f0.month - 1]} {f0.year + 543} · อายุงานโดยประมาณ {n["months"]} เดือน',
                  _hbars([(_e(k).replace('ศัลยกรรม', '') or _e(k), int(v), f'{int(v):,}', None) for k, v in dv.items()],
                         label_w=150, val_w=60), minh=440))
    with b:
        pr = ''.join(f'<div style="display:flex;justify-content:space-between;gap:10px;font-size:13px;padding:5px 0;'
                     f'border-top:1px solid #EEF2F6"><span>{_e(p)}</span><b>{int(c):,} เคส</b></div>'
                     for p, c in n['procs'].items())
        _md(_card('หัตถการที่เข้าบ่อย 10 อันดับ', f'จากทั้งหมด {n["nprocs"]:,} ชนิด', f'<div>{pr}</div>', minh=440))
    _md('<div class="da-s" style="line-height:1.7">ใช้วางแผนหมุนเวียนน้องใหม่ : ดูว่าใครยังเข้าสาขาไหนน้อย '
        'หรือยังได้ circulate น้อยเมื่อเทียบกับ scrub · อายุงานประมาณจากเคสแรกที่พบในข้อมูล ไม่ใช่วันเริ่มงานจริง</div>')


# ---------- การ์ด 3 : แนวโน้ม + เจาะลึก ----------
def _month_bars(now, prev, common) -> str:
    mx = max([v for v in now + prev if v] or [1])
    cols = ''
    for i in range(12):
        m = TH_MON[FY_MONTHS[i] - 1]
        p = prev[i] if i in common else 0
        cols += (f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px">'
                 f'<div style="font-size:11px;font-weight:700">{now[i] or ""}</div>'
                 f'<div style="display:flex;align-items:flex-end;gap:3px;height:150px">'
                 f'<div style="width:12px;height:{p / mx * 150:.0f}px;background:{_BASE};border-radius:3px 3px 0 0"></div>'
                 f'<div style="width:12px;height:{now[i] / mx * 150:.0f}px;background:{_ACC};border-radius:3px 3px 0 0"></div>'
                 f'</div><div style="font-size:11px;color:#5B6B7B">{m}</div></div>')
    return f'<div style="display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:4px">{cols}</div>'


def _legend(items) -> str:
    return '<div class="da-s">' + ' &nbsp; '.join(
        f'<span style="display:inline-block;width:10px;height:10px;background:{c};border-radius:2px"></span> {t}'
        for c, t in items) + '</div>'


def _view_tr(C, L):
    _back()
    fy = _pick_fy(C, 'da_fy_tr')
    nv = novices(L, fy)
    nvk = [n['key'] for n in nv]
    T = trends(C, L, fy, nvk)
    D = deep(C, L, fy, nvk)
    cm = T['common']
    rng = (f'{TH_MON[FY_MONTHS[cm[0]] - 1]} ถึง {TH_MON[FY_MONTHS[cm[-1]] - 1]}' if cm else '')
    _md(f'<div style="margin:4px 0 8px">'
        f'<div><div class="da-sec" style="margin:0">แนวโน้มการทำงาน</div>'
        f'<div class="da-s">ปีงบ {fy} = {fy_range_text(fy)} · เทียบเดือนเดียวกันของปีงบ {fy - 1} ({rng})</div></div></div>')
    chg = ((T['n_common_now'] - T['n_common_prev']) / T['n_common_prev'] * 100) if T['n_common_prev'] else None
    _kpis([(f'เคสปีงบ {fy}', f'{T["n"]:,}', f'เคส' + (f' ({rng} {chg:+.0f}% จากปีก่อน)' if chg is not None else '')),
           (f'เวลาใช้ห้องเฉลี่ยต่อเคส {rng}', _fmt(T['dur_now']), f'นาที (ปีก่อน {_fmt(T["dur_prev"])})'),
           (f'เคสที่ออกห้องหลัง 16:30 {rng}', _fmt(T['late_now']) + '%', f'(ปีก่อน {_fmt(T["late_prev"])}%)')])
    now, prev = T['months_now'], T['months_prev']
    nz = [i for i in range(12) if now[i] > 0]
    low = min(nz, key=lambda i: now[i]) if nz else None
    if chg is None:
        _ct = ''
    elif abs(chg) < 1:
        _ct = f' : ช่วง {rng} ใกล้เคียงปีก่อน'
    else:
        _ct = f' : ช่วง {rng} {"เพิ่มขึ้น" if chg > 0 else "ลดลง"} {abs(chg):.0f}% จากปีก่อน'
    t1 = (f'ปีงบ {fy} มี {T["n"]:,} เคส' + _ct
          + (f' ต่ำสุดที่ {TH_MON[FY_MONTHS[low] - 1]} {now[low]:,} เคส' if low is not None else ''))
    _md(_card(t1, f'จำนวนเคสรายเดือนปีงบ {fy} เทียบเดือนเดียวกันปีก่อน : {rng} ปีก่อนรวม {T["n_common_prev"]:,} · '
              f'ปีนี้รวม {T["n_common_now"]:,}',
              _legend([(_BASE, f'ปีงบ {fy - 1}'), (_ACC, f'ปีงบ {fy}')]) + _month_bars(now, prev, cm)))
    a, b = st.columns(2)
    with a:
        dv = T['divs']
        if dv:
            up, dn = dv[0], dv[-1]
            rows = [(_e(x['div']).replace('ศัลยกรรม', '') or _e(x['div']), abs(x['pct']), f'{x["pct"]:+.0f}%',
                     _ACC if x is up else (_WARN if x is dn and x['pct'] < 0 else _BASE)) for x in dv]
            _md(_card(f'สาขา{_e(up["div"]).replace("ศัลยกรรม", "")} เปลี่ยนเพิ่มมากที่สุด {up["pct"]:+.0f}% · '
                      f'{_e(dn["div"]).replace("ศัลยกรรม", "")} {dn["pct"]:+.0f}%',
                      f'จำนวนเคส {rng} เทียบช่วงเดียวกันปีก่อน (สาขาที่มีอย่างน้อย 100 เคส)',
                      _hbars(rows, label_w=150, val_w=60, accent_first=False), minh=430))
    with b:
        w1, w0 = T['workload_now'], T['workload_prev']
        v1 = [x for x in w1 if x]
        v0 = [x for x in w0 if x]
        a1 = sum(v1) / len(v1) if v1 else None
        a0 = sum(v0) / len(v0) if v0 else None
        mxw = max(v1 + v0 + [1])
        cols = ''.join(
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px">'
            f'<div style="display:flex;align-items:flex-end;gap:2px;height:120px">'
            f'<div style="width:8px;height:{(w0[i] or 0) / mxw * 120:.0f}px;background:{_BASE};border-radius:2px 2px 0 0"></div>'
            f'<div style="width:8px;height:{(w1[i] or 0) / mxw * 120:.0f}px;background:{_ACC};border-radius:2px 2px 0 0"></div>'
            f'</div><div style="font-size:10px;color:#5B6B7B">{TH_MON[FY_MONTHS[i] - 1]}</div></div>' for i in range(12))
        _md(_card(f'ภาระงานต่อคนเฉลี่ย {_fmt(a1, 1)} เคสต่อเดือน (ปีก่อน {_fmt(a0, 1)})',
                  f'จำนวนครั้งที่เข้าเคส (scrub และ circulate) ต่อพยาบาล 1 คน ต่อเดือน {rng}',
                  _legend([(_BASE, f'ปีงบ {fy - 1}'), (_ACC, f'ปีงบ {fy}')]) +
                  f'<div style="display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:2px">{cols}</div>', minh=430))
    if T['ramp']:
        rp = T['ramp']
        pk = max(rp, key=lambda r: r['scrub'] + r['circ'])
        mxr = max(r['scrub'] + r['circ'] for r in rp) or 1
        cols = ''.join(
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px">'
            f'<div style="font-size:11px;font-weight:700">{r["scrub"] + r["circ"]:.0f}</div>'
            f'<div style="display:flex;flex-direction:column;justify-content:flex-end;height:130px;width:26px">'
            f'<div style="height:{r["circ"] / mxr * 130:.0f}px;background:{_BASE}"></div>'
            f'<div style="height:{r["scrub"] / mxr * 130:.0f}px;background:{_NEW}"></div></div>'
            f'<div style="font-size:11px;color:#5B6B7B">{r["m"]}</div></div>' for r in rp)
        _md(_card(f'น้องใหม่ปีงบ {fy} เข้าเคสเฉลี่ยสูงสุดในเดือนที่ {pk["m"]} ({pk["scrub"] + pk["circ"]:.0f} เคสต่อคน)',
                  f'เคสเฉลี่ยต่อคนต่อเดือน นับจากเดือนแรกที่เข้าเคส : Novice ปีงบ {fy} {len(nv)} คน '
                  f'(แสดงเฉพาะเดือนที่ทุกคนมีข้อมูลครบ)',
                  _legend([(_NEW, 'scrub'), (_BASE, 'circulate')]) +
                  f'<div style="display:flex;gap:10px;align-items:flex-end">{cols}</div>'))
    # ---------- เจาะลึก ----------
    _md(f'<div class="da-sec">เจาะลึก : กำลังคนพยาบาล</div><div class="da-s">ปีงบ {fy} รวมเคสนอกเวลาไว้ก่อน</div>')
    import numpy as np
    H = D['heat']
    if D['n_timed']:
        hmax = int(H.max()) or 1
        pw, ph = np.unravel_index(int(H.argmax()), H.shape)

        def _cc(v):
            if v == 0:
                return '#F5F7FA'
            t = v / hmax
            stops = [(0, (230, 240, 252)), (0.33, (159, 195, 232)), (0.66, (29, 111, 224)), (1, (16, 38, 61))]
            for (u0, a0), (u1, a1) in zip(stops, stops[1:]):
                if t <= u1:
                    k = (t - u0) / (u1 - u0)
                    return '#%02X%02X%02X' % tuple(int(a0[j] + (a1[j] - a0[j]) * k) for j in range(3))
            return '#10263D'
        hdr = ''.join(f'<div style="font-size:11px;color:#5B6B7B;text-align:center">{h}</div>' for h in range(24))
        rows = ''.join(f'<div style="font-size:13px;align-self:center">{_WD[w]}</div>' + ''.join(
            f'<div title="{_WD[w]} {h:02d}:00 : {H[w, h]} เคส" style="height:24px;border-radius:4px;'
            f'background:{_cc(H[w, h])}"></div>' for h in range(24)) for w in range(7))
        _md(_card(f'เคสเข้าห้องหนาแน่นสุดช่วง {ph:02d}:00 วัน{_WDF[pw]} · เคสเริ่มหลัง 16:00 มี {D["after16"]:,} เคส '
                  f'({D["after16"] / D["n_timed"] * 100:.0f}%)',
                  f'จำนวนเคสตามชั่วโมงที่เข้าห้อง × วันในสัปดาห์ ปีงบ {fy} ({D["n_timed"]:,} เคสที่มีเวลาเข้าห้อง) · สีเข้ม = เคสมาก',
                  f'<div style="display:grid;grid-template-columns:36px repeat(24,minmax(0,1fr));gap:3px"><div></div>{hdr}{rows}</div>'))
    mx = D['mx']
    if not mx.empty:
        cap = D['capable']
        few = [d for d in mx.columns if cap[d] <= 5]

        def _short(s):
            return _e(s).replace('ศัลยกรรม', '').strip() or _e(s)

        def _mc(v):
            if v == 0:
                return '#F5F7FA', '#C9D3DD'
            t = min(v / 60, 1)
            return (f'rgb({int(230 - t * 219)},{int(244 - t * 122)},{int(241 - t * 133)})',
                    '#FFFFFF' if t > 0.55 else '#12212E')
        head = ''.join(f'<div style="font-size:11px;font-weight:600;text-align:center;line-height:1.3;'
                       f'color:{"#B5531A" if d in few else "#3E4C59"}">{_short(d)}<div style="font-weight:500">'
                       f'{cap[d]} คน</div></div>' for d in mx.columns)
        body = ''
        for k, r in mx.iterrows():
            tag = f' <span style="font-size:10px;color:{_NEW};font-weight:700">ใหม่</span>' if k in nvk else ''
            cells = ''
            for d in mx.columns:
                bg, fg = _mc(int(r[d]))
                cells += (f'<div style="height:22px;border-radius:3px;background:{bg};color:{fg};font-size:11px;'
                          f'display:flex;align-items:center;justify-content:center;font-weight:{700 if r[d] >= _CAPABLE else 400}">'
                          f'{int(r[d]) or ""}</div>')
            body += f'<div style="font-size:12px;white-space:nowrap;align-self:center">{_nm(k)}{tag}</div>{cells}'
        t = (' · '.join(f'{_short(d)} มีคนเข้าได้ {cap[d]} คน' for d in few) + ' : สาขาที่มีคนเข้าได้ไม่ถึง 5 คน') if few \
            else 'ทุกสาขามีคนเข้าได้อย่างน้อย 6 คน'
        _md(_card(t, f'จำนวนครั้งที่พยาบาลแต่ละคนเข้าเคสแต่ละสาขา ปีงบ {fy} ({len(mx)} คนที่เข้าเคสอย่างน้อย {_MIN_CASES} ครั้ง) · '
                     f'ตัวหนา = {_CAPABLE} ครั้งขึ้นไป ถือว่าเข้าสาขานั้นได้ · ใต้ชื่อสาขาคือจำนวนคนที่เข้าได้',
                  f'<div style="display:grid;grid-template-columns:120px repeat({len(mx.columns)},minmax(0,1fr));gap:3px">'
                  f'<div></div>{head}{body}</div>'))
    per = D['per']
    if not per.empty and per['timed'].sum() > 0:
        lt = per.sort_values('late', ascending=False).head(12)
        hi = per[per['timed'] >= _MIN_CASES].sort_values('late_pct', ascending=False).head(1)
        nvl = per[per.index.isin(nvk)]['late_pct'].dropna()
        rows = [(_nm(k) + (f' <span style="font-size:10px;color:{_NEW};font-weight:700">ใหม่</span>' if k in nvk else ''),
                 r['late'], f'<b>{r["late"]:,.0f}</b> เคส · {r["late_pct"]:.0f}% ของเคสที่เข้า', None) for k, r in lt.iterrows()]
        foot = 'ตัวเลขนับตามชื่อที่บันทึกใน HIS จึงรวมเวรที่แลกกันด้วย'
        if len(hi):
            foot += f' · {_nm(hi.index[0])} มีสัดส่วนสูงสุด {hi.iloc[0]["late_pct"]:.0f}% จาก {int(hi.iloc[0]["timed"])} เคส'
        if len(nvl):
            foot += f' · น้องใหม่อยู่ที่ {nvl.min():.0f}-{nvl.max():.0f}%'
        _md(_card(f'เคสที่จบหลัง 16:30 คิดเป็น {_fmt(D["late_all"])}% ของงานทั้งหมด · {_nm(lt.index[0])} อยู่เคสที่จบเย็นมากสุด '
                  f'{lt.iloc[0]["late"]:,.0f} เคส',
                  f'จำนวนเคสที่ออกจากห้องหลัง 16:30 หรือข้ามเที่ยงคืน ต่อพยาบาล 12 อันดับแรก ปีงบ {fy} · นับทั้ง scrub และ '
                  f'circulate · รวมเคสนอกเวลา', _hbars(rows, label_w=150, val_w=200), foot))
    if not per.empty:
        a, b = st.columns(2)
        with a:
            bins = [(0, 100), (100, 200), (200, 300), (300, 400), (400, 500), (500, 600), (600, 700), (700, 10 ** 6)]
            bl = [f'{_MIN_CASES}-99', '100-199', '200-299', '300-399', '400-499', '500-599', '600-699', '700+']
            cnt = [[int(((per['cases'] >= lo) & (per['cases'] < hi) & (per.index.isin(nvk) == isn)).sum())
                    for lo, hi in bins] for isn in (False, True)]
            bmax = max(x + y for x, y in zip(*cnt)) or 1
            cols = ''.join(
                f'<div style="display:flex;flex-direction:column;justify-content:flex-end;height:200px">'
                f'<div style="font-size:12px;text-align:center;font-weight:700;padding-bottom:4px">{cnt[0][i] + cnt[1][i]}</div>'
                + (f'<div style="height:{cnt[1][i] / bmax * 170:.0f}px;background:{_NEW};border-radius:5px 5px 0 0"></div>'
                   if cnt[1][i] else '') +
                f'<div style="height:{cnt[0][i] / bmax * 170:.0f}px;background:{_BASE};'
                f'border-radius:{"0 0 5px 5px" if cnt[1][i] else "5px"}"></div></div>' for i in range(len(bins)))
            labs = ''.join(f'<div style="font-size:11px;color:#5B6B7B;text-align:center">{x}</div>' for x in bl)
            q = per['cases'].quantile([0.25, 0.5, 0.75])
            _md(_card(f'ครึ่งหนึ่งเข้าเคสเกิน {q[0.5]:,.0f} ครั้งต่อปี · น้อยสุด {per["cases"].min():,} มากสุด {per["cases"].max():,} ครั้ง',
                      f'จำนวนพยาบาลตามช่วงจำนวนครั้งที่เข้าเคส ปีงบ {fy} ({len(per)} คน) · สีเขียว = น้องใหม่',
                      f'<div style="display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:8px;align-items:end">{cols}</div>'
                      f'<div style="display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:8px">{labs}</div>',
                      f'กลุ่มกลาง 50% อยู่ที่ {q[0.25]:,.0f}-{q[0.75]:,.0f} ครั้ง · กลุ่มต่ำกว่า 100 ครั้งอาจเป็นคนที่ย้ายเข้า-ออกกลางปี ลา '
                      f'หรือหมุนมาจากหน่วยอื่น ตัวเลขนี้ไม่ได้หักวันลา', minh=470))
        with b:
            med = float(per['scrub_pct'].median())
            stack, dots = {}, ''
            for k, r in per.sort_values('scrub_pct').iloc[np.argsort(per.sort_values('scrub_pct').index.isin(nvk), kind='stable')].iterrows():
                bn = int(r['scrub_pct'] // 4)
                lv = stack.get(bn, 0)
                stack[bn] = lv + 1
                dots += (f'<div title="{_nm(k)} : scrub {r["scrub_pct"]:.0f}%" style="position:absolute;'
                         f'left:calc({min(r["scrub_pct"], 98):.1f}% - 6px);bottom:{lv * 15}px;width:12px;height:12px;'
                         f'border-radius:50%;background:{_NEW if k in nvk else _BASE}"></div>')
            hF = max(stack.values()) * 15 + 6
            nvs = per[per.index.isin(nvk)].sort_values('scrub_pct', ascending=False)
            n70 = int((nvs['scrub_pct'] >= 70).sum())
            lst = ' · '.join(f'{_nm(k)} {r["scrub_pct"]:.0f}%' for k, r in nvs.iterrows())
            _md(_card((f'น้องใหม่ {n70} ใน {len(nvs)} คนเป็น scrub เกิน 70% ของเคส · ' if n70 else '')
                      + f'ภาพรวมกลางอยู่ที่ {med:.0f}%',
                      f'สัดส่วนเคสที่เป็น scrub ต่อเคสทั้งหมดของแต่ละคน ปีงบ {fy} · 1 จุด = 1 คน · สีเขียว = น้องใหม่',
                      f'<div style="position:relative;height:{hF}px;margin:6px 6px 0"><div style="position:absolute;'
                      f'left:{med:.1f}%;top:0;bottom:0;border-left:1.5px dashed #5B6B7B"></div>{dots}</div>'
                      '<div style="display:flex;justify-content:space-between;font-size:11px;color:#5B6B7B;'
                      'border-top:1px solid #C9D3DD;padding-top:4px"><span>0% : circulate ล้วน</span><span>50%</span>'
                      '<span>100% : scrub ล้วน</span></div>'
                      + (f'<div style="font-size:12px;color:#3E4C59;line-height:1.6">{lst}</div>' if lst else ''),
                      'เส้นประ = ค่ากลางของทุกคน', minh=470))
    if D['pairs']:
        P = D['pairs']

        def _bar(v, c):
            return (f'<div style="display:flex;align-items:center;gap:8px"><div style="flex:1;background:#F1F4F7;'
                    f'border-radius:5px"><div style="width:{v:.0f}%;height:12px;border-radius:5px;background:{c}"></div>'
                    f'</div><div style="width:40px;text-align:right">{v:.0f}%</div></div>')
        th = ''.join(f'<div style="font-size:12px;font-weight:700;color:#3E4C59;{al}">{t}</div>' for t, al in (
            ('น้องใหม่', ''), ('ครั้งที่จับคู่', 'text-align:right'), ('จำนวนคู่ที่เคยทำงานด้วย', 'text-align:right'),
            ('คู่บ่อยสุดคิดเป็น', ''), ('คู่กับน้องใหม่ด้วยกัน', ''), ('คู่บ่อยสุด 3 อันดับ (เคส)', '')))
        rows = ''.join(
            f'<div>{_nm(r["key"])}</div><div style="text-align:right">{r["n_pairs"]:,}</div>'
            f'<div style="text-align:right">{r["n_partners"]}</div>{_bar(r["top_share"], _BASE)}'
            f'{_bar(r["with_novice"], _WARN if r["with_novice"] >= 50 else _BASE)}'
            f'<div style="font-size:12px;color:#5B6B7B">{", ".join(f"{_nm(a)} ({c})" for a, c in r["top3"])}</div>'
            for r in P)
        pr = [r['n_partners'] for r in P]
        _md(_card(f'น้องใหม่แต่ละคนเคยคู่กับคนอื่น {min(pr)}-{max(pr)} คน · {_nm(P[0]["key"])} คู่กับน้องใหม่ด้วยกัน '
                  f'{P[0]["with_novice"]:.0f}% ของเคส',
                  f'ทีมคู่ scrub กับ circulate ในเคสเดียวกันของน้องใหม่ {len(P)} คน ปีงบ {fy} · เรียงตามสัดส่วนที่คู่กับน้องใหม่ด้วยกัน · '
                  'สีส้ม = ตั้งแต่ครึ่งหนึ่งขึ้นไป',
                  f'<div style="display:grid;grid-template-columns:110px 80px 120px minmax(0,1fr) minmax(0,1fr) 280px;'
                  f'gap:8px 14px;align-items:center;font-size:13px">{th}{rows}</div>',
                  'ครั้งที่จับคู่อาจมากกว่าจำนวนเคส เพราะบางเคสมีหลายคนในบทบาทเดียวกัน · ตัวเลขนับจากชื่อใน HIS'))
    _md('<div class="da-s" style="line-height:1.7">หมายเหตุ : นับทุกเคสที่บันทึกชื่อพยาบาลรวมเคสนอกเวลาและฉุกเฉิน · '
        'เวลาใช้ห้อง = เข้าห้องถึงออกห้อง · เทียบปีต่อปีเฉพาะเดือนที่มีข้อมูลทั้งสองปี</div>')


def _render_body():
    _md(_CSS)
    try:
        C, L = _load()
    except Exception as _ex:
        st.error("โหลดข้อมูลไม่สำเร็จ : ลองกด 🔄 รีเฟรช อีกครั้ง")
        print(f"[data_analysis] load fail: {_ex}")
        return
    if C is None or C.empty or L.empty:
        st.info("ยังไม่มีข้อมูลชื่อพยาบาลในฐานข้อมูล")
        return
    v = st.session_state.get(_K_VIEW, 'hub')
    {'noy': _view_noy, 'nov': _view_nov, 'tr': _view_tr}.get(v, _view_hub)(C, L)
