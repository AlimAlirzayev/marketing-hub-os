# Notion Workers

Ramin-OS Notion Workers live here. These are Notion-hosted TypeScript projects,
not local services and not MCP servers.

Current project:

- `ramin-os-agent-tools`: read-only/draft-only Custom Agent tools for action
  screening and Ramin-OS handoff preparation.

Start from the system docs:

- `docs/NOTION_WORKERS.md`
- `gateway/notion_workers.py`
- `config/agent_permissions.json` (`notion_workers`)

Credentialed actions such as login, deploy, worker env management, OAuth, real
sync triggers, and webhook URL handling require a human checkpoint.
