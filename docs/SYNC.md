# Sync — share the engine, keep the data private

Two systems run this codebase: the **corporate** build (`BRAND=xalq`) and the
**personal/global** build (`BRAND=global`). They must share the *engine* and never
share the *business data*. This file is the contract.

## The boundary

| SHARED — travels via git (push/pull) | PRIVATE — git-ignored, never crosses |
| --- | --- |
| Code, tools, features, capabilities | `.env`, API keys |
| Engineering decisions (`memory/`) | Customer data |
| Brand **mechanism** (`brand.py`) | Brand **content** (each system's own `brand_kit`)¹ |
| Capability docs | Business/strategy decisions + conversation context (`data/private_context/`) |

So your personal system's customer talks, brand assets, and business decisions do
**not** reflect into the work system. Only the system's power — new tools, features,
fixes, up-to-date engineering — flows between them.

Memory enforces this in code: `shared_memory.remember()` writes **private by
default**; you must pass `scope="shared"` to put something in the traveling layer,
and only for engine/capability facts. See [`../shared_memory.py`](../shared_memory.py).

## The "button" — auto-sync on startup

Each machine pulls the latest engine from the common remote (the private GitHub
repo) when it starts. It only fast-forwards code; it never touches private data.

- Windows: [`sync-engine.ps1`](../scripts/sync-engine.ps1)
- Linux / macOS / Hetzner: [`sync-engine.sh`](../scripts/sync-engine.sh)

```powershell
.\scripts\sync-engine.ps1     # work PC
```
```bash
./scripts/sync-engine.sh      # server / mac
```

Wire it as the first step of the system launcher so "open the system" = "pull the
latest engine, then boot." The script is safe: it fast-forwards only, warns on
uncommitted changes, and reminds you to push local engine commits.

## Flow in one line

> Improve the engine on either system → `git push` → the other runs `sync-engine`
> on startup → it fast-forwards the new code only. Private data stays home, always.

To move a *specific* improvement without taking everything, `git cherry-pick` that
commit (the agent can do this for you).

---
¹ **Follow-up (not yet done):** brand *content* (`social-studio/brand_kit` assets) is
currently committed, so it would travel. Making per-system brand content private
(git-ignored, each system fills its own) is a known next step — flagged here so it
isn't a silent gap. The memory/context/customer boundary above **is** enforced now.
