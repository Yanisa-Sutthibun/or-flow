@echo off
chcp 65001 >nul
title General Surgery OR Dashboard
cd /d "%~dp0"
echo ============================================================
echo  General Surgery OR Dashboard - Streamlit Launcher
echo ============================================================
echo.
echo Current folder: %CD%
echo.

REM Check if streamlit is installed
streamlit --version >nul 2>&1
if errorlevel 1 (
    echo [!] streamlit not found. Installing dependencies...
    pip install -r requirements.txt
    echo.
    pip install xgboost lightgbm rapidfuzz joblib pyarrow
    echo.
)

echo Starting Streamlit...
echo Browser should open automatically at http://localhost:8501
echo (Press Ctrl+C in this window to stop)
echo.
streamlit run main_or_app.py

pause
