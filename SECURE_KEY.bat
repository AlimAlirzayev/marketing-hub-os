@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\secure_key.py %*
) else (
  python scripts\secure_key.py %*
)
pause
