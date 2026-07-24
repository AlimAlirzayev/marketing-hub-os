param(
    [ValidateSet("Install", "Status", "Uninstall")]
    [string]$Action = "Status"
)

# ASCII-only: Windows PowerShell 5.1 can misread non-ASCII script source.
$ErrorActionPreference = "Stop"
$TaskName = "Ramin-OS-Supervisor"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if ($Action -eq "Status") {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Output "not-installed"
        exit 1
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Output ("installed state={0} last={1} next={2}" -f
        $task.State, $info.LastRunTime, $info.NextRunTime)
    exit 0
}

if ($Action -eq "Uninstall") {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "uninstalled"
    } else {
        Write-Output "not-installed"
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Repo virtualenv Python is missing: $Python"
}

$taskAction = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "-m gateway.supervisor" `
    -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $taskAction `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Starts the owner-only Ramin-OS gateway supervisor at user logon." `
    -Force | Out-Null

Write-Output "installed"
