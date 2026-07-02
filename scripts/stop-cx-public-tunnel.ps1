$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repo "data\logs\cloudflared-cx.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "Tunnel PID fayli tapilmadi."
    exit 0
}

$tunnelPid = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
if ($tunnelPid) {
    $proc = Get-Process -Id $tunnelPid -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $tunnelPid -Force
        Write-Host "Tunnel dayandirildi: PID $tunnelPid"
    } else {
        Write-Host "Tunnel prosesi artiq islemir."
    }
}
Remove-Item -Force $pidFile -ErrorAction SilentlyContinue
