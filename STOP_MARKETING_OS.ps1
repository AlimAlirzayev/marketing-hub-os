# Stops every Marketing OS service (frees the ports). ASCII-only on purpose.
$ports = 8000, 8501, 8800, 8810, 8811, 8820, 8830, 8840
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
