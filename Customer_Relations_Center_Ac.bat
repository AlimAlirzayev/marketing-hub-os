@echo off
setlocal
title Xalq Insurance Digital OS - Customer Relations Center Launcher
set "ROOT=%~dp0"
set "CENTER_DIR=%ROOT%cx-command-center"

echo Customer Relations Center acilir...
echo Dashboard: http://127.0.0.1:8810
echo.

netstat -ano | findstr ":8810" | findstr "LISTENING" >nul
if errorlevel 1 (
    start "Xalq Insurance Digital OS - Customer Relations Center Server" powershell -NoExit -ExecutionPolicy Bypass -File "%CENTER_DIR%\run.ps1" 8810
    timeout /t 4 /nobreak >nul
) else (
    echo Customer Relations Center artiq isleyir.
)
start "" "http://127.0.0.1:8810"

echo Customer Relations Center ayrica pencereye qaldirildi.
echo Bu pencereni baglaya bilersiniz.
timeout /t 2 /nobreak >nul
endlocal
