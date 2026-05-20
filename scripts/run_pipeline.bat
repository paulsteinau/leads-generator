@echo off
cd /d %~dp0..
set PYTHONPATH=%cd%
py -3.12 pipeline\run.py
pause
