# Ramin-OS Operating Charter For AI Agents

This workspace is Ramin-OS: the unified Xalq Insurance Digital / Marketing OS.
Every Codex, Claude Code, Gemini, script, service, and generated artifact must
serve this one system.

## Always Start Here

**Step 0 — equalize with the twin.** Two twin systems (corporate + fleet) share
this engine via GitHub. Your FIRST action in any session — Codex, Claude, Gemini,
or any other agent — is to pull the newest engine so you never work on stale code:

```bash
python scripts/sync_engine.py --pull-only
```

(Claude Code does this automatically via the SessionStart hook; every other agent
runs it manually. It is safe: ff-only, never touches local work, exits quietly.)

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
- A build is not complete until its useful result is visible and operable from
  the user side. Follow `docs/USER_VISIBLE_DELIVERY_STANDARD.md` for every new
  capability, invention, workflow, report, dashboard, and material improvement.
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
5. Update docs/context when the system gains a new capability. **Ship rule:** a
   new lane/rail/tool ships WITH its self-description in the same commit —
   update `_SELF_FACTS` (gateway/executor.py) and `services.json` capabilities.
   The chat brain answers from that card, not from the repo; skip this and it
   keeps describing the old system (observed 2026-07-17: the bot proposed
   building a multi-step planner hours after one had shipped).
6. Capture reusable lessons through the Brain workflow when the lesson should
   survive the current session.

## User-Visible Delivery Gate

Every construction session owns the user experience as well as the engine. UI
is a parallel delivery lane, not a later cleanup task.

1. Before building, identify the operator journey: where the capability belongs
   in the existing Hub/module, how the user starts it, what progress is shown,
   where the result appears, and what the next valid action is.
2. When parallel agents or a specialist team are available, assign an explicit
   product/UX/frontend lane alongside backend, integration, security, and test
   work. The lanes review one another and converge on one integrated product.
3. Extend the owning module and the unified Hub information architecture. Do
   not create an isolated dashboard, hidden script, mystery port, or second
   front door merely because it is faster.
4. The user-facing surface must expose real inputs, honest status/progress,
   useful errors, the actual result or artifact preview, relevant history, and
   the next valid action. Never substitute demo numbers or a log dump for the
   real operator experience; label unavailable data and provide a real input or
   connection path.
5. Match the shared visual language and interaction patterns. Check responsive
   layout, clear Azerbaijani operator copy where appropriate, accessibility,
   empty/loading/error/success states, and safe confirmation steps for risky
   actions.
6. Validate the complete journey from the user side, not only through unit
   tests or API calls. Start or safely restart the relevant local service, use
   the interface with representative input, and verify that the visible result
   matches the underlying output.
7. At handoff, open the finished surface or artifact for the operator whenever
   the environment permits. Otherwise provide a verified exact Hub path/local
   URL plus a screenshot or preview. State what was built, where it lives, how
   to use it, what was actually tested, and any remaining boundary.

Pure infrastructure, security, or maintenance work does not need a new screen,
but its operator-relevant state and effect must be visible in an existing Hub
health, audit, activity, settings, or owning-module surface. Research-only work
must land in the relevant visible report/library workflow when the result is
meant for recurring use.

If the interface, Hub placement, discoverability, or user-side validation is
missing, report the work as **partial**, never **complete**. A backend-only
delivery is allowed only when the user explicitly scopes the task that way or a
documented blocker makes the UI impossible; record the UI follow-up and blocker
before ending the session. The full acceptance checklist is in
`docs/USER_VISIBLE_DELIVERY_STANDARD.md`.

## Checks (how to know the system is green)

```powershell
python run_tests.py       # ALL suites — the only command that runs everything
python audit_services.py  # registry (services.json) vs reality — no drift
```

`run_tests.py` runs each suite in its **own interpreter**, and that is not
optional. This repo deliberately holds standalone tools rooted in their own
folders, so it contains eight different `config.py` modules, a
`meta-capi/gateway.py` that shadows the root `gateway/` package, and a
`seo/http.py` that shadows the Python stdlib `http`. Put them in one process and
they overwrite each other in `sys.modules` — you get failures like
`module 'gateway' has no attribute '_client_ip'` on code that is perfectly fine.

So: **a red suite here is far more often a shadowing artifact than a real bug.**
Never "fix" the sub-projects to make a single flat `pytest` run work — process
isolation is the design. A bare `pytest` at the root is scoped by `pytest.ini` to
the collision-free root suite only; anything wider must go through `run_tests.py`.

Baseline: 6 suites, 504 tests green, ~30s.

## Current Strategic Direction

- The hub and `services.json` are the operational front door.
- Product capabilities ship as one vertical slice: engine + governance +
  unified UX/UI + Hub discovery + user-side proof. Hidden capability is
  unfinished capability.
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
