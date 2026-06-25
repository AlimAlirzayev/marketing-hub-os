# ============================================================
# MCP Server setup (for Claude Code)
# n8n-mcp + browser-use + filesystem + memory + qdrant
# ============================================================

param(
    [string]$BaseDir = "C:\Users\a.alirzayev\ramin-os"
)

$mcpConfig = "$BaseDir\claude-agents\.claude\settings.json"
$mcpConfigDir = Split-Path $mcpConfig -Parent
if (-not (Test-Path $mcpConfigDir)) {
    New-Item -ItemType Directory -Path $mcpConfigDir -Force | Out-Null
}

# Pull the ElevenLabs key from .env so a regen does not wipe a real key.
$elevenKey = "REPLACE_WITH_ELEVENLABS_API_KEY"
$envFile = "$BaseDir\.env"
if (Test-Path $envFile) {
    $m = Select-String -Path $envFile -Pattern '^\s*ELEVENLABS_API_KEY\s*=\s*(.+)$' | Select-Object -First 1
    if ($m -and $m.Matches[0].Groups[1].Value.Trim()) {
        $elevenKey = $m.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
    }
}

$config = @{
    mcpServers = @{
        "n8n-mcp" = @{
            command = "npx"
            args    = @("-y", "n8n-mcp")
            env     = @{
                N8N_API_URL = "http://localhost:5678/api/v1"
                N8N_API_KEY = "REPLACE_WITH_N8N_API_KEY"
            }
        }
        "filesystem" = @{
            command = "npx"
            args    = @("-y", "@modelcontextprotocol/server-filesystem", "$BaseDir")
        }
        "memory" = @{
            command = "npx"
            args    = @("-y", "@modelcontextprotocol/server-memory")
        }
        "browser-use" = @{
            command = "uvx"
            args    = @("browser-use-mcp")
        }
        "elevenlabs" = @{
            command = "uvx"
            args    = @("elevenlabs-mcp")
            env     = @{
                ELEVENLABS_API_KEY       = $elevenKey
                ELEVENLABS_MCP_BASE_PATH = "$BaseDir\audio-studio\output"
            }
        }
        "qdrant" = @{
            command = "npx"
            args    = @("-y", "@qdrant/mcp-server-qdrant")
            env     = @{
                QDRANT_URL = "http://localhost:6333"
            }
        }
    }
} | ConvertTo-Json -Depth 10

Set-Content -Path $mcpConfig -Value $config -Encoding utf8
Write-Host "==> MCP config written: $mcpConfig" -ForegroundColor Green
Write-Host ""
Write-Host "NOTE: to obtain the n8n API key:" -ForegroundColor Yellow
Write-Host "  1. http://localhost:5678 -> Settings -> API" -ForegroundColor Yellow
Write-Host "  2. Create a new key" -ForegroundColor Yellow
Write-Host "  3. Paste it in settings.json over REPLACE_WITH_N8N_API_KEY" -ForegroundColor Yellow
Write-Host ""
if ($elevenKey -eq "REPLACE_WITH_ELEVENLABS_API_KEY") {
    Write-Host "NOTE: ElevenLabs (music + sfx + tts + voice clone) is registered but keyless:" -ForegroundColor Yellow
    Write-Host "  1. Free key (10k credits/mo): https://elevenlabs.io/app/settings/api-keys" -ForegroundColor Yellow
    Write-Host "  2. Add ELEVENLABS_API_KEY=... to .env, then re-run this script." -ForegroundColor Yellow
} else {
    Write-Host "==> ElevenLabs key loaded from .env into the MCP config." -ForegroundColor Green
}
