# SHARED CONTEXT — read this first

This file is the **shared, git-tracked memory** that travels between every machine
(work PC, MacBook, Hetzner server) and channel. Any session — a chat, the autonomous
graph, Telegram — should read it first so nobody starts with amnesia. Keep it short
and current. **Never put secrets/keys here** (it is committed).

## What this system is
A self-hosted, zero-budget **marketing OS**. One codebase serves two brands via the
`BRAND` env var (`brand.py`): `xalq` = Xalq Sigorta (corporate), `global` = Marketing
Hub (generic). Same code everywhere; only `BRAND` + `.env` differ per machine.

## The cross-machine bridge + the engine/data boundary
Private GitHub repo `git@github.com:AlimAlirzayev/marketing-hub-os.git`. Sync is
**automatic** via one brain, `scripts/sync_engine.py` (safe two-way: ff-pull +
push-committed-only). It fires on its own: SessionStart pulls, SessionEnd pushes,
the launcher pulls at boot, `PULL.bat` is a one-click, and Telegram `/update`
pulls the VPS on command. You never have to say "pull first" — it's already done.

**Hard boundary (see `docs/SYNC.md`):** only the ENGINE travels (code, tools,
capabilities, engineering decisions in `memory/`). PRIVATE business data never
crosses — `.env`, customer data, brand content, strategy/conversation context live
in git-ignored `data/private_context/` (+ `.env`, `data/`). `shared_memory.remember()`
is **private by default**; pass `scope="shared"` only for engine/capability facts.
Move a single improvement without taking everything via `git cherry-pick`.

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
