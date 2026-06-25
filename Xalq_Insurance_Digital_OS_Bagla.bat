@echo off
title Xalq Insurance Digital OS - Bagla
echo Xalq Insurance Digital OS panelleri baglanir...

for %%P in (8501 8810 8840) do (
    for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
        echo Port %%P prosesi dayandirilir: %%A
        taskkill /PID %%A /F >nul 2>nul
    )
)

echo Hazirdir.
timeout /t 2 /nobreak >nul
