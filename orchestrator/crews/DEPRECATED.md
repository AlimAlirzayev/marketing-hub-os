# DEPRECATED — use `gateway/council.py`

These CrewAI crews are **unwired skeletons** and are superseded by the live
multi-agent layer.

## Why deprecated
- `crew.kickoff()` is never called (`jarvis_bridge.dispatch_from_jarvis` returns
  `crew_ready`, marked `TODO`). They never execute.
- They depend on **CrewAI**, which is deliberately not installed on this
  locked-down corporate machine (the whole gateway avoids langchain/crewai).
- They duplicate, less capably, what already works.

## What replaces it — `gateway/council.py`
A zero-budget, **subscriber-CLI AI Council**:
- consults **Codex + Claude Code + Gemini CLI** in parallel (no API keys),
- synthesizes one decision (Codex as chair),
- executes via the gateway, with `gateway/security.py` governance.

Toggle with `AI_COUNCIL_ENABLED` (on by default). This is the production
multi-agent path; it is wired into `gateway/executor.py`.

## Status
Files are **kept, not deleted** (they belong to earlier work and may seed a
CrewAI-free, council-pattern reimplementation later). Importing `orchestrator.crews`
emits a `DeprecationWarning`. Do not build new work on them — extend the council.
