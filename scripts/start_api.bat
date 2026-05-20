@echo off
cd /d %~dp0..
set PYTHONPATH=%cd%
set API_PORT=8001
echo Beende laufende Prozesse auf Port %API_PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%API_PORT% " ^| findstr LISTENING 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)
py -3.12 -m uvicorn api.main:app --port %API_PORT%
