"""
main_or_utilization.py — Operating Room Utilization Dashboard
─────────────────────────────────────────────────────────────────────
Redesigned for OR Head Nurse / OR Manager (May 2026).
Hierarchy: KPI band → Hero (utilization by specialty) → Drill-down tabs.
Design principles: F-pattern, progressive disclosure, color-as-meaning,
consistent type scale, minimal chart junk.
"""
from __future__ import annotations
from pathlib import Path
from datetime import date, timedelta
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go


# ═════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════
WORK_MIN = 480                                  # 8:00-16:00 = 480 นาที (จ-ศ)
TARGET_UTIL = 75                                # benchmark
ONTIME_HOUR = 8.5                               # 8:30 น. = "เริ่มทันเวลา"
ROOT = Path(__file__).resolve().parent

# ✅ ค่าคงที่ห้องจาก room_config (single source of truth)
#    เดิมไฟล์นี้ copy มาเองแล้วลืม OR9 (ห้อง 98) → ห้องหายจากทุกกราฟ utilization
from room_config import (MOVE_DATE as _MOVE_DATE, NEW_BUILDING_ROOMS,
                         ROOM_INFO, SPECIALTY_FULL)
NEW_BLDG_START = pd.Timestamp(_MOVE_DATE)
ROOM_SPECIALTY = {r: spec for r, (_, spec) in ROOM_INFO.items()}

DATA_CANDIDATES = [
    ROOT / "data" / "year69" / "intraopปี69.xls",
    ROOT.parent / "thesis_main_OR" / "data_for_train" / "year69" / "intraopปี69.xls",
    ROOT / "data" / "historical" / "main_or_history.csv",
]

THAI_MONTH_SHORT = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.", 5: "พ.ค.", 6: "มิ.ย.",
    7: "ก.ค.", 8: "ส.ค.", 9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค.",
}

DOW_TH = {0: "จันทร์", 1: "อังคาร", 2: "พุธ", 3: "พฤหัส", 4: "ศุกร์"}

# ═════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM — single source of truth for colors & layout
# ═════════════════════════════════════════════════════════════════════
COLOR_GOOD    = "#16a34a"   # green — meeting/exceeding target
COLOR_OK      = "#f59e0b"   # amber — approaching target
COLOR_WARN    = "#dc2626"   # red — well below target
COLOR_PRIMARY = "#0284c7"   # sky — neutral data
COLOR_ACCENT  = "#dc2626"   # red — highlight winner/loser
COLOR_MUTED   = "#94a3b8"   # gray — secondary
COLOR_INK     = "#0f172a"   # text strong
COLOR_INK2    = "#475569"   # text muted
COLOR_BG_SOFT = "#f8fafc"

CHART_FONT = dict(family="Sarabun, sans-serif", size=13, color=COLOR_INK2)


def style_layout(**override):
    """Consistent Plotly layout defaults — minimal chart junk."""
    base = dict(
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        font=CHART_FONT,
        margin=dict(l=10, r=20, t=20, b=10),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)",
                   zeroline=False, linecolor="rgba(0,0,0,0.1)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)",
                   zeroline=False, linecolor="rgba(0,0,0,0.1)"),
        showlegend=False,
        hoverlabel=dict(bgcolor="white", bordercolor="rgba(0,0,0,0.1)",
                        font=dict(size=13, color=COLOR_INK)),
    )
    base.update(override)
    return base


# ═════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════
def hhmmss_to_sec(v):
    if pd.isna(v): return np.nan
    v = int(v)
    return (v // 10000) * 3600 + ((v // 100) % 100) * 60 + (v % 100)


def to_thai_month(s):
    try:
        y, m = s.split("-")
        be = int(y) + 543
        return THAI_MONTH_SHORT[int(m)] + " " + str(be % 100).zfill(2)
    except Exception:
        return str(s)


def to_thai_date(d):
    if d is None: return ""
    be = d.year + 543
    return str(d.day) + " " + THAI_MONTH_SHORT[d.month] + " " + str(be % 100).zfill(2)


def sec_to_hhmm(sec):
    if pd.isna(sec): return "—"
    sec = int(sec)
    return "{:02d}:{:02d}".format(sec // 3600, (sec % 3600) // 60)


def format_room_label(r):
    if pd.isna(r): return "?"
    r = int(r)
    info = ROOM_INFO.get(r)
    if info is None: return ""
    or_n, spec = info
    if spec == "EM":
        return or_n + " " + spec + " 🚨"
    return or_n + " " + spec


def util_color(pct):
    if pct >= TARGET_UTIL:        return COLOR_GOOD
    if pct >= TARGET_UTIL - 15:   return COLOR_OK
    return COLOR_WARN


def turnover_color(m):
    if m <= 20: return COLOR_GOOD
    if m <= 30: return COLOR_OK
    return COLOR_WARN


def duration_color(m):
    if m < 60:  return COLOR_GOOD
    if m < 120: return COLOR_OK
    return COLOR_WARN


def start_color(sec):
    if sec <= 8.5 * 3600: return COLOR_GOOD
    if sec <= 9.5 * 3600: return COLOR_OK
    return COLOR_WARN


def _load_from_db() -> pd.DataFrame:
    """ดึงข้อมูล utilization จากตาราง cases (Supabase/SQLite)
    — ใช้บน Streamlit Cloud ที่ไม่มีไฟล์ intraop (ไฟล์ local เป็น PDPA gitignore)
    คืนคอลัมน์ชุดเดียวกับ loader ไฟล์: date, enter_sec, exit_sec, in_room_min,
    orroom_n, month, dow"""
    try:
        from main_or_db import get_conn
        conn = get_conn()
        df = pd.read_sql_query(
            "SELECT op_date, room_no, in_or_at, op_end_at, actual_duration_min "
            "FROM cases WHERE status IN ('post_op','discharged','done') "
            "AND in_or_at IS NOT NULL AND op_end_at IS NOT NULL "
            "AND op_date >= ?", conn, params=[_MOVE_DATE])
        conn.close()
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    _in = pd.to_datetime(df["in_or_at"], errors="coerce")
    _out = pd.to_datetime(df["op_end_at"], errors="coerce")
    df["date"] = pd.to_datetime(df["op_date"], errors="coerce").dt.normalize()
    df["enter_sec"] = _in.dt.hour * 3600 + _in.dt.minute * 60 + _in.dt.second
    df["exit_sec"] = _out.dt.hour * 3600 + _out.dt.minute * 60 + _out.dt.second
    _dur_fallback = (df["exit_sec"] - df["enter_sec"]) / 60
    df["in_room_min"] = pd.to_numeric(df["actual_duration_min"],
                                      errors="coerce").fillna(_dur_fallback)
    df["orroom_n"] = pd.to_numeric(df["room_no"], errors="coerce").astype("Int64")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["dow"] = df["date"].dt.dayofweek
    df = df[(df["in_room_min"] > 0) & (df["in_room_min"] < 600)
            & df["orroom_n"].notna() & df["date"].notna() & (df["dow"] < 5)]
    return df[df["orroom_n"].isin(NEW_BUILDING_ROOMS)].copy()


@st.cache_data(ttl=3600)
def load_utilization_data():
    src = None
    for p in DATA_CANDIDATES:
        if p.exists():
            src = p
            break
    if src is None:
        # ไม่มีไฟล์ local (เช่นบน cloud) → ดึงจากฐานข้อมูลแทน
        return _load_from_db()

    if src.suffix == ".xls":
        df = pd.read_excel(src)
        df["date"]        = pd.to_datetime(df["roomdatein"], errors="coerce").dt.normalize()
        df["enter_sec"]   = df["roomtimein"].apply(hhmmss_to_sec)
        df["exit_sec"]    = df["roomtimeout"].apply(hhmmss_to_sec)
        df["in_room_min"] = (df["exit_sec"] - df["enter_sec"]) / 60
        df["orroom_n"]    = pd.to_numeric(df["orroom"], errors="coerce").astype("Int64")
    else:
        df = pd.read_csv(src)
        df["date"] = pd.to_datetime(df.get("opedate", df.get("date")), errors="coerce").dt.normalize()
        df["in_room_min"] = pd.to_numeric(df.get("actual_duration_min", df.get("opusetime", 60)), errors="coerce")
        df["orroom_n"] = pd.to_numeric(df.get("orroom"), errors="coerce").astype("Int64")

    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["dow"]   = df["date"].dt.dayofweek
    df = df[
        (df["in_room_min"] > 0) & (df["in_room_min"] < 600) &
        (df["orroom_n"].notna()) & (df["date"].notna()) & (df["dow"] < 5)
    ].copy()
    df = df[df["orroom_n"].isin(NEW_BUILDING_ROOMS)].copy()
    # 🆕 เฉพาะยุคตึกใหม่ (ตั้งแต่ 1 มี.ค. 69) — กันข้อมูลตึกเก่า/ก่อนย้ายหลุดเข้ามา
    df = df[df["date"] >= NEW_BLDG_START].copy()
    return df


def compute_daily(v):
    """Util daily — cap effective time to 8:00-16:00 (จ-ศ)."""
    if v.empty: return v
    WS, WE = 8 * 3600, 16 * 3600
    v = v.copy()
    v["eff_start"]   = v["enter_sec"].clip(lower=WS)
    v["eff_end"]     = v["exit_sec"].clip(upper=WE)
    v["inhours_min"] = ((v["eff_end"] - v["eff_start"]) / 60).clip(lower=0)
    daily = v.groupby(["orroom_n", "date"]).agg(
        total_in_room=("inhours_min", "sum"),
        n_cases=("in_room_min", "count"),
    ).reset_index()
    daily["util_pct"] = (daily["total_in_room"] / WORK_MIN * 100).clip(upper=100)  # 📐 M-08: util ≤ 100% (ตรงทั้งระบบ)
    daily["month"] = daily["date"].dt.to_period("M").astype(str)
    return daily


def compute_turnover(case_df):
    """Turnover (นาที) = exit prev → enter next (same room, same day, 5-180 นาที)."""
    if case_df.empty:
        return pd.DataFrame(columns=["orroom_n", "date", "turnover_min"])
    df = case_df.sort_values(["orroom_n", "date", "enter_sec"]).copy()
    df["prev_exit_sec"] = df.groupby(["orroom_n", "date"])["exit_sec"].shift(1)
    df["turnover_min"] = (df["enter_sec"] - df["prev_exit_sec"]) / 60
    return df[(df["turnover_min"] >= 5) & (df["turnover_min"] <= 180)][
        ["orroom_n", "date", "turnover_min"]
    ].copy()


# ═════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ═════════════════════════════════════════════════════════════════════
def kpi_card(label, value, sublabel=None, color=COLOR_PRIMARY, icon=""):
    sub = ('<div style="font-size:12px;color:#94a3b8;margin-top:6px;">' + sublabel + '</div>'
           if sublabel else '')
    return (
        '<div style="background:white;border:1px solid #e5e7eb;border-left:4px solid ' + color + ';'
        'border-radius:10px;padding:14px 18px;height:100%;">'
        '<div style="font-size:11px;color:#64748b;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;">'
        + icon + '&nbsp;&nbsp;' + label + '</div>'
        '<div style="font-size:30px;font-weight:700;color:' + COLOR_INK + ';line-height:1.15;margin-top:8px;">'
        + value + '</div>' + sub + '</div>'
    )


def section_header(title, subtitle=None):
    sub = ('<p style="margin:3px 0 0;color:#64748b;font-size:12.5px;">' + subtitle + '</p>'
           if subtitle else '')
    st.markdown(
        '<div style="margin:22px 0 12px;border-bottom:1px solid #e5e7eb;padding-bottom:8px;">'
        '<h3 style="margin:0;font-size:17px;color:' + COLOR_INK + ';font-weight:700;letter-spacing:0.2px;">'
        + title + '</h3>' + sub + '</div>',
        unsafe_allow_html=True
    )


def insight_box(html, color=COLOR_PRIMARY, bg="#f0f9ff"):
    st.markdown(
        '<div style="background:' + bg + ';border-left:4px solid ' + color + ';'
        'border-radius:8px;padding:14px 18px;margin:8px 0 16px;font-size:14.5px;'
        'line-height:1.6;color:' + COLOR_INK + ';">' + html + '</div>',
        unsafe_allow_html=True
    )


# ═════════════════════════════════════════════════════════════════════
# MAIN PAGE
# ═════════════════════════════════════════════════════════════════════
def page_utilization():
    # ─── HEADER ──────────────────────────────────────
    st.markdown(
        '<div style="background:linear-gradient(135deg,#0c4a6e 0%,#0369a1 100%);'
        'border-radius:12px;padding:20px 26px;margin-bottom:18px;color:#ffffff;">'
        '<div style="font-size:22px;font-weight:700;letter-spacing:0.3px;color:#ffffff;line-height:1.3;">'
        '📊 ภาพรวมการใช้ห้องผ่าตัด</div>'
        '<div style="margin-top:6px;color:#ffffff;font-size:13px;opacity:0.92;">'
        'อาคารใหม่ ตั้งแต่ 1 มี.ค. 69 — เวลาทำการ จ-ศ 8:00-16:00 น. (9 ห้อง)</div>'
        '</div>',
        unsafe_allow_html=True
    )
    # 📐 M-08: footnote นิยาม utilization เดียวทั้งระบบ
    st.caption("ℹ️ นิยาม Utilization: เวลาที่ห้องถูกใช้ในช่วง 8:00–16:00 (clip รายห้อง-วัน) "
               "÷ (ห้อง × 480 นาที) · util ≤ 100% · turnover 1–90 นาที — "
               "นิยาม (clip 8–16 รายห้อง-วัน) ตรงกันทุกหน้า · หน้านี้แสดง **ค่ามัธยฐาน** ของ util "
               "รายห้อง-วัน (Dashboard = ของวันนี้ · สถิติย้อนหลัง = ค่าเฉลี่ย)")

    df = load_utilization_data()
    if df.empty:
        st.warning("❌ ไม่พบข้อมูล — เครื่อง local: วาง intraopปี69.xls ที่ data/year69/ · "
                   "บน cloud: ต้องมีเคสที่ผ่าเสร็จ (มีเวลาเข้า-ออกห้อง) ในฐานข้อมูลก่อน")
        return

    # ─── DATE PICKER ──────────────────────────────────
    min_d = df["date"].min().date()
    max_d = df["date"].max().date()
    default_start = max(min_d, NEW_BLDG_START.date())

    c1, c2, c3 = st.columns([2, 2, 4])
    with c1:
        sel_from = st.date_input("📅 จาก", value=default_start,
                                  min_value=min_d, max_value=max_d,
                                  format="YYYY/MM/DD", key="util_from")
    with c2:
        sel_to = st.date_input("📅 ถึง", value=max_d,
                                min_value=min_d, max_value=max_d,
                                format="YYYY/MM/DD", key="util_to")

    if sel_from > sel_to:
        st.error("⚠️ วันที่เริ่มต้นต้องไม่หลังกว่าวันสิ้นสุด")
        return

    mask = (df["date"].dt.date >= sel_from) & (df["date"].dt.date <= sel_to)
    df_f = df[mask].copy()
    if df_f.empty:
        st.info("ไม่มีข้อมูลในช่วงวันที่เลือก")
        return

    daily = compute_daily(df_f)
    daily["specialty"] = daily["orroom_n"].apply(lambda r: ROOM_SPECIALTY.get(int(r), "?"))
    n_days = (sel_to - sel_from).days + 1
    n_cases_total = int(daily["n_cases"].sum())

    with c3:
        st.markdown(
            '<div style="font-size:12.5px;color:#64748b;margin-top:30px;text-align:right;">'
            '<b style="color:' + COLOR_INK + ';">' + to_thai_date(sel_from) +
            ' – ' + to_thai_date(sel_to) + '</b><br>'
            'รวม ' + str(n_days) + ' วัน  •  ' + "{:,}".format(n_cases_total) + ' เคส'
            '</div>',
            unsafe_allow_html=True
        )

    # ═════════════════════════════════════════════════
    # TIER 1: KPI BAND
    # ═════════════════════════════════════════════════
    overall_util = float(daily["util_pct"].median())
    turnover = compute_turnover(df_f)
    median_to = float(turnover["turnover_min"].median()) if not turnover.empty else None

    first_case = df_f.groupby(["orroom_n", "date"])["enter_sec"].min()
    on_time_pct = (first_case <= ONTIME_HOUR * 3600).mean() * 100 if len(first_case) > 0 else None

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(kpi_card(
            "ใช้ห้องเฉลี่ย", "{:.0f}%".format(overall_util),
            sublabel="เป้าหมาย {}%".format(TARGET_UTIL),
            color=util_color(overall_util), icon="📊"
        ), unsafe_allow_html=True)
    with k2:
        st.markdown(kpi_card(
            "เคสรวม", "{:,}".format(n_cases_total),
            sublabel="เฉลี่ย {:.1f} เคส/วัน".format(n_cases_total / max(n_days, 1)),
            color=COLOR_PRIMARY, icon="🏥"
        ), unsafe_allow_html=True)
    with k3:
        if median_to is not None:
            st.markdown(kpi_card(
                "Turnover เฉลี่ย", "{:.0f} นาที".format(median_to),
                sublabel="เป้าหมาย ≤ 20 นาที",
                color=turnover_color(median_to), icon="⏱️"
            ), unsafe_allow_html=True)
        else:
            st.markdown(kpi_card("Turnover เฉลี่ย", "—", sublabel="ไม่มีข้อมูล",
                                  color=COLOR_MUTED, icon="⏱️"), unsafe_allow_html=True)
    with k4:
        if on_time_pct is not None:
            ocol = COLOR_GOOD if on_time_pct >= 70 else (COLOR_OK if on_time_pct >= 50 else COLOR_WARN)
            st.markdown(kpi_card(
                "เริ่มทันเวลา", "{:.0f}%".format(on_time_pct),
                sublabel="เคสแรก ≤ 8:30 น.",
                color=ocol, icon="⏰"
            ), unsafe_allow_html=True)
        else:
            st.markdown(kpi_card("เริ่มทันเวลา", "—", color=COLOR_MUTED, icon="⏰"),
                         unsafe_allow_html=True)

    st.caption(
        "📊 **ใช้ห้องเฉลี่ย** นับเฉพาะห้อง-วันที่เปิดใช้จริง (มีเคสอย่างน้อย 1) "
        "เทียบเวลาทำการ 8:00–16:00 น. — ไม่รวมวันที่ห้องปิด/ไม่มีเคส"
    )

    # ═════════════════════════════════════════════════
    # TIER 2: HERO — Utilization by Specialty
    # ═════════════════════════════════════════════════
    section_header(
        "🏆 สาขาไหนใช้ห้องคุ้มที่สุด",
        "เส้นประเขียว = เป้าหมาย 75%  •  แดง/เหลือง = ต่ำกว่าเป้า"
    )

    summary = daily.groupby("specialty").agg(
        median_util=("util_pct", "median"),
        n_cases=("n_cases", "sum"),
        active_days=("date", "count"),
    ).reset_index()
    summary["full_name"] = summary["specialty"].map(SPECIALTY_FULL).fillna(summary["specialty"])
    summary["color"] = summary["median_util"].apply(util_color)
    summary_sorted_desc = summary.sort_values("median_util", ascending=False)
    summary_for_chart = summary.sort_values("median_util", ascending=True)  # bottom-up for horiz bar

    top = summary_sorted_desc.iloc[0]
    bot = summary_sorted_desc.iloc[-1]
    n_above = int((summary["median_util"] >= TARGET_UTIL).sum())
    n_total = len(summary)

    insight_box(
        '<b style="color:' + COLOR_INK + ';">' + str(n_above) + '/' + str(n_total) + ' สาขา</b> '
        'ใช้ห้องถึงเป้า {}% — '.format(TARGET_UTIL) +
        '🏆 ดีสุด: <b>' + top["full_name"] + '</b> '
        '<span style="color:' + COLOR_GOOD + ';">{:.0f}%</span>'.format(top["median_util"]) +
        ' &nbsp;|&nbsp; ⚠️ ต่ำสุด: <b>' + bot["full_name"] + '</b> '
        '<span style="color:' + COLOR_WARN + ';">{:.0f}%</span>'.format(bot["median_util"]),
        color=COLOR_PRIMARY, bg="#f0f9ff"
    )

    fig_hero = go.Figure(go.Bar(
        y=summary_for_chart["full_name"],
        x=summary_for_chart["median_util"],
        orientation="h",
        marker=dict(color=summary_for_chart["color"], line=dict(width=0)),
        text=["{:.0f}%".format(v) for v in summary_for_chart["median_util"]],
        textposition="outside",
        textfont=dict(size=13, color=COLOR_INK),
        customdata=summary_for_chart["n_cases"].astype(int),
        hovertemplate="<b>%{y}</b><br>Utilization: %{x:.0f}%<br>เคส: %{customdata:,}<extra></extra>",
    ))
    fig_hero.add_vline(x=TARGET_UTIL, line_dash="dash", line_color=COLOR_GOOD, line_width=2)
    fig_hero.add_annotation(x=TARGET_UTIL, y=1.02, yref="paper",
                              text="🎯 เป้า {}%".format(TARGET_UTIL),
                              showarrow=False, xanchor="left", yanchor="bottom",
                              font=dict(color=COLOR_GOOD, size=11))
    fig_hero.update_layout(**style_layout(
        height=max(280, 44 * len(summary) + 60),
        xaxis=dict(range=[0, 105], title=None, ticksuffix="%",
                   showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        yaxis=dict(autorange="reversed", title=None),
        margin=dict(l=10, r=60, t=30, b=10),
    ))
    st.plotly_chart(fig_hero, use_container_width=True, key="hero_util")

    # ═════════════════════════════════════════════════
    # TIER 3: DRILL-DOWN TABS
    # ═════════════════════════════════════════════════
    section_header("🔎 ดูรายละเอียดเพิ่มเติม")
    tab1, tab2, tab3, tab4 = st.tabs([
        "🚪 รายห้อง", "📅 วันไหนยุ่งสุด", "⏱️ เวลา & Turnover", "📈 เทรนด์รายเดือน"
    ])

    # ─── TAB 1: รายห้อง ──────────────────────────────
    with tab1:
        by_room = daily.groupby("orroom_n").agg(
            median_util=("util_pct", "median"),
            n_cases=("n_cases", "sum"),
        ).reset_index().sort_values("median_util", ascending=True)
        by_room["room_label"] = by_room["orroom_n"].apply(format_room_label)
        by_room["color"] = by_room["median_util"].apply(util_color)

        st.markdown('<div style="font-size:13.5px;color:' + COLOR_INK2 +
                     ';margin:6px 0 8px;"><b>ห้องไหนใช้คุ้ม / ว่างเยอะ</b></div>',
                     unsafe_allow_html=True)
        fig_r = go.Figure(go.Bar(
            y=by_room["room_label"], x=by_room["median_util"], orientation="h",
            marker_color=by_room["color"],
            text=["{:.0f}%".format(v) for v in by_room["median_util"]],
            textposition="outside",
            textfont=dict(size=13),
            customdata=by_room["n_cases"].astype(int),
            hovertemplate="<b>%{y}</b><br>%{x:.0f}%<br>เคส: %{customdata:,}<extra></extra>",
        ))
        fig_r.add_vline(x=TARGET_UTIL, line_dash="dash", line_color=COLOR_GOOD, line_width=2)
        fig_r.update_layout(**style_layout(
            height=max(280, 44 * len(by_room) + 60),
            xaxis=dict(range=[0, 110], title=None, ticksuffix="%"),
            yaxis=dict(autorange="reversed", title=None),
            margin=dict(l=10, r=60, t=10, b=10),
        ))
        st.plotly_chart(fig_r, use_container_width=True, key="tab1_rooms")

        # Start time secondary
        st.markdown('<div style="margin-top:22px;font-size:13.5px;color:' + COLOR_INK2 +
                     ';margin-bottom:6px;"><b>⏰ เคสแรกของวันเริ่มกี่โมง</b> '
                     '<span style="color:#94a3b8;font-weight:400;">(เขียว ≤ 8:30 / เหลือง ≤ 9:30 / แดง > 9:30)</span></div>',
                     unsafe_allow_html=True)
        fc = df_f.groupby(["orroom_n", "date"])["enter_sec"].min().reset_index()
        st_room = fc.groupby("orroom_n")["enter_sec"].median().reset_index()
        st_room["room_label"] = st_room["orroom_n"].apply(format_room_label)
        st_room["start_hhmm"] = st_room["enter_sec"].apply(sec_to_hhmm)
        st_room["start_hour"] = st_room["enter_sec"] / 3600
        st_room["color"]      = st_room["enter_sec"].apply(start_color)
        st_room = st_room.sort_values("enter_sec")

        fig_st = go.Figure(go.Bar(
            y=st_room["room_label"], x=st_room["start_hour"], orientation="h",
            marker_color=st_room["color"],
            text=st_room["start_hhmm"] + " น.",
            textposition="outside",
            textfont=dict(size=13),
        ))
        fig_st.add_vline(x=8, line_dash="dash", line_color=COLOR_GOOD, line_width=2)
        fig_st.update_layout(**style_layout(
            height=max(240, 38 * len(st_room) + 60),
            xaxis=dict(range=[7, 12], title=None,
                       tickmode="array", tickvals=[7, 8, 9, 10, 11, 12],
                       ticktext=["7:00", "8:00", "9:00", "10:00", "11:00", "12:00"]),
            yaxis=dict(autorange="reversed", title=None),
            margin=dict(l=10, r=80, t=10, b=10),
        ))
        st.plotly_chart(fig_st, use_container_width=True, key="tab1_start")

    # ─── TAB 2: วันไหนยุ่งสุด ────────────────────────
    with tab2:
        dates_in_period = pd.date_range(sel_from, sel_to)
        work_dates = dates_in_period[dates_in_period.dayofweek < 5]
        n_days_per_dow = pd.Series(work_dates.dayofweek).value_counts().to_dict()

        df_dow = df_f.copy()
        df_dow["dow_name"] = df_dow["dow"].map(DOW_TH)

        view = st.radio("ดูแบบไหน?", ["🏥 รวมทุกห้อง", "🚪 แยกรายห้อง"],
                          horizontal=True, key="tab2_view")

        if view == "🏥 รวมทุกห้อง":
            cpd = df_dow.groupby(["dow", "dow_name"]).size().reset_index(name="total")
            full = pd.DataFrame({"dow": list(range(5)),
                                 "dow_name": [DOW_TH[i] for i in range(5)]})
            cpd = full.merge(cpd[["dow", "total"]], on="dow", how="left").fillna(0)
            cpd["n_days"] = cpd["dow"].map(n_days_per_dow).fillna(1).clip(lower=1)
            cpd["avg"] = cpd["total"] / cpd["n_days"]
            cpd = cpd.sort_values("dow").reset_index(drop=True)

            mi = int(cpd["avg"].idxmax()) if cpd["avg"].sum() > 0 else -1
            colors = [COLOR_ACCENT if i == mi else COLOR_PRIMARY for i in cpd.index]

            fig = go.Figure(go.Bar(
                x=cpd["dow_name"], y=cpd["avg"], marker_color=colors,
                text=["{:.1f}".format(v) for v in cpd["avg"]],
                textposition="outside", textfont=dict(size=14),
                hovertemplate="<b>%{x}</b><br>เคสเฉลี่ย: %{y:.1f}/วัน<extra></extra>",
            ))
            fig.update_layout(**style_layout(
                height=340,
                yaxis=dict(title="เคสเฉลี่ย/วัน"),
                xaxis=dict(title=None),
            ))
            st.plotly_chart(fig, use_container_width=True, key="tab2_all")

            if mi >= 0:
                bd, qd = cpd.loc[mi], cpd.loc[int(cpd["avg"].idxmin())]
                insight_box(
                    '🔥 <b>วัน' + bd["dow_name"] + '</b> ยุ่งสุด: '
                    '<span style="color:' + COLOR_ACCENT + ';">'
                    '<b>{:.1f} เคส/วัน</b></span> &nbsp;•&nbsp; '.format(bd["avg"]) +
                    '😴 <b>วัน' + qd["dow_name"] + '</b> ว่างสุด: '
                    '<span style="color:' + COLOR_GOOD + ';">'
                    '<b>{:.1f} เคส/วัน</b></span>'.format(qd["avg"]),
                    color=COLOR_ACCENT, bg="#fff7ed"
                )
        else:
            avail = sorted([int(r) for r in df_dow["orroom_n"].dropna().unique()])
            opts = {format_room_label(r): r for r in avail}
            sel_lab = st.selectbox("🚪 เลือกห้อง", list(opts.keys()), key="tab2_room")
            sel_room = opts[sel_lab]
            rdf = df_dow[df_dow["orroom_n"] == sel_room]

            cpd = rdf.groupby(["dow", "dow_name"]).size().reset_index(name="total")
            full = pd.DataFrame({"dow": list(range(5)),
                                 "dow_name": [DOW_TH[i] for i in range(5)]})
            cpd = full.merge(cpd[["dow", "total"]], on="dow", how="left").fillna(0)
            cpd["n_days"] = cpd["dow"].map(n_days_per_dow).fillna(1).clip(lower=1)
            cpd["avg"] = cpd["total"] / cpd["n_days"]
            cpd = cpd.sort_values("dow").reset_index(drop=True)

            mi = int(cpd["avg"].idxmax()) if cpd["avg"].sum() > 0 else -1
            colors = [COLOR_ACCENT if i == mi else COLOR_PRIMARY for i in cpd.index]

            fig = go.Figure(go.Bar(
                x=cpd["dow_name"], y=cpd["avg"], marker_color=colors,
                text=["{:.1f}".format(v) for v in cpd["avg"]],
                textposition="outside", textfont=dict(size=14),
                hovertemplate="<b>%{x}</b><br>" + sel_lab +
                              "<br>เคสเฉลี่ย: %{y:.1f}/วัน<extra></extra>",
            ))
            fig.update_layout(**style_layout(
                height=340,
                yaxis=dict(title="เคสเฉลี่ย/วัน"),
                xaxis=dict(title=None),
            ))
            st.plotly_chart(fig, use_container_width=True, key="tab2_per_room")

            if mi >= 0:
                bd = cpd.loc[mi]
                insight_box(
                    '📌 <b>' + sel_lab + '</b> ยุ่งสุดวัน<b>' + bd["dow_name"] + '</b> — '
                    '<b style="color:' + COLOR_ACCENT + ';">{:.1f} เคส/วัน</b> &nbsp;•&nbsp; '.format(bd["avg"]) +
                    'รวมทั้งช่วง: <b>{:,} เคส</b>'.format(int(rdf.shape[0])),
                    color=COLOR_PRIMARY, bg="#eff6ff"
                )

    # ─── TAB 3: เวลา & Turnover ─────────────────────
    with tab3:
        df_f["specialty"] = df_f["orroom_n"].apply(lambda r: ROOM_SPECIALTY.get(int(r), "?"))

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown('<div style="font-size:13.5px;color:' + COLOR_INK2 +
                         ';margin-bottom:8px;"><b>📊 เวลาในห้องต่อเคส (รายสาขา)</b> '
                         '<span style="color:#94a3b8;font-weight:400;">มัธยฐาน</span></div>',
                         unsafe_allow_html=True)
            ds = df_f.groupby("specialty").agg(
                med_min=("in_room_min", "median"),
                n=("in_room_min", "count"),
            ).reset_index().sort_values("med_min", ascending=True)
            ds["full"]  = ds["specialty"].map(SPECIALTY_FULL).fillna(ds["specialty"])
            ds["color"] = ds["med_min"].apply(duration_color)

            fig_d = go.Figure(go.Bar(
                y=ds["full"], x=ds["med_min"], orientation="h",
                marker_color=ds["color"],
                text=["{:.0f} นาที".format(v) for v in ds["med_min"]],
                textposition="outside", textfont=dict(size=12),
                customdata=ds["n"].astype(int),
                hovertemplate="<b>%{y}</b><br>%{x:.0f} นาที (n=%{customdata:,})<extra></extra>",
            ))
            fig_d.update_layout(**style_layout(
                height=max(280, 44 * len(ds) + 60),
                xaxis=dict(title="นาที"),
                yaxis=dict(autorange="reversed", title=None),
                margin=dict(l=10, r=80, t=10, b=10),
            ))
            st.plotly_chart(fig_d, use_container_width=True, key="tab3_dur")

        with col_b:
            st.markdown('<div style="font-size:13.5px;color:' + COLOR_INK2 +
                         ';margin-bottom:8px;"><b>⏱️ Turnover เฉลี่ย (รายสาขา)</b> '
                         '<span style="color:#94a3b8;font-weight:400;">เป้า ≤ 20 นาที</span></div>',
                         unsafe_allow_html=True)
            if turnover.empty:
                st.info("ไม่มีข้อมูล turnover ในช่วงนี้")
            else:
                turnover["specialty"] = turnover["orroom_n"].apply(
                    lambda r: ROOM_SPECIALTY.get(int(r), "?"))
                ts = turnover.groupby("specialty").agg(
                    med=("turnover_min", "median"),
                    n=("turnover_min", "count"),
                ).reset_index().sort_values("med", ascending=True)
                ts["full"]  = ts["specialty"].map(SPECIALTY_FULL).fillna(ts["specialty"])
                ts["color"] = ts["med"].apply(turnover_color)

                fig_t = go.Figure(go.Bar(
                    y=ts["full"], x=ts["med"], orientation="h",
                    marker_color=ts["color"],
                    text=["{:.0f} นาที".format(v) for v in ts["med"]],
                    textposition="outside", textfont=dict(size=12),
                    customdata=ts["n"].astype(int),
                    hovertemplate="<b>%{y}</b><br>%{x:.0f} นาที (n=%{customdata})<extra></extra>",
                ))
                fig_t.add_vline(x=20, line_dash="dash", line_color=COLOR_GOOD, line_width=2)
                fig_t.update_layout(**style_layout(
                    height=max(280, 44 * len(ts) + 60),
                    xaxis=dict(title="นาที"),
                    yaxis=dict(autorange="reversed", title=None),
                    margin=dict(l=10, r=80, t=10, b=10),
                ))
                st.plotly_chart(fig_t, use_container_width=True, key="tab3_to")

    # ─── TAB 4: เทรนด์รายเดือน ──────────────────────
    with tab4:
        monthly = daily.groupby("month").agg(
            med_util=("util_pct", "median"),
            n_cases=("n_cases", "sum"),
        ).reset_index().sort_values("month")
        monthly["m_th"] = monthly["month"].apply(to_thai_month)

        if len(monthly) <= 1:
            st.info("ต้องมีข้อมูลอย่างน้อย 2 เดือน เพื่อแสดงเทรนด์")
        else:
            st.markdown('<div style="font-size:13.5px;color:' + COLOR_INK2 +
                         ';margin-bottom:6px;"><b>เทรนด์การใช้ห้อง (รวม)</b></div>',
                         unsafe_allow_html=True)
            fig_m = go.Figure(go.Scatter(
                x=monthly["m_th"], y=monthly["med_util"],
                mode="lines+markers+text",
                text=["{:.0f}%".format(v) for v in monthly["med_util"]],
                textposition="top center",
                line=dict(width=3, color=COLOR_PRIMARY),
                marker=dict(size=12, color=COLOR_PRIMARY,
                             line=dict(width=2, color="white")),
                hovertemplate="<b>%{x}</b><br>Median util: %{y:.0f}%<extra></extra>",
            ))
            fig_m.add_hline(y=TARGET_UTIL, line_dash="dash", line_color=COLOR_GOOD, line_width=2)
            fig_m.add_annotation(x=1, xref="paper", y=TARGET_UTIL, yref="y",
                                   text="🎯 เป้า " + str(TARGET_UTIL) + "%",
                                   showarrow=False, xanchor="right", yanchor="bottom",
                                   font=dict(color=COLOR_GOOD, size=11))
            fig_m.update_layout(**style_layout(
                height=360,
                yaxis=dict(range=[0, 100], title="Median Utilization %", ticksuffix="%"),
                xaxis=dict(title=None),
            ))
            st.plotly_chart(fig_m, use_container_width=True, key="tab4_overall")

            # per-room trend
            st.markdown('<div style="margin-top:22px;font-size:13.5px;color:' + COLOR_INK2 +
                         ';margin-bottom:6px;"><b>เทรนด์รายห้อง</b> '
                         '<span style="color:#94a3b8;font-weight:400;">'
                         'เส้นสูง = ใช้คุ้ม / เส้นต่ำ = ห้องว่าง</span></div>',
                         unsafe_allow_html=True)
            br = daily.groupby(["orroom_n", "month"])["util_pct"].median().reset_index()
            br["room"] = br["orroom_n"].apply(format_room_label)
            br["m_th"] = br["month"].apply(to_thai_month)
            order = (br.groupby("orroom_n")["util_pct"].mean()
                     .sort_values(ascending=False).index.tolist())
            order_lab = [format_room_label(r) for r in order]
            month_order = [to_thai_month(m) for m in sorted(br["month"].unique())]

            fig_rl = px.line(
                br, x="m_th", y="util_pct", color="room", markers=True,
                category_orders={"room": order_lab, "m_th": month_order},
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"util_pct": "Util %", "m_th": "", "room": "ห้อง"},
            )
            fig_rl.update_traces(line=dict(width=2), marker=dict(size=8),
                                   hovertemplate="<b>%{fullData.name}</b><br>%{x}: %{y:.0f}%<extra></extra>")
            fig_rl.add_hline(y=TARGET_UTIL, line_dash="dash",
                                line_color=COLOR_GOOD, line_width=1.5)
            fig_rl.update_layout(**style_layout(
                height=440,
                yaxis=dict(range=[0, 100], title="Utilization %", ticksuffix="%"),
                xaxis=dict(title=None),
                showlegend=True,
                legend=dict(orientation="v", y=1, x=1.02, font=dict(size=11),
                              title_text="ห้อง (เรียงคุ้ม→ว่าง)"),
                hovermode="x unified",
            ))
            st.plotly_chart(fig_rl, use_container_width=True, key="tab4_rooms")

    # ─── FOOTER: Download ───────────────────────────
    st.markdown('<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 14px;">',
                  unsafe_allow_html=True)
    csv = summary_sorted_desc[["specialty", "full_name", "median_util", "n_cases", "active_days"]] \
        .to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 Download summary CSV", data=csv,
                        file_name="utilization_summary.csv", mime="text/csv")
