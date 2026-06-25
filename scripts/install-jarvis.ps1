# ============================================================
# Install the isair/jarvis local voice assistant
# Downloads the latest Windows release and extracts it into jarvis\
# ============================================================

param(
    [string]$BaseDir = "C:\Users\a.alirzayev\ramin-os"
)

$ErrorActionPreference = "Stop"

$jarvisDir = "$BaseDir\jarvis"
$tempDir   = "$BaseDir\.tmp"
$zipPath   = "$tempDir\jarvis-windows.zip"

foreach ($d in @($jarvisDir, $tempDir)) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

Write-Host "==> Jarvis install (isair/jarvis)" -ForegroundColor Cyan
Write-Host ""

# Resolve the latest release asset via the GitHub API
$apiUrl = "https://api.github.com/repos/isair/jarvis/releases/latest"
Write-Host "==> querying latest release ..." -ForegroundColor Yellow

try {
    $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ "User-Agent" = "ramin-os-installer" }
} catch {
    Write-Host "ERROR: could not reach the GitHub releases API." -ForegroundColor Red
    Write-Host "Manual fallback: download a Windows release from" -ForegroundColor Yellow
    Write-Host "  https://github.com/isair/jarvis/releases" -ForegroundColor Yellow
    Write-Host "and extract it into: $jarvisDir" -ForegroundColor Yellow
    exit 1
}

$asset = $release.assets | Where-Object { $_.name -match "win" -and $_.name -match "\.zip$" } | Select-Object -First 1
if (-not $asset) {
    Write-Host "WARNING: no Windows .zip asset found in the latest release ($($release.tag_name))." -ForegroundColor Yellow
    Write-Host "Download manually from: https://github.com/isair/jarvis/releases" -ForegroundColor Yellow
    exit 1
}

Write-Host "==> downloading $($asset.name) ($($release.tag_name)) ..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath

Write-Host "==> extracting into $jarvisDir ..." -ForegroundColor Yellow
Expand-Archive -Path $zipPath -DestinationPath $jarvisDir -Force

# Seed config from the committed example if the real config is missing
$configExample = "$jarvisDir\config.yaml.example"
$configFile    = "$jarvisDir\config.yaml"
if ((Test-Path $configExample) -and (-not (Test-Path $configFile))) {
    Copy-Item $configExample $configFile
    Write-Host "==> created config.yaml from config.yaml.example" -ForegroundColor Green
}

Write-Host ""
Write-Host "==> done. Jarvis installed at: $jarvisDir" -ForegroundColor Cyan
Write-Host "    Review config.yaml, then start Jarvis and say the wake word." -ForegroundColor DarkGray
