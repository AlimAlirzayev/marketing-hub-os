# Repo-local setup for Notion Workers. This installs the Notion CLI into
# .tools/notion-cli and installs the Ramin-OS worker dependencies.

param(
    [string]$BaseDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$NodeDir = $null
$PortableNode = Get-ChildItem -Path (Join-Path $BaseDir "video-studio\tools") -Recurse -Filter "node.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1

if ($PortableNode) {
    $NodeDir = Split-Path -Parent $PortableNode.FullName
} elseif (Get-Command node -ErrorAction SilentlyContinue) {
    $NodeDir = Split-Path -Parent (Get-Command node).Source
} else {
    throw "Node.js 22+ is required. Run .\scripts\install-video-tools.ps1 or install Node.js before this setup."
}

$env:Path = "$NodeDir;$env:Path"
$Npm = Join-Path $NodeDir "npm.cmd"
if (-not (Test-Path $Npm)) {
    $Npm = "npm"
}

$CliPrefix = Join-Path $BaseDir ".tools\notion-cli"
Write-Host "==> Installing Notion CLI into $CliPrefix" -ForegroundColor Green
& $Npm install --global ntn --prefix $CliPrefix

$WorkerDir = Join-Path $BaseDir "notion-workers\ramin-os-agent-tools"
Write-Host "==> Installing worker dependencies in $WorkerDir" -ForegroundColor Green
Push-Location $WorkerDir
try {
    & $Npm install
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "==> Notion Workers local setup complete." -ForegroundColor Green
Write-Host "Use .\scripts\notion-cli.ps1 --version to verify the CLI." -ForegroundColor DarkGray
Write-Host "Login, deploy, env push/pull, OAuth, and webhook handling require a human checkpoint." -ForegroundColor Yellow
