@echo off
REM One-click, token-free engine sync. Double-click this any time.
REM Pulls the latest shared engine and pushes your committed engine commits.
REM No chat, no Claude tokens -- it just runs the same safe sync brain.
cd /d "%~dp0"
python scripts\sync_engine.py
echo.
pause
