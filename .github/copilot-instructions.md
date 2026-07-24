# Ramin-OS Copilot Instructions

Read and follow `AGENTS.md`, `SECURITY.md`, `services.json`, and
`docs/RAMIN_OS_CONTEXT.md` before broad work.

Refresh `python scripts/builder_context.py --print` first so Copilot works from
the same live state, shared decisions, and curated memory indexes as Claude and
Codex. Current code and shared decisions outrank agent-private memory.

Every construction session is governed by
`docs/USER_VISIBLE_DELIVERY_STANDARD.md`. Build a vertical product slice:
engine, governance, unified UX/UI, Hub discovery, real result preview,
user-side validation, and exact operator handoff. Do not call backend-only work
complete when an applicable interface or visible proof is missing; report it
as **partial** with the blocker.
