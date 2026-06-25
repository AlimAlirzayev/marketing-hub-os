# CAPI backup gateway launcher. Real-time browser-event collector (Pixel twin).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Setting up virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r requirements.txt
}

$env:PYTHONIOENCODING = "utf-8"
$port = if ($args.Count -gt 0) { $args[0] } else { 8812 }
Write-Host "CAPI Gateway -> http://localhost:$port  (demo: /demo)" -ForegroundColor Green
& $py -m uvicorn gateway:app --host 0.0.0.0 --port $port
