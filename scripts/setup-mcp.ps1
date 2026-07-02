# ============================================================
# MCP Server setup (for Claude Code)
# n8n-mcp + browser-use + filesystem + memory + qdrant + flora
# ============================================================

param(
    [string]$BaseDir = "C:\Users\a.alirzayev\ramin-os"
)

$mcpConfig = "$BaseDir\claude-agents\.claude\settings.json"
$mcpConfigDir = Split-Path $mcpConfig -Parent
if (-not (Test-Path $mcpConfigDir)) {
    New-Item -ItemType Directory -Path $mcpConfigDir -Force | Out-Null
}

$npxCommand = "npx"
$portableNpx = Get-ChildItem -Path "$BaseDir\video-studio\tools" -Recurse -Filter "npx.cmd" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if ($portableNpx) {
    $npxCommand = $portableNpx.FullName
}

$config = @{
    mcpServers = @{
        "context7" = @{
            command = $npxCommand
            args    = @("-y", "@upstash/context7-mcp")
        }
        "n8n-mcp" = @{
            command = $npxCommand
            args    = @("-y", "n8n-mcp")
            env     = @{
                N8N_API_URL = "http://localhost:5678/api/v1"
                N8N_API_KEY = "REPLACE_WITH_N8N_API_KEY"
            }
        }
        "filesystem" = @{
            command = $npxCommand
            args    = @("-y", "@modelcontextprotocol/server-filesystem", "$BaseDir")
        }
        "memory" = @{
            command = $npxCommand
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
                ELEVENLABS_MCP_BASE_PATH = "$BaseDir\audio-studio\output"
            }
        }
        "qdrant" = @{
            command = $npxCommand
            args    = @("-y", "@qdrant/mcp-server-qdrant")
            env     = @{
                QDRANT_URL = "http://localhost:6333"
            }
        }
        "flora" = @{
            command = $npxCommand
            args    = @("-y", "mcp-remote", "https://agents.flora.ai/mcp")
        }
    }
} | ConvertTo-Json -Depth 10

Set-Content -Path $mcpConfig -Value $config -Encoding utf8
Write-Host "==> MCP config written: $mcpConfig" -ForegroundColor Green
Write-Host ""
if ($portableNpx) {
    Write-Host "==> Using portable Node/npm for npx: $npxCommand" -ForegroundColor Green
} else {
    Write-Host "NOTE: Portable npx was not found; MCP settings will use npx from PATH." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "NOTE: Context7 is registered as a read-only docs grounding MCP." -ForegroundColor Green
Write-Host "  For higher limits, configure Context7 authentication at user/MCP-client level;" -ForegroundColor DarkGray
Write-Host "  do not paste API keys into tracked files." -ForegroundColor DarkGray
Write-Host ""
Write-Host "NOTE: to obtain the n8n API key:" -ForegroundColor Yellow
Write-Host "  1. http://localhost:5678 -> Settings -> API" -ForegroundColor Yellow
Write-Host "  2. Create a new key" -ForegroundColor Yellow
Write-Host "  3. Paste it in settings.json over REPLACE_WITH_N8N_API_KEY" -ForegroundColor Yellow
Write-Host ""
Write-Host "NOTE: ElevenLabs MCP is registered without writing the API key into settings.json." -ForegroundColor Yellow
Write-Host "  Set ELEVENLABS_API_KEY in the process environment before launching Claude if needed." -ForegroundColor Yellow
Write-Host ""
Write-Host "NOTE: FLORA MCP is registered through the official remote endpoint." -ForegroundColor Yellow
Write-Host "  First use opens OAuth; do not paste FLORA API keys into tracked files." -ForegroundColor Yellow
Write-Host "  Ask for a cost check before large/billed generation batches." -ForegroundColor Yellow
