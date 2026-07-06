# ============================================================
#  Xalq Sigorta - Marketing OS - single start-up
#  Registry-driven: it launches EXACTLY what services.json lists
#  (the hub + every tool), then opens the front door in a browser.
#  Add a tool to services.json -> it starts here automatically.
#  NOTE: ASCII-only on purpose - Windows PowerShell 5.1 mis-reads
#  non-ASCII .ps1 source and fails to parse. (Service names come
#  from the UTF-8 JSON at runtime, so diacritics there are fine.)
# ============================================================
$ErrorActionPreference = "SilentlyContinue"
$root = $PSScriptRoot

# Step 0: pull the latest shared engine BEFORE booting, so "open the system"
# always means "run the newest code". Safe + best-effort (never blocks startup).
Write-Host ""
Write-Host "  Muherrik senkronlasdirilir (GitHub)..." -ForegroundColor DarkCyan
python (Join-Path $root "scripts\sync_engine.py")

$reg = Get-Content (Join-Path $root "services.json") -Raw -Encoding UTF8 | ConvertFrom-Json

Write-Host ""
Write-Host "  Xalq Sigorta - Marketing OS basladilir (services.json)..." -ForegroundColor Cyan
Write-Host ""

foreach ($s in $reg.services) {
    $py  = Join-Path $root ($s.venv + "\Scripts\python.exe")
    $cwd = Join-Path $root $s.cwd
    if (-not (Test-Path $py)) {
        Write-Host ("  ! {0,-11} venv yoxdur: {1}" -f $s.key, $s.venv) -ForegroundColor Yellow
        continue
    }
    if ($s.launch -eq "uvicorn") {
        $argList = @("-m","uvicorn",$s.target,"--host","127.0.0.1","--port","$($s.port)")
    } elseif ($s.launch -eq "streamlit") {
        $argList = @("-m","streamlit","run",$s.target,"--server.port","$($s.port)","--server.headless","true")
    } else {
        Write-Host ("  ! {0,-11} bilinmeyen launch: {1}" -f $s.key, $s.launch) -ForegroundColor Yellow
        continue
    }
    Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $cwd -WindowStyle Hidden
    Write-Host ("  + {0,-11} http://localhost:{1}" -f $s.key, $s.port) -ForegroundColor Green
}

# Always-on brain: worker + scheduler + Telegram bot in ONE process. Safe to
# start blindly - a singleton lock makes a second copy exit immediately.
$gwpy = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $gwpy) {
    Start-Process -FilePath $gwpy -ArgumentList @("-m","gateway.supervisor") -WorkingDirectory $root -WindowStyle Hidden
    Write-Host "  + supervisor  (Telegram agent + isci + planlayici)" -ForegroundColor Green
}

$door = ($reg.services | Where-Object { $_.front_door } | Select-Object -First 1)
$port = if ($door) { $door.port } else { 8000 }
Start-Sleep -Seconds 6
Write-Host ""
Write-Host ("  Hazirdir -> http://localhost:{0}" -f $port) -ForegroundColor Cyan
Write-Host ""
Start-Process ("http://localhost:{0}" -f $port)

# Self-check at boot: reconcile registry vs reality (the blind-spot catcher).
# Prints which services came up and flags any unregistered/missing ones.
$env:PYTHONIOENCODING = "utf-8"
$apy = Join-Path $root "meta-capi\.venv\Scripts\python.exe"
if (Test-Path $apy) { & $apy (Join-Path $root "audit_services.py") }
