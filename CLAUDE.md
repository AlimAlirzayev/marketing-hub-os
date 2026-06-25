# Claude Code Entry Point

This root workspace is Ramin-OS. Claude Code work here must follow the same
operating charter as Codex and the rest of the agent system.

Read first:

1. `AGENTS.md`
2. `docs/RAMIN_OS_CONTEXT.md`
3. `SECURITY.md`
4. `services.json`
5. `claude-agents/CLAUDE.md` for Claude-specific subagent and MCP conventions

Important rule: do not treat `claude-agents/` as a separate product. It is the
Claude Code control plane inside the larger Ramin-OS ecosystem.

When the system shape changes, refresh:

```powershell
python scripts/system_context.py
```

