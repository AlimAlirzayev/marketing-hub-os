@echo off
setlocal
title Xalq Insurance Digital OS - Launcher
set "ROOT=%~dp0"

echo Xalq Insurance Digital OS panelleri acilir...
echo.
echo 1/3 Customer Relations Center start olunur...
netstat -ano | findstr ":8810" | findstr "LISTENING" >nul
if errorlevel 1 (
    start "Xalq Insurance Digital OS - Customer Relations Center Server" powershell -NoExit -ExecutionPolicy Bypass -File "%ROOT%cx-command-center\run.ps1" 8810
) else (
    echo Customer Relations Center artiq isleyir.
)

echo 2/3 Influencer Hunter start olunur...
netstat -ano | findstr ":8840" | findstr "LISTENING" >nul
if errorlevel 1 (
    start "Xalq Insurance Digital OS - Influencer Hunter" /D "%ROOT%influencer-hunter" "%ROOT%.venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8840
) else (
    echo Influencer Hunter artiq isleyir.
)

echo 3/3 Bas Iqametgah paneli start olunur...
call "%ROOT%Xalq_Insurance_Digital_OS_Bas_Iqametgah.bat"

endlocal
