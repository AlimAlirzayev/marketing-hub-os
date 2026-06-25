# Launch OpenCode wired to RAMIN OS free providers - zero manual setup.
# Usage:  .\scripts\opencode.ps1 [opencode args...]
#   .\scripts\opencode.ps1                      # interactive TUI
#   .\scripts\opencode.ps1 run "task" -m google/gemini-2.5-flash
# Prepends the portable Node, loads free keys from .env, maps the Gemini env var.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$nodeDir = Join-Path $repo "video-studio\tools\node-v24.15.0-win-x64"
if (-not (Test-Path "$nodeDir\opencode.cmd")) {
  Write-Error "OpenCode not installed in portable Node. Run: & '$nodeDir\npm.cmd' install -g opencode-ai"
  exit 1
}
$env:Path = "$nodeDir;$env:Path"

# Load the free provider keys from .env into this process only.
$envFile = Join-Path $repo ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*(GROQ_API_KEY|GEMINI_API_KEY|OPENROUTER_API_KEY|DEEPSEEK_API_KEY|CEREBRAS_API_KEY)\s*=\s*(.+)$') {
      Set-Item -Path "Env:$($matches[1])" -Value $matches[2].Trim()
    }
  }
}
# OpenCode's Google provider reads GOOGLE_GENERATIVE_AI_API_KEY.
if ($env:GEMINI_API_KEY -and -not $env:GOOGLE_GENERATIVE_AI_API_KEY) {
  $env:GOOGLE_GENERATIVE_AI_API_KEY = $env:GEMINI_API_KEY
}

& "$nodeDir\opencode.cmd" @args
exit $LASTEXITCODE
