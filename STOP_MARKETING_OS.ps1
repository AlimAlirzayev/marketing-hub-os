# Stops every Marketing OS service (frees the ports). ASCII-only on purpose.
# Ports come from services.json - the single source of truth - never a
# hardcoded list (the old list here silently missed 6 newer services).
$root = $PSScriptRoot
$reg = Get-Content (Join-Path $root "services.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$ports = $reg.services | ForEach-Object { $_.port }
foreach ($p in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        try {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
            Write-Host ("  - port {0} stopped" -f $p) -ForegroundColor Yellow
        } catch {}
    }
}
Write-Host ""
Write-Host "  Marketing OS stopped." -ForegroundColor Cyan
Write-Host ""
