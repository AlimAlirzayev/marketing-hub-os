# ============================================================
# Install portable Node.js + FFmpeg for Xalq Insurance Digital OS Video Studio
#
# winget is blocked by corporate Group Policy on this machine, so the tools
# are downloaded as zips and extracted into video-studio/tools/ - no admin
# rights, no PATH changes. paths.py locates them from there.
#
# Idempotent: re-running skips anything already installed.
# ============================================================

param(
    [string]$NodeVersion = "v24.15.0"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "==> Video Studio tools install" -ForegroundColor Cyan
Write-Host ""

$studio = Join-Path $PSScriptRoot "..\video-studio" | Resolve-Path
$tools = Join-Path $studio "tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null

# --- Node.js (portable zip) ---------------------------------------------
$nodeDir = Join-Path $tools "node-$NodeVersion-win-x64"
if (Test-Path (Join-Path $nodeDir "node.exe")) {
    Write-Host "==> Node.js already present - skipping" -ForegroundColor DarkGray
} else {
    Write-Host "==> downloading Node.js $NodeVersion ..." -ForegroundColor Yellow
    $nodeZip = Join-Path $tools "node.zip"
    $nodeUrl = "https://nodejs.org/dist/$NodeVersion/node-$NodeVersion-win-x64.zip"
    Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeZip -UseBasicParsing -TimeoutSec 300
    Expand-Archive -Path $nodeZip -DestinationPath $tools -Force
    Remove-Item $nodeZip
    Write-Host "    Node.js -> $nodeDir" -ForegroundColor Green
}

# --- FFmpeg (portable zip) ----------------------------------------------
$ffmpegDir = Get-ChildItem -Path $tools -Directory -Filter "ffmpeg-*" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($ffmpegDir -and (Test-Path (Join-Path $ffmpegDir.FullName "bin\ffmpeg.exe"))) {
    Write-Host "==> FFmpeg already present - skipping" -ForegroundColor DarkGray
} else {
    Write-Host "==> downloading FFmpeg (gyan.dev essentials) ..." -ForegroundColor Yellow
    $ffZip = Join-Path $tools "ffmpeg.zip"
    $ffUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    Invoke-WebRequest -Uri $ffUrl -OutFile $ffZip -UseBasicParsing -TimeoutSec 300
    Expand-Archive -Path $ffZip -DestinationPath $tools -Force
    Remove-Item $ffZip
    Write-Host "    FFmpeg installed under $tools" -ForegroundColor Green
}

# --- Verify --------------------------------------------------------------
Write-Host ""
Write-Host "==> verifying ..." -ForegroundColor Cyan
& (Join-Path $nodeDir "node.exe") --version
$ffmpegBin = Get-ChildItem -Path $tools -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
& $ffmpegBin.FullName -version | Select-Object -First 1

Write-Host ""
Write-Host "==> done. Next:" -ForegroundColor Green
Write-Host "    pip install -r video-studio\requirements.txt" -ForegroundColor Yellow
