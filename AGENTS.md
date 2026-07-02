# Ramin-OS Operating Charter For AI Agents

This workspace is Ramin-OS: the unified Xalq Insurance Digital / Marketing OS.
Every Codex, Claude Code, Gemini, script, service, and generated artifact must
serve this one system.

## Always Start Here

Before planning broad work or editing shared behavior, read:

1. `docs/RAMIN_OS_CONTEXT.md`
2. `services.json`
3. `SECURITY.md`
4. The README or source files for the module you are touching

Refresh the context whenever the system shape changes:

```powershell
python scripts/system_context.py
```

## Non-Negotiables

- Security is the highest law.
- Never read, print, copy, upload, or summarize `.env`, `.env.bak`, API keys,
  tokens, cookies, or credentials.
- `services.json` is the single source of truth for ports, services, and hub
  visibility.
- Do not create disconnected side tools when an existing Ramin-OS module can be
  reinforced.
- Do not undo work done by another agent unless you understand why it exists and
  the user explicitly wants it changed.
- Risky actions need checkpoints: posting, sending, spending, deleting,
  credentialed browsing, production writes, and private-network access.
- Use Context7 as a read-only documentation grounding layer for external
  library/API work. Never send secrets, customer data, claims, policies, or
  private strategy to documentation tools.
- Check `config/agent_permissions.json` before adding or expanding an agent,
  MCP server, workflow, or automation capability.

## How To Work

1. Build a current map of the system first.
2. Choose the smallest useful improvement that strengthens the whole OS.
3. Prefer existing patterns: gateway, brain, services registry, hub, audit,
   Agent Radar, Context7 docs grounding, permission manifests, module READMEs,
   and tests.
4. Make scoped edits and run meaningful checks.
5. Update docs/context when the system gains a new capability.
6. Capture reusable lessons through the Brain workflow when the lesson should
   survive the current session.

## Current Strategic Direction

- The hub and `services.json` are the operational front door.
- The gateway and AI Council are the autonomous execution layer.
- The Brain is institutional memory.
- Agent Radar is the governance layer for outside agents and future workflows.
- CX, Ads, GA4, CAPI, Influencer Hunter, Price Hunter, Creative/Atelier, Copy,
  Publisher, Audio, and Video are domain modules that should become more
  integrated over time, not more fragmented.
- How the agents coordinate — which one plans, executes, reviews, and where
  results and memory land — is mapped in `docs/ORCHESTRATION.md`. Read it before
  adding or rewiring any agent so new work joins the council/router, not a new
  silo.
