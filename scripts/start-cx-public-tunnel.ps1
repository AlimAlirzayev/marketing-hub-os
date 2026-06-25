param(
    [string]$LocalUrl = "http://127.0.0.1:8810",
    [string]$EnvPath = ".env",
    [switch]$NoEnvUpdate
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$tools = Join-Path $repo ".tools"
$cloudflared = Join-Path $tools "cloudflared.exe"
$logDir = Join-Path $repo "data\logs"
$log = Join-Path $logDir "cloudflared-cx.log"
$errLog = Join-Path $logDir "cloudflared-cx.err.log"
$pidFile = Join-Path $logDir "cloudflared-cx.pid"

New-Item -ItemType Directory -Force -Path $tools, $logDir | Out-Null

if (-not (Test-Path $cloudflared)) {
    $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Write-Host "cloudflared download edilir..."
    Invoke-WebRequest -Uri $url -OutFile $cloudflared
}

if (Test-Path $pidFile) {
    $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($oldPid) {
        $old = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($old) {
            Write-Host "Movcud tunnel isleyir: PID $oldPid"
            if (Test-Path $log) {
                $existing = Select-String -Path $log -Pattern "https://[-a-zA-Z0-9.]+\.trycloudflare\.com" -AllMatches |
                    ForEach-Object { $_.Matches.Value } |
                    Select-Object -Last 1
                if ($existing) {
                    Write-Host "Public URL: $existing"
                    exit 0
                }
            }
        }
    }
}

Remove-Item -Force $log, $errLog -ErrorAction SilentlyContinue

$args = @("tunnel", "--url", $LocalUrl, "--no-autoupdate", "--protocol", "http2")
$proc = Start-Process -FilePath $cloudflared -ArgumentList $args -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $errLog -PassThru
$proc.Id | Set-Content -Path $pidFile

Write-Host "Tunnel basladildi: PID $($proc.Id)"

$deadline = (Get-Date).AddSeconds(45)
$publicUrl = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $logPaths = @($log, $errLog) | Where-Object { Test-Path $_ }
    if ($logPaths) {
        $publicUrl = Select-String -Path $logPaths -Pattern "https://[-a-zA-Z0-9.]+\.trycloudflare\.com" -AllMatches |
            ForEach-Object { $_.Matches.Value } |
            Select-Object -Last 1
        if ($publicUrl) {
            break
        }
    }
    if ($proc.HasExited) {
        break
    }
}

if (-not $publicUrl) {
    Write-Error "Public URL tapilmadi. Log: $log"
    if (Test-Path $log) {
        Get-Content $log -Tail 40
    }
    if (Test-Path $errLog) {
        Get-Content $errLog -Tail 40
    }
    exit 1
}

if (-not $NoEnvUpdate) {
    $targetEnv = Join-Path $repo $EnvPath
    if (-not (Test-Path $targetEnv)) {
        New-Item -ItemType File -Path $targetEnv | Out-Null
    }
    $lines = Get-Content $targetEnv
    $found = $false
    $lines = $lines | ForEach-Object {
        if ($_ -match "^\s*CX_PUBLIC_BASE_URL\s*=") {
            $found = $true
            "CX_PUBLIC_BASE_URL=$publicUrl"
        } else {
            $_
        }
    }
    if (-not $found) {
        $lines += "CX_PUBLIC_BASE_URL=$publicUrl"
    }
    $lines | Set-Content -Path $targetEnv -Encoding UTF8
}

Write-Host "Public URL: $publicUrl"
Write-Host "Meta callback: $publicUrl/api/webhooks/meta"
Write-Host "Chatplace callback: $publicUrl/api/webhooks/chatplace"
