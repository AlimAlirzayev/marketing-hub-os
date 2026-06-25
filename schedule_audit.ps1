# Registers a daily Windows task that runs the drift audit and pings Telegram
# ONLY when there is real drift (no daily spam). Free: no LLM tokens.
#   .\schedule_audit.ps1            # register, daily 09:00
#   .\schedule_audit.ps1 -Time 08:30
#   .\schedule_audit.ps1 -Heartbeat # also send a daily "all-ok" message
#   .\schedule_audit.ps1 -Remove    # unregister
# ASCII-only on purpose (Windows PowerShell 5.1 parser).
param(
    [string]$Time = "09:00",
    [switch]$Heartbeat,
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$task = "MarketingOS-Audit"

if ($Remove) {
    schtasks /Delete /TN $task /F
    Write-Host "Removed scheduled task '$task'." -ForegroundColor Yellow
    return
}

$py = Join-Path $root "meta-capi\.venv\Scripts\python.exe"
$script = Join-Path $root "audit_services.py"
if (-not (Test-Path $py)) { throw "Python venv not found: $py" }

$flags = "--telegram"
if ($Heartbeat) { $flags = "--telegram --always" }
$argument = ('"{0}" {1}' -f $script, $flags)

$action  = New-ScheduledTaskAction -Execute $py -Argument $argument -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At ([DateTime]::Parse($Time))
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Force `
    -Description "Marketing OS registry-vs-reality drift audit -> Telegram alert on drift" | Out-Null

Write-Host "Scheduled '$task' daily at $Time (drift-only Telegram)." -ForegroundColor Green
Write-Host "  Heartbeat (daily all-ok msg): .\schedule_audit.ps1 -Heartbeat" -ForegroundColor DarkGray
Write-Host "  Remove: .\schedule_audit.ps1 -Remove" -ForegroundColor DarkGray
