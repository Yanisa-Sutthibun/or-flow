"""
test_minimal.py — เทสว่า Streamlit + environment ทำงานปกติไหม
รัน: streamlit run test_minimal.py
"""
import streamlit as st

st.set_page_config(page_title="Test", page_icon="🧪", layout="wide")

st.title("🧪 Test Minimal Page")
st.success("✅ ถ้าเห็นหน้านี้ = Streamlit + environment ทำงานปกติ")

st.markdown("---")

# Test 1: imports
st.subheader("Test 1: Python imports")
try:
    import pandas as pd
    st.write("✅ pandas:", pd.__version__)
except Exception as e:
    st.error(f"❌ pandas: {e}")

try:
    import xgboost
    st.write("✅ xgboost:", xgboost.__version__)
except Exception as e:
    st.error(f"❌ xgboost: {e}")

try:
    import joblib
    st.write("✅ joblib:", joblib.__version__)
except Exception as e:
    st.error(f"❌ joblib: {e}")

try:
    from rapidfuzz import fuzz
    st.write("✅ rapidfuzz: ok")
except Exception as e:
    st.error(f"❌ rapidfuzz: {e}")

try:
    import plotly
    st.write("✅ plotly:", plotly.__version__)
except Exception as e:
    st.error(f"❌ plotly: {e}")

# Test 2: model file exists
st.subheader("Test 2: Files")
import os
for f in [
    "models/main_or_model_v1.pkl",
    "models/main_or_pipeline_v1.pkl",
    "models/main_or_clusters_v1.pkl",
    "data/historical/main_or_history.csv",
    "main_or_predictor.py",
    "main_or_core.py",
]:
    if os.path.exists(f):
        size = os.path.getsize(f) / 1024
        st.write(f"✅ {f} ({size:.1f} KB)")
    else:
        st.error(f"❌ ไม่พบ: {f}")

# Test 3: load predictor
st.subheader("Test 3: Load predictor")
try:
    from main_or_predictor import SurgicalTimePredictor
    p = SurgicalTimePredictor.load_default()
    st.write(f"✅ Predictor loaded — vocab: {len(p.proc_kw_vocab)} หัตถการ, {len(p.surgeon_vocab)} แพทย์")

    # Test predict
    r = p.predict(
        procedure_name="EGD + Colonoscopy",
        surgeon_name="SURG_001",  # 🔒 M-12: ไม่ฝังชื่อแพทย์จริงในไฟล์ทดสอบ (git-tracked)
        division=1, orroom=11, age=68, planned_hour=9,
        opedate="2024-07-15",
    )
    st.write(f"✅ Test predict: {r.predicted_minutes} นาที, confidence={r.confidence_level}")
except Exception as e:
    st.error(f"❌ Predictor error: {e}")
    import traceback
    st.code(traceback.format_exc())

# Test 4: Secrets
st.subheader("Test 4: Streamlit secrets")
try:
    # 🔒 M-12: ไม่โชว์รหัสจริงบนจอ — บอกแค่ "ตั้งค่าแล้ว/ยัง"
    has_pw = bool(st.secrets.get("app_password"))
    mode = st.secrets.get("db_mode", "(no key)")
    st.write(f"app_password: {'✅ ตั้งค่าแล้ว' if has_pw else '❌ ยังไม่ตั้ง'}")
    st.write(f"db_mode: `{mode}`")
except Exception as e:
    st.warning(f"⚠️ secrets.toml: {e}")

# Test 5: โมเดลที่ deploy จริง (or_time_model / honest_v1) — smoke test
st.subheader("Test 5: โมเดลที่ deploy (honest_v1)")
try:
    import or_time_model
    d = or_time_model.predict_detail({
        'procedure_name': 'Appendectomy', 'surgeon_name': '',
        'division': '75', 'orroom': 11, 'age': 40, 'planned_hour': 9,
    }, 'room_use')
    st.write(f"✅ honest_v1 ทำนาย {d['predicted_min']} นาที · "
             f"ช่วง 90%={d['interval90']} · conformal={d['conformal']}")
except Exception as e:
    st.error(f"❌ or_time_model error: {e}")
    import traceback
    st.code(traceback.format_exc())

st.markdown("---")
st.caption("ถ้าทุก test ผ่าน = ปัญหาไม่ใช่ environment → ผมจะแก้ main_or_app.py ต่อ")
