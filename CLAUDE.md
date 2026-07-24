# Claude Code Entry Point

This root workspace is Ramin-OS. Claude Code work here must follow the same
operating charter as Codex and the rest of the agent system.

Read first:

1. `AGENTS.md`
2. `docs/RAMIN_OS_CONTEXT.md`
3. `SECURITY.md`
4. `services.json`
5. `claude-agents/CLAUDE.md` for Claude-specific subagent and MCP conventions
6. `docs/CONTEXT7_GROUNDING.md` for read-only documentation grounding rules
7. `config/agent_permissions.json` before adding or expanding agents/tools

Important rule: do not treat `claude-agents/` as a separate product. It is the
Claude Code control plane inside the larger Ramin-OS ecosystem.

When the system shape changes, refresh:

```powershell
python scripts/system_context.py
```

## Mandatory User-Visible Delivery Gate

For every construction session, `docs/USER_VISIBLE_DELIVERY_STANDARD.md` is a
completion gate, not optional guidance.

- Plan the operator journey and the UX/UI lane with the engine work.
- Extend the owning module and the unified Hub; do not create a hidden tool or
  a second front door.
- Show real input, truthful progress and errors, the actual result or preview,
  and the next safe action.
- Exercise the finished journey from the user side and hand off the exact Hub
  path or verified URL with visible proof.
- Never call a build complete when its applicable UI, Hub discovery, or
  user-side validation is missing. Report it as **partial** and name the exact
  blocker or follow-up.

The same gate applies when Claude delegates work to subagents or specialist
teams. The lead session owns integration and final user-visible acceptance.
