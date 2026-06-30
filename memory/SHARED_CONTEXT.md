# SHARED CONTEXT — read this first

This file is the **shared, git-tracked memory** that travels between every machine
(work PC, MacBook, Hetzner server) and channel. Any session — a chat, the autonomous
graph, Telegram — should read it first so nobody starts with amnesia. Keep it short
and current. **Never put secrets/keys here** (it is committed).

## What this system is
A self-hosted, zero-budget **marketing OS**. One codebase serves two brands via the
`BRAND` env var (`brand.py`): `xalq` = Xalq Sigorta (corporate), `global` = Marketing
Hub (generic). Same code everywhere; only `BRAND` + `.env` differ per machine.

## The cross-machine bridge
Private GitHub repo `git@github.com:AlimAlirzayev/marketing-hub-os.git`. Workflow:
commit + push on one machine → `git pull` on another. `.env` and heavy media are
git-ignored and never travel; recreate `.env` per machine. The two deployments are
independent lines; share a specific improvement with `git cherry-pick`, not auto-sync.

## Architecture (the spine)
- **Model gateway:** `llm_router.py` (LiteLLM) — free-first cascade + fallback + usage
  log. Every model call goes through it. Free models (Gemini/Groq/…), not premium.
- **Autonomous spine:** `orchestrator/graph.py` (LangGraph) — `intake → plan →
  [risk gate] → (risky) human checkpoint → execute → remember`, durable checkpointer
  + `interrupt()` for risky-action approval. Built on llm_router (free brain).
- **Working memory:** `brain/` (per-machine, richer recall/reflect).
- **Shared memory (this):** `shared_memory.py` + `memory/` (travels via git).
- **Council:** `gateway/council.py` (Codex+Claude+Gemini; OpenCode only adds when it
  brings a distinct free model). Map: `docs/ORCHESTRATION.md`.

## Direction (the why)
The system must stand on its own: **Claude Code = BUILDER** (premium, occasional);
**the system = OPERATOR** (always-on, free LLMs), reachable through its OWN interfaces.
The business must not stop when a Claude Code session's tokens run out.

## Roadmap
1. **Shared traveling memory** ← this layer (foundation).
2. **Admin control-center dashboard** driving the free brain.
3. **Upgrade Telegram** to a first-class agent — all wired to the same gateway + memory.

## Non-negotiables
Security is the highest law: never commit `.env`/keys/PII. Risky actions
(post/send/pay/delete/call) require a human checkpoint. Don't fragment — reinforce
existing modules (`AGENTS.md`).
