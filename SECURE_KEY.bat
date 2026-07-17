@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\secure_key.py %*
) else (
  python scripts\secure_key.py %*
)
if errorlevel 1 goto :done
if /I "%~1"=="META_ACCESS_TOKEN" (
  if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\meta_relaunch.py
  ) else (
    python scripts\meta_relaunch.py
  )
)
:done
pause
