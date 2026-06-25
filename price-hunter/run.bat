@echo off
REM Price Hunter dashboard - on-demand AZ price intelligence.
cd /d "%~dp0"
echo Starting Price Hunter backend on http://localhost:8830 ...
start "" http://localhost:8830
".venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8830
pause
