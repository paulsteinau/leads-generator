@echo off
cd /d %~dp0..
set PYTHONPATH=%cd%
py -3.12 -m uvicorn api.main:app --port 8000
