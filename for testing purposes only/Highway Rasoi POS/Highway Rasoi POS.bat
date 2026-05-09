@echo off
title Highway Rasoi POS
color 0B
cls
echo.
echo  ============================================================
echo                  Highway Rasoi POS
echo                  Starting up...
echo  ============================================================
echo.

REM --- Make sure we are running from the script's own folder ---
cd /d "%~dp0"

REM --- Check Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python is not installed or not on PATH.
    echo.
    echo      Please install Python 3.x from:
    echo      https://www.python.org/downloads/
    echo.
    echo      During installation, tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
echo  [ OK ] Python found.
echo.

REM --- Install dependencies (silent) ---
echo  Checking dependencies...
pip install flask flask-socketio werkzeug --quiet --disable-pip-version-check >nul 2>&1
echo  [ OK ] Dependencies ready.
echo.

REM --- Make sure data + uploads exist ---
if not exist "data" mkdir data
if not exist "static\uploads" mkdir static\uploads

echo  ============================================================
echo    Highway Rasoi POS is now running.
echo.
echo    Open in your browser:
echo       http://127.0.0.1:5003/login
echo.
echo    Default biller login:
echo       ID:        BILLER001
echo       Password:  Pass@1234
echo.
echo    Admin portal:  http://127.0.0.1:5003/admin/login
echo       Admin ID:  POSADMIN2024
echo       Password:  Adm!nX9@Secure
echo.
echo    To stop the server, close this window or press Ctrl+C.
echo  ============================================================
echo.

REM --- Auto-open the browser after a short delay ---
start "" /b cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5003/login"

REM --- Run the server (blocking) ---
python app.py

echo.
echo  Server has stopped.
pause
