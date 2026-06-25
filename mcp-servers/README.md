# Xalq Insurance Digital OS - MCP Servers

Model Context Protocol servers that give Claude Code and the agents real-world
capabilities. These are wired into `claude-agents/.claude/settings.json` by
`scripts/setup-mcp.ps1`.

## Servers in use

| Server        | Command                                          | Purpose                                        |
|---------------|--------------------------------------------------|------------------------------------------------|
| `n8n-mcp`     | `npx -y n8n-mcp`                                 | Create and run n8n workflows from the agent    |
| `filesystem`  | `npx -y @modelcontextprotocol/server-filesystem` | Read/write inside the `ramin-os` project root  |
| `memory`      | `npx -y @modelcontextprotocol/server-memory`     | Persistent knowledge graph across sessions     |
| `browser-use` | `uvx browser-use-mcp`                            | Drive a real browser for scraping and web tasks|
| `qdrant`      | `npx -y @qdrant/mcp-server-qdrant`               | Vector DB access for RAG over documents        |

## Setup

```powershell
..\scripts\setup-mcp.ps1
```

This writes `claude-agents/.claude/settings.json` with an `mcpServers` block.
After running it:

1. Open n8n at http://localhost:5678 -> Settings -> API
2. Create a new API key
3. Paste it into `settings.json` over `REPLACE_WITH_N8N_API_KEY`

## Prerequisites

- Node.js (provides `npx`) - for n8n-mcp, filesystem, memory, qdrant
- `uv` (provides `uvx`) - for browser-use
- Docker services running (`docker compose up -d`) - so n8n and Qdrant are reachable

## Adding a custom MCP server

1. Add an entry to the `mcpServers` block in `setup-mcp.ps1` (the
   PowerShell hashtable around lines 12-45).
2. Re-run `setup-mcp.ps1` to regenerate `settings.json`.
3. If the server has its own code, place it in a subfolder here, e.g.
   `mcp-servers/my-custom-server/`.

This folder is reserved for custom or self-hosted MCP server code; the servers
in the table above are installed on demand via `npx` / `uvx` and need no files
here.
