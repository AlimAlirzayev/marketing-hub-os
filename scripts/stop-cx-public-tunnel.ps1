$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repo "data\logs\cloudflared-cx.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "Tunnel PID fayli tapilmadi."
    exit 0
}

$pid = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pid) {
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $pid -Force
        Write-Host "Tunnel dayandirildi: PID $pid"
    } else {
        Write-Host "Tunnel prosesi artiq islemir."
    }
}
Remove-Item -Force $pidFile -ErrorAction SilentlyContinue
