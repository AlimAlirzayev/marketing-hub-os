# Builder Context Bridge

## Purpose

Codex, Claude Code, Gemini, OpenCode, Copilot, the gateway, and specialist
agents are entry points into one Ramin-OS—not independent systems. The Builder
Context Bridge gives every construction session the same cold-start view of
current rules, live state, shared decisions, and curated memory indexes.

## How It Works

Run:

```powershell
python scripts/builder_context.py --print
```

The script reads:

- the masked live `gateway.sense.pulse()` state;
- recent shared decisions from `memory/decisions.jsonl`;
- Claude Code's local curated project `memory/MEMORY.md`, when present;
- Codex's local curated `memory_summary.md`, when present.

It writes a machine-local, git-ignored card to `data/builder_context.md`.
Claude Code receives the same card automatically through its project
`SessionStart` hook. Repo entry instructions require other builders to refresh
it after the normal engine pull.

## Authority and Safety

The bridge is read-only toward agent-owned memories. It never merges, edits, or
publishes their private stores. Repository code, `services.json`, current
runtime state, and shared decisions outrank memory excerpts, which may be stale.

The bridge does not read `.env`, credential stores, raw transcripts, customer
records, claims, policies, or payment data. Common secret shapes are redacted
defensively before the local card is written or printed.

Durable decisions still belong in the existing shared Brain workflow and
`memory/decisions.jsonl`. This bridge removes cold-start asymmetry without
creating another memory silo.
