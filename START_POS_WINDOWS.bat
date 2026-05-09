@echo off
title Restaurant POS System
color 0A
cls
echo.
echo  ============================================================
echo    Restaurant POS System  -  Starting...
echo  ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found!
    echo  Download from: https://www.python.org/downloads/
    echo  Check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo  [OK] Python found
echo.
echo  Checking dependencies...
pip install flask flask-socketio werkzeug --quiet --disable-pip-version-check
echo  [OK] Dependencies ready
echo.

if not exist "data" mkdir data
if not exist "static\uploads" mkdir static\uploads

echo  ============================================================
echo    POS running at:     http://127.0.0.1:5003
echo    Admin portal:       http://127.0.0.1:5003/admin/login
echo    Dashboard (phone):  http://[YOUR-IP]:5003/dashboard
echo.
echo    Press Ctrl+C to stop
echo  ============================================================
echo.

start "" timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5003/login"

python app.py
pause
