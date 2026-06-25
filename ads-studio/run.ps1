# Ads Studio launcher. Creates/uses the local venv, then serves the dashboard.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Setting up virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r requirements.txt
}

# UTF-8 so Azerbaijani text logs cleanly on Windows consoles.
$env:PYTHONIOENCODING = "utf-8"

$port = if ($args.Count -gt 0) { $args[0] } else { 8800 }
Write-Host "Ads Studio -> http://localhost:$port" -ForegroundColor Green
Start-Process "http://localhost:$port"
& $py -m uvicorn app:app --host 127.0.0.1 --port $port
