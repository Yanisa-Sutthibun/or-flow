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
# (SurgicalTimePredictor + pkl v1 ถูกถอดจาก chain 4 ก.ค. 2026 — เช็คเฉพาะของที่ใช้จริง)
st.subheader("Test 2: Files")
import os
for f in [
    "models/thesis_ML/hier_room_use.json",
    "models/thesis_ML/resid_room_use.pkl",
    "models/thesis_ML/conformal.json",
    "models/model_v2/model.pkl",
    "main_or_core.py",
]:
    if os.path.exists(f):
        size = os.path.getsize(f) / 1024
        st.write(f"✅ {f} ({size:.1f} KB)")
    else:
        st.error(f"❌ ไม่พบ: {f}")

# Test 3: shadow model_v2 (โหลด + ทำนาย 1 เคส)
st.subheader("Test 3: Shadow model_v2")
try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'models', 'model_v2'))
    from predictor import ModelV2
    _mv2 = ModelV2()
    r2 = _mv2.predict_case({'procedure': 'EGD + Colonoscopy',
                            'surgeon': 'SURG_002',  # 🔒 รหัส ไม่ใช้ชื่อจริง
                            'division': '75', 'age': 68})
    st.write(f"✅ model_v2 ทำนาย {r2['predicted_min']} นาที · "
             f"ช่วง 90%={r2['range90']} · มั่นใจ={r2['confidence']}")
except Exception as e:
    st.error(f"❌ model_v2 error: {e}")
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

# Test 5: โมเดลที่ deploy จริง (or_time_model / thesis_ML) — smoke test
st.subheader("Test 5: โมเดลที่ deploy (thesis_ML)")
try:
    import or_time_model
    d = or_time_model.predict_detail({
        'procedure_name': 'Appendectomy', 'surgeon_name': '',
        'division': '75', 'orroom': 11, 'age': 40, 'planned_hour': 9,
    }, 'room_use')
    st.write(f"✅ thesis_ML ทำนาย {d['predicted_min']} นาที · "
             f"ช่วง 90%={d['interval90']} · conformal={d['conformal']}")
except Exception as e:
    st.error(f"❌ or_time_model error: {e}")
    import traceback
    st.code(traceback.format_exc())

st.markdown("---")
st.caption("ถ้าทุก test ผ่าน = ปัญหาไม่ใช่ environment → ผมจะแก้ main_or_app.py ต่อ")
