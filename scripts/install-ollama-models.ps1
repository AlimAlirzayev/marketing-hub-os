# ============================================================
# Pull local Ollama models for Xalq Insurance Digital OS
#   gemma3:4b   -> Jarvis local brain (fast, low RAM)
#   qwen2.5:7b  -> heavier local reasoning fallback
# ============================================================

param(
    [string[]]$Models = @("gemma3:4b", "qwen2.5:7b")
)

$ErrorActionPreference = "Stop"

Write-Host "==> Ollama model install" -ForegroundColor Cyan
Write-Host ""

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "ERROR: 'ollama' not found on PATH." -ForegroundColor Red
    Write-Host "Install it first: https://ollama.com/download/windows" -ForegroundColor Yellow
    exit 1
}

foreach ($m in $Models) {
    Write-Host "==> pulling $m ..." -ForegroundColor Yellow
    ollama pull $m
}

Write-Host ""
Write-Host "==> installed models:" -ForegroundColor Green
ollama list

Write-Host ""
Write-Host "==> done. Ollama API: http://localhost:11434" -ForegroundColor Cyan
