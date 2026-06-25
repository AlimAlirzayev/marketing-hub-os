# Registers a daily Windows task that refreshes the Agent Radar governance scan.
# It does not run external agents, post content, spend money, or read secrets.
#   .\schedule_agent_radar.ps1            # register, daily 09:15
#   .\schedule_agent_radar.ps1 -Time 08:45
#   .\schedule_agent_radar.ps1 -Remove    # unregister
# ASCII-only on purpose (Windows PowerShell 5.1 parser).
param(
    [string]$Time = "09:15",
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$task = "MarketingOS-AgentRadar"

if ($Remove) {
    schtasks /Delete /TN $task /F
    Write-Host "Removed scheduled task '$task'." -ForegroundColor Yellow
    return
}

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Python venv not found: $py" }

$argument = "-m gateway.agent_radar autoscan"
$action  = New-ScheduledTaskAction -Execute $py -Argument $argument -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At ([DateTime]::Parse($Time))
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Force `
    -Description "Marketing OS automatic agent-governance opportunity scan" | Out-Null

Write-Host "Scheduled '$task' daily at $Time." -ForegroundColor Green
Write-Host "  Report: output\agent-radar\marketing_os_scan.md" -ForegroundColor DarkGray
Write-Host "  Remove: .\schedule_agent_radar.ps1 -Remove" -ForegroundColor DarkGray
