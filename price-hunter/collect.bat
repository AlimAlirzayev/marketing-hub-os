@echo off
REM One background price-collection pass (records history, no notifications).
REM Schedule hourly (silent):
REM   schtasks /Create /TN "PriceHunterCollect" /TR "\"%~dp0collect.bat\"" /SC HOURLY /F
cd /d "%~dp0"
".venv\Scripts\python.exe" collector.py
