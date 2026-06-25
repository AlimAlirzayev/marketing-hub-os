@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

rem --- Find a Python that has the deps (prefer local venv, fall back to ads-studio) ---
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=..\ads-studio\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

rem --- CSV path: dragged onto the .bat, or typed in ---
set "CSV=%~1"
if "%CSV%"=="" set /p "CSV=CSV faylini bu pencereye surusdurun, ve ya yolunu yapisdirin: "
if "%CSV%"=="" goto :end

echo.
echo ============================================================
echo   ADDIM 1/2 - ON BAXIS (Meta-ya HEC NE gonderilmir)
echo ============================================================
"%PY%" import_sales.py "%CSV%"
if errorlevel 1 goto :end

echo.
echo ============================================================
echo   Yuxaridaki reqemler dogrudursa Meta-ya gonderek.
echo ============================================================
set /p "GO=GONDERMEK ucun 1 yazin ve Enter (legv: sadece Enter): "
if not "%GO%"=="1" goto :end

echo.
echo   Gonderilir...
"%PY%" import_sales.py "%CSV%" --send

:end
echo.
pause
