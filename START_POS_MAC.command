#!/bin/bash
clear
echo ""
echo "  ============================================================"
echo "    Restaurant POS System  -  Starting..."
echo "  ============================================================"
echo ""

PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "  [ERROR] Python not found!"
    echo "  Install from: https://www.python.org/downloads/"
    echo "  Or via Homebrew: brew install python"
    read -p "  Press Enter to exit..."
    exit 1
fi

echo "  [OK] $($PYTHON --version)"
echo ""
echo "  Checking dependencies..."
$PYTHON -m pip install flask flask-socketio werkzeug --quiet --disable-pip-version-check 2>&1
echo "  [OK] Dependencies ready"
echo ""

mkdir -p data
mkdir -p static/uploads

(sleep 3 && open "http://127.0.0.1:5003/login" 2>/dev/null || \
           xdg-open "http://127.0.0.1:5003/login" 2>/dev/null) &

echo "  ============================================================"
echo "    POS running at:     http://127.0.0.1:5003"
echo "    Admin portal:       http://127.0.0.1:5003/admin/login"
echo "    Dashboard (phone):  http://[YOUR-IP]:5003/dashboard"
echo ""
echo "    Press Ctrl+C to stop"
echo "  ============================================================"
echo ""

$PYTHON app.py

echo ""
echo "  Server stopped."
read -p "  Press Enter to exit..."
