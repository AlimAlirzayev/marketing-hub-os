# Atelier standalone launcher. Atelier is an importable package, so the
# server runs as `atelier.app:app` from the repo root (one dir up). The venv
# still lives in atelier/.venv. Registered in services.json (port 8820,
# "Kreativ Studiya") and embedded in the hub like every other studio.
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$root = Split-Path $here -Parent

$py = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Setting up virtual environment..." -ForegroundColor Cyan
    python -m venv (Join-Path $here ".venv")
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r (Join-Path $here "requirements.txt")
}

# UTF-8 so Azerbaijani text logs cleanly on Windows consoles.
$env:PYTHONIOENCODING = "utf-8"

$port = if ($args.Count -gt 0) { $args[0] } else { 8820 }
Write-Host "Atelier -> http://localhost:$port" -ForegroundColor Green
Set-Location $root
Start-Process "http://localhost:$port"
& $py -m uvicorn atelier.app:app --host 127.0.0.1 --port $port
