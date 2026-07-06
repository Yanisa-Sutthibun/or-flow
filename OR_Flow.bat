@echo off
REM ═══════════════════════════════════════════════════════════════
REM  OR Flow - one-file launcher
REM  Double-click = open the app (auto-minimizes, won't start twice)
REM  To STOP the app: close the minimized "OR Flow" window in taskbar
REM ═══════════════════════════════════════════════════════════════

REM Relaunch self minimized (so no big black window stays on screen)
if not "%1"=="MIN" (
    start "OR Flow" /min cmd /c ""%~f0" MIN"
    exit /b 0
)

chcp 65001 >nul
title OR Flow  (close this window to stop the app)
cd /d "%~dp0"

REM Already running? -> just open the browser, don't start twice
netstat -ano | findstr :8501 | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
    start "" http://localhost:8501
    exit /b 0
)

REM First run on this machine? install requirements once
streamlit --version >nul 2>&1
if errorlevel 1 (
    echo [!] Installing requirements (first time only)...
    pip install -r requirements.txt
)

echo Starting OR Flow ... the browser will open automatically.
echo Keep this window minimized. Closing it stops the app.
streamlit run main_or_app.py
