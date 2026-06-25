@echo off
title Xalq Insurance Digital OS - Bas Iqametgah
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo Xalq Insurance Digital OS Bas Iqametgah ise salinir...
echo Dashboard: http://127.0.0.1:8501
echo.

netstat -ano | findstr ":8501" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo Bas Iqametgah artiq isleyir.
    start "" "http://127.0.0.1:8501"
    timeout /t 2 /nobreak >nul
    exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
    echo Ilk acilisdir: Python virtual environment yaradilir...
    python -m venv .venv
)

if not exist ".venv\.panel-ready" (
    echo Lazimi paketler qurasdirilir...
    ".venv\Scripts\python.exe" -m pip install -r requirements-panel.txt
    if errorlevel 1 (
        echo.
        echo Paketlerin qurasdirilmasinda problem oldu.
        pause
        exit /b 1
    )
    echo ready > ".venv\.panel-ready"
)

start "" "http://127.0.0.1:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
endlocal
