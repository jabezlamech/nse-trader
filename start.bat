@echo off
title NSE Candle Analyzer

echo.
echo  =========================================
echo   NSE Candle Analyzer - Starting Server
echo  =========================================
echo.
echo  Dashboard : http://localhost:8000
echo  API Docs  : http://localhost:8000/docs
echo  Kite Auth : http://localhost:8000/api/kite/login
echo.
echo  Press Ctrl+C to stop.
echo.

cd /d "%~dp0backend"

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
