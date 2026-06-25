# GA4 Studio launcher — website analytics dashboard. Opens in the browser.
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
$port = if ($args.Count -gt 0) { $args[0] } else { 8850 }
Write-Host "GA4 Studio (Vebsayt Analitikasi) -> http://localhost:$port" -ForegroundColor Green
Start-Process "http://localhost:$port"
& $py -m uvicorn app:app --host 127.0.0.1 --port $port
