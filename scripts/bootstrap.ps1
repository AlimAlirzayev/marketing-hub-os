# ============================================================
# Xalq Insurance Digital OS - master bootstrap
# Runs all install steps in order. Each step can be skipped.
# This does NOT start Docker services - run "docker compose up -d" yourself.
# ============================================================

param(
    [string]$BaseDir = "C:\Users\a.alirzayev\ramin-os",
    [switch]$SkipTemplates,
    [switch]$SkipAgents,
    [switch]$SkipOllama,
    [switch]$SkipJarvis,
    [switch]$SkipMcp
)

$ErrorActionPreference = "Stop"
$scripts = "$BaseDir\scripts"

function Invoke-Step {
    param([string]$Name, [string]$Script, [bool]$Skip)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    if ($Skip) {
        Write-Host "  SKIPPED: $Name" -ForegroundColor DarkGray
        return
    }
    Write-Host "  STEP: $Name" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    & $Script -BaseDir $BaseDir
}

Write-Host "==> Xalq Insurance Digital OS bootstrap starting" -ForegroundColor Green

Invoke-Step "Import n8n workflow templates" "$scripts\import-templates.ps1" $SkipTemplates.IsPresent
Invoke-Step "Install Claude Code agents and skills" "$scripts\install-agents.ps1" $SkipAgents.IsPresent
Invoke-Step "Configure MCP servers" "$scripts\setup-mcp.ps1" $SkipMcp.IsPresent

# install-ollama-models.ps1 takes no -BaseDir parameter
if (-not $SkipOllama) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  STEP: Pull Ollama models" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    & "$scripts\install-ollama-models.ps1"
} else {
    Write-Host ""
    Write-Host "  SKIPPED: Pull Ollama models" -ForegroundColor DarkGray
}

Invoke-Step "Install Jarvis voice assistant" "$scripts\install-jarvis.ps1" $SkipJarvis.IsPresent

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  BOOTSTRAP COMPLETE - remaining manual steps:" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  1. Copy .env.example to .env and fill in your API keys" -ForegroundColor White
Write-Host "  2. docker compose up -d" -ForegroundColor White
Write-Host "  3. Open n8n http://localhost:5678 and create an API key" -ForegroundColor White
Write-Host "  4. Paste the n8n API key into claude-agents\.claude\settings.json" -ForegroundColor White
Write-Host "  5. cd orchestrator; python -m venv venv; pip install -r requirements.txt" -ForegroundColor White
