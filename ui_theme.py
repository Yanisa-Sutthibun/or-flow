"""
ui_theme.py — Central design system (flat, clinical blue)

Inject ครั้งเดียวต่อ page → consistent styling ทั้งแอพ
(ตารางผ่าตัด · บริหารจัดการ · ตั้งค่า)

Design: flat clinical SaaS
- Palette: slate ink + clinical blue + clean semantic colors
- Typography: Inter (Latin) + IBM Plex Sans Thai
- Components: flat refined buttons, metrics, cards, tabs, sidebar (เงาบางมาก ไม่มี gradient)

NOTE: CSS ต้องเป็น string block ต่อเนื่อง — ห้ามมี blank line ภายใน string literal
เหตุผล: Streamlit markdown parser ตัด <style> block ถ้าเจอ blank line → CSS รั่วเป็น text
(คอมเมนต์ Python คั่นระหว่าง literal ได้ ปลอดภัย)
"""

import streamlit as st

THEME_CSS = (
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@400;500;600;700&'
    'family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap" rel="stylesheet">'
    '<style>'
    ':root{'
    '--ink-900:#0f172a;--ink-800:#1e293b;--ink-700:#334155;--ink-600:#475569;'
    '--ink-500:#64748b;--ink-400:#94a3b8;--ink-300:#cbd5e1;--ink-200:#e2e8f0;'
    '--ink-100:#eef2f6;--ink-50:#f6f8fa;'
    '--canvas:#f6f8fa;--surface:#ffffff;'
    '--brand-900:#0b3d70;--brand-700:#1565c0;--brand-600:#1976d2;'
    '--brand-500:#1e88e5;--brand-400:#42a5f5;--brand-100:#e3f0fb;--brand-50:#f2f8fe;'
    '--success-700:#1b7f4b;--success-500:#22a565;--success-100:#e6f6ec;'
    '--warning-700:#9a6700;--warning-500:#e3920b;--warning-100:#fdf3dd;'
    '--danger-700:#c0392b;--danger-500:#e24b4a;--danger-100:#fbe9e8;'
    '--info-700:#1565c0;--info-500:#1e88e5;--info-100:#e3f0fb;'
    '--shadow-sm:0 1px 2px rgba(15,23,42,.05);'
    '--shadow-md:0 2px 8px rgba(15,23,42,.07);'
    '}'
    # Global typography
    'html,body,[class*="css"],.stApp{'
    "font-family:'Inter','IBM Plex Sans Thai','Sarabun','Segoe UI',sans-serif !important;"
    '-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;'
    'color:var(--ink-700);}'
    '.stApp{background:var(--canvas)}'
    '.main .block-container{padding-top:1.4rem;padding-bottom:3rem;max-width:1280px}'
    'h1,h2,h3,h4,h5,h6,.stMarkdown h1,.stMarkdown h2,.stMarkdown h3{'
    'color:var(--ink-900) !important;font-weight:600 !important;letter-spacing:-0.2px;'
    "font-family:'Inter','IBM Plex Sans Thai',sans-serif !important;}"
    # Page header (flat + accent bar)
    '.admin-header,.page-header{'
    'background:var(--surface);border:1px solid var(--ink-100);'
    'border-left:5px solid var(--brand-700);border-radius:12px;'
    'padding:16px 22px;margin-bottom:18px;box-shadow:var(--shadow-sm);}'
    '.admin-header h1,.page-header h1,.page-header h2{'
    'margin:0 !important;font-size:23px !important;font-weight:600 !important;'
    'color:var(--ink-900) !important;letter-spacing:-0.3px;}'
    '.admin-header p,.page-header p{'
    'margin:5px 0 0 !important;font-size:13.5px !important;'
    'color:var(--ink-500) !important;font-weight:400;}'
    # Legacy header classes → flatten
    '.header-title{color:var(--ink-900) !important;font-size:23px !important;'
    'font-weight:600 !important;letter-spacing:-0.3px;margin-bottom:14px !important;}'
    '.subheader,.sub-title{color:var(--ink-800) !important;font-size:17px !important;'
    'font-weight:600 !important;margin-top:18px !important;margin-bottom:10px !important;}'
    # Buttons (flat)
    '.stButton > button{'
    'border-radius:9px !important;border:1px solid var(--ink-200) !important;'
    'background:var(--surface) !important;color:var(--ink-800) !important;'
    'font-weight:500 !important;font-size:14px !important;padding:8px 16px !important;'
    'min-height:42px !important;'
    'box-shadow:none !important;transition:background .12s,border-color .12s;}'
    '.stButton > button:hover{'
    'border-color:var(--brand-400) !important;background:var(--brand-50) !important;}'
    '.stButton > button:active{transform:scale(0.99)}'
    '.stButton > button:focus{'
    'box-shadow:0 0 0 3px var(--brand-100) !important;outline:none !important;}'
    '.stButton > button:disabled{'
    'background:var(--ink-50) !important;color:var(--ink-300) !important;'
    'border-color:var(--ink-100) !important;cursor:not-allowed;}'
    '.stButton > button[kind="primary"],'
    '.stButton > button[data-baseweb="button"][kind="primary"]{'
    'background:var(--brand-700) !important;color:#fff !important;'
    'border-color:var(--brand-700) !important;}'
    '.stButton > button[kind="primary"]:hover{'
    'background:var(--brand-600) !important;border-color:var(--brand-600) !important;}'
    '.stDownloadButton > button{'
    'background:var(--brand-700) !important;color:#fff !important;'
    'border-color:var(--brand-700) !important;box-shadow:none !important;}'
    '.stDownloadButton > button:hover{'
    'background:var(--brand-600) !important;border-color:var(--brand-600) !important;}'
    # Metrics (flat)
    '[data-testid="stMetric"]{'
    'background:var(--surface);border:1px solid var(--ink-100);border-radius:10px;'
    'padding:13px 15px !important;box-shadow:none;}'
    '[data-testid="stMetricLabel"],[data-testid="stMetricLabel"] > div{'
    'font-size:12px !important;color:var(--ink-500) !important;font-weight:500 !important;}'
    '[data-testid="stMetricValue"]{'
    "font-family:'Inter',sans-serif !important;font-size:26px !important;"
    'font-weight:600 !important;color:var(--ink-900) !important;letter-spacing:-0.5px;}'
    '[data-testid="stMetricDelta"]{font-size:11px !important;font-weight:500 !important;}'
    # Tabs
    '.stTabs [data-baseweb="tab-list"]{'
    'gap:2px;background:transparent;border-bottom:1px solid var(--ink-100);padding:0 2px;}'
    '.stTabs [data-baseweb="tab"]{'
    'background:transparent !important;color:var(--ink-500) !important;'
    'font-weight:500 !important;font-size:14px !important;padding:9px 15px !important;'
    'border-radius:0 !important;border-bottom:2px solid transparent !important;}'
    '.stTabs [data-baseweb="tab"]:hover{color:var(--ink-800) !important;}'
    '.stTabs [aria-selected="true"]{'
    'color:var(--brand-700) !important;border-bottom-color:var(--brand-700) !important;'
    'font-weight:600 !important;}'
    # Inputs
    '.stTextInput input,.stNumberInput input,.stDateInput input,'
    '.stTextArea textarea,.stSelectbox [data-baseweb="select"] > div{'
    'border:1px solid var(--ink-200) !important;border-radius:8px !important;'
    'background:var(--surface) !important;font-size:14px !important;color:var(--ink-900) !important;}'
    '.stTextInput input:focus,.stNumberInput input:focus,'
    '.stDateInput input:focus,.stTextArea textarea:focus{'
    'border-color:var(--brand-500) !important;'
    'box-shadow:0 0 0 3px var(--brand-100) !important;outline:none !important;}'
    # Expander
    '.streamlit-expanderHeader,[data-testid="stExpander"] summary{'
    'background:var(--surface) !important;border:1px solid var(--ink-100) !important;'
    'border-radius:10px !important;font-weight:500 !important;color:var(--ink-700) !important;}'
    '.streamlit-expanderHeader:hover,[data-testid="stExpander"] summary:hover{'
    'border-color:var(--brand-400) !important;color:var(--ink-900) !important;}'
    '[data-testid="stExpander"]{border:none !important;box-shadow:none !important;}'
    # Sidebar
    '[data-testid="stSidebar"]{background:var(--surface) !important;'
    'border-right:1px solid var(--ink-100);}'
    '[data-testid="stSidebar"] .block-container{padding-top:1.3rem}'
    # Alerts / containers
    '.stAlert{border-radius:10px !important;border-width:1px !important;}'
    '[data-baseweb="notification"]{border-radius:10px !important}'
    '[data-testid="stDataFrame"]{border:1px solid var(--ink-100);'
    'border-radius:10px;overflow:hidden;}'
    'div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:12px !important;}'
    '.stCheckbox label,.stRadio label{font-size:14px !important;color:var(--ink-700) !important}'
    'hr{border-color:var(--ink-100) !important;opacity:1 !important}'
    # Section title chip
    '.section-mega-title{'
    'display:flex;align-items:center;gap:10px;background:var(--surface);'
    'border:1px solid var(--ink-100);border-left:4px solid var(--brand-700);'
    'padding:13px 17px;border-radius:8px;margin:22px 0 13px;'
    'font-size:17px;font-weight:600;color:var(--ink-900);box-shadow:var(--shadow-sm);}'
    # Legacy gradient cards → flatten
    '.card{background:var(--surface) !important;border:1px solid var(--ink-100) !important;'
    'border-left:4px solid var(--brand-700) !important;border-radius:12px !important;'
    'box-shadow:var(--shadow-sm) !important;padding:16px 18px !important;}'
    '.card-waiting{border-left-color:var(--warning-500) !important;}'
    '.card-inor{border-left-color:var(--brand-500) !important;}'
    '.card-recovery{border-left-color:var(--success-500) !important;}'
    '.card-emergency{border-left-color:var(--danger-500) !important;'
    'border:1px solid var(--danger-100) !important;border-left:4px solid var(--danger-500) !important;}'
    # OR room cards
    '.or-room-card{background:var(--surface) !important;border-radius:12px !important;'
    'border:1px solid var(--ink-100) !important;box-shadow:var(--shadow-sm) !important;'
    'border-top:3px solid var(--ink-200) !important;}'
    '.or-room-empty{background:var(--ink-50) !important;border-top-color:var(--ink-300) !important;}'
    '.or-room-active{background:var(--surface) !important;'
    'border-top-color:var(--brand-700) !important;}'
    # KPI / legacy metric boxes
    '.metric-box,.kpi-card{background:var(--surface) !important;border-radius:10px !important;'
    'border:1px solid var(--ink-100) !important;padding:13px 15px !important;'
    'box-shadow:none !important;}'
    '.metric-num,.stat-value{'
    "font-family:'Inter',sans-serif !important;font-size:26px !important;"
    'font-weight:600 !important;color:var(--ink-900) !important;letter-spacing:-0.5px;}'
    '.metric-lbl,.stat-title{'
    'font-size:12px !important;color:var(--ink-500) !important;font-weight:500 !important;}'
    '.timer{font-family:"Courier New",monospace;color:var(--danger-500) !important;}'
    '.pill{display:inline-block;font-size:12.5px;font-weight:500;'
    'padding:3px 11px;border-radius:12px;letter-spacing:0.2px;}'
    # Status chips กลาง (สี = ความหมาย) — ใช้แทน inline color ในหน้าต่างๆ ได้
    '.or-chip{display:inline-flex;align-items:center;gap:4px;font-size:12.5px;'
    'font-weight:500;padding:2px 10px;border-radius:999px;white-space:nowrap;}'
    '.or-chip.wait{background:var(--ink-100);color:var(--ink-500);}'
    '.or-chip.hold{background:var(--warning-100);color:var(--warning-700);}'
    '.or-chip.inor{background:var(--success-100);color:var(--success-700);}'
    '.or-chip.over{background:var(--danger-100);color:var(--danger-700);}'
    '.or-chip.post{background:var(--info-100);color:var(--info-700);}'
    '.or-chip.done{background:var(--ink-50);color:var(--ink-400);}'
    '.stCaption,[data-testid="stCaptionContainer"]{'
    'color:var(--ink-500) !important;font-size:12.5px !important;}'
    '.stProgress > div > div{background:var(--brand-700) !important}'
    '.stProgress > div{background:var(--ink-100) !important}'
    # Sidebar brand block
    '.or-brand{display:flex;align-items:center;gap:10px;padding:2px 2px 14px;'
    'border-bottom:1px solid var(--ink-100);margin-bottom:12px;}'
    '.or-brand .mark{display:inline-flex;align-items:center;justify-content:center;'
    'width:32px;height:32px;border-radius:9px;background:var(--brand-100);'
    'color:var(--brand-700);font-size:18px;}'
    '.or-brand .nm{font-size:15px;font-weight:600;color:var(--ink-900);line-height:1.15;}'
    '.or-brand .sub{font-size:11px;color:var(--ink-500);}'
    # เลิกใช้ sidebar แล้ว (เปลี่ยนเป็นแท็บบนสุด) — ซ่อน sidebar + header bar + ลดช่องว่างด้านบน
    '[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],'
    '[data-testid="collapsedControl"]{display:none !important;}'
    '[data-testid="stHeader"]{background:transparent !important;height:0 !important;}'
    '.block-container,[data-testid="stMainBlockContainer"],'
    '[data-testid="stAppViewBlockContainer"]{padding-top:1.2rem !important;}'
    # 🗂️ เมนูหลัก: แต่ง radio แนวนอน (key=_main_page) ให้เป็น "แท็บขีดเส้นใต้" แบบ production
    #    (ยังเป็น radio = รันเฉพาะหน้าที่เลือก · ถ้า Streamlit รุ่นเก่าไม่มี class นี้ จะ fallback เป็น radio ปกติ ไม่พัง)
    '.st-key-_main_page div[role="radiogroup"]{gap:2px !important;flex-wrap:wrap;'
    'border-bottom:1px solid var(--ink-100);margin-bottom:4px;}'
    '.st-key-_main_page div[role="radiogroup"]>label{margin:0 !important;'
    'padding:9px 18px !important;border-bottom:2px solid transparent;'
    'border-radius:8px 8px 0 0;cursor:pointer;transition:background .15s;}'
    '.st-key-_main_page div[role="radiogroup"]>label:hover{background:var(--brand-50) !important;}'
    '.st-key-_main_page div[role="radiogroup"]>label>div:first-child{display:none !important;}'
    '.st-key-_main_page div[role="radiogroup"]>label p{font-size:15px !important;'
    'color:var(--ink-500) !important;font-weight:600 !important;margin:0 !important;}'
    '.st-key-_main_page div[role="radiogroup"]>label:has(input:checked){'
    'border-bottom-color:var(--brand-700) !important;}'
    '.st-key-_main_page div[role="radiogroup"]>label:has(input:checked) p{'
    'color:var(--brand-700) !important;}'
    # 🟢 ชิปสถานะบนหัว (header status chips)
    '.or-chips{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 8px;}'
    '.or-chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;'
    'color:var(--ink-500);background:var(--brand-50);padding:4px 10px;'
    'border-radius:8px;border:1px solid var(--ink-100);}'
    '.or-chip .dot{width:7px;height:7px;border-radius:50%;background:#10b981;'
    'display:inline-block;}'
    # 🔇 ซ่อน iframe ของ auto-refresh (มันจองช่องว่างเปล่าใต้แท็บ) — ยุบทั้ง container
    'iframe[title="streamlit_autorefresh.st_autorefresh"]{display:none !important;}'
    '[data-testid="stElementContainer"]:has(> iframe[title="streamlit_autorefresh.st_autorefresh"]),'
    '[data-testid="element-container"]:has(> iframe[title="streamlit_autorefresh.st_autorefresh"]){'
    'display:none !important;height:0 !important;margin:0 !important;}'
    # 📏 ลดระยะห่างแนวตั้งระหว่างบล็อก ให้แน่นแบบ dashboard (ข้อมูลขยับขึ้น ไม่ต้องเลื่อนเยอะ)
    '[data-testid="stVerticalBlock"]{gap:0.6rem !important;}'
    '</style>'
)


def inject_theme() -> None:
    """Inject central theme CSS (ต้องเรียกทุก rerun — อย่าใส่ session_state guard)."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def render_page_header(emoji: str, title: str, subtitle: str = "") -> None:
    """Render unified page header — เรียกใช้ตอนต้น page."""
    sub_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="page-header"><h2>{emoji} {title}</h2>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_brand(title: str = "OR Flow", subtitle: str = "ห้องผ่าตัดศัลยกรรมทั่วไป",
                         icon: str = "🏥") -> None:
    """Render แบรนด์หัว sidebar — เรียกตอนต้น sidebar."""
    st.sidebar.markdown(
        f'<div class="or-brand"><span class="mark">{icon}</span>'
        f'<div><div class="nm">{title}</div><div class="sub">{subtitle}</div></div></div>',
        unsafe_allow_html=True,
    )
