@echo off
cd /d %~dp0
set PYTHONPATH=%cd%

echo Starte Berlin Lead-Gen...

:: API starten (eigenes Fenster)
start "Berlin API" cmd /k "py -3.12 -m uvicorn api.main:app --reload --port 8000"

:: Kurz warten damit API hochfaehrt
timeout /t 3 /nobreak > nul

:: Dashboard starten (eigenes Fenster)
start "Berlin Dashboard" cmd /k "cd dashboard && npm run dev"

:: Kurz warten damit Next.js startet
timeout /t 5 /nobreak > nul

:: Browser oeffnen
start "" "http://localhost:3000"

echo Fertig! Browser oeffnet sich automatisch.
echo Beide Fenster (API + Dashboard) koennen minimiert werden.
