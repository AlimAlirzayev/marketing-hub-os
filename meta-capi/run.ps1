# Meta CAPI helper launcher. Creates/uses a local venv, then runs the checker.
#   .\run.ps1            # verify (stages 0-2, sends nothing)
#   .\run.ps1 --send     # also fire a test event into Test Events
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
& $py verify_capi.py @args
