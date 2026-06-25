# Marketing OS Hub launcher (the front door, port 8000).
# Reuses meta-capi's venv (already has fastapi + uvicorn + requests).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot "..\meta-capi\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        python -m venv .venv
        & $py -m pip install --quiet --upgrade pip
        & $py -m pip install --quiet fastapi uvicorn requests
    }
}

$env:PYTHONIOENCODING = "utf-8"
$port = if ($args.Count -gt 0) { $args[0] } else { 8000 }
Write-Host "Marketing OS -> http://localhost:$port" -ForegroundColor Green
Start-Process "http://localhost:$port"
& $py -m uvicorn app:app --host 127.0.0.1 --port $port
