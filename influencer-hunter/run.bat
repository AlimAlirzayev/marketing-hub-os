@echo off
REM Influencer Hunter dashboard - AZ creator intelligence.
cd /d "%~dp0"
echo Starting Influencer Hunter backend on http://localhost:8840 ...
start "" http://localhost:8840
"..\.venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8840
pause
