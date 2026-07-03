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

## Auto-sync — you never have to ask

One brain does all syncing: [`scripts/sync_engine.py`](../scripts/sync_engine.py)
(stdlib only, no venv). It **pulls** new engine commits (fast-forward only) and
**pushes** your already-committed engine commits — never auto-committing a dirty
tree, never force-pushing, never touching private (git-ignored) data. It has a
short network timeout and never raises, so it can safely run from a hook.

Every entry point calls that one brain, so both machines stay current **without
you doing anything**:

| Trigger | What fires | Effect |
| --- | --- | --- |
| **Open a chat / VSC session** | SessionStart hook → `sync_engine.py --pull-only` | You open, it pulls the newest engine in the background — the first thing that happens. |
| **End a session** | SessionEnd hook → `sync_engine.py --push-only` | Your committed engine improvements ship to the other machine automatically. |
| **Boot the system** | `START_MARKETING_OS.ps1` step 0 | "Open the system" = "pull latest, then run it." |
| **One click** | double-click [`PULL.bat`](../PULL.bat) | Token-free, no chat — just syncs. |
| **From your phone** | Telegram `/update` (owner only) | The VPS pulls the latest engine on command. |
| **Always-on host, by itself** | `gateway.supervisor` engine-sync thread | Pulls at start + every `ENGINE_SYNC_MIN` minutes (default 60; 0 = off) and Telegram-announces real updates to the owner — a 24/7 server stays current with no human. |
| **Manual** | `scripts/sync-engine.ps1` / `.sh` (thin wrappers) | Same brain, explicit run. |

So on the MacBook you don't say "pull first" — by the time you write your first
message, the SessionStart hook has already synced. If it prints
`pulled new engine updates`, that's the update finishing in the background.

## Keys travel too — but only ENCRYPTED (the vault)

Plaintext keys never touch git (`.env` stays ignored). But keys still flow
between the friends automatically, the way SOPS/git-crypt do it: as ciphertext.

* `secrets/keys.vault` — git-TRACKED encrypted blob (Fernet: AES + HMAC, scrypt
  key derivation). Anyone reading the repo sees noise — no values, no key names.
* `KEY_VAULT_SECRET` — the master passphrase, set ONCE per machine in `.env`
  (same value on both). It never travels and is never committed.

One-time bootstrap on EACH machine (owner-only, message auto-deleted):

    /setkey KEY_VAULT_SECRET <your-passphrase>

From then on the flow is fully automatic:

    /setkey RAPIDAPI_KEY abc123...  →  written to THIS .env
                                    →  encrypted into the vault
                                    →  committed + pushed (mail sent)
    …other friend's next sync       →  sync brain decrypts + merges into ITS .env

`sync_engine.py` applies newly-arrived vault keys after every pull, so every
trigger (session open, boot, PULL.bat, `/update`, the supervisor's hourly tick)
also delivers keys. Machine-identity keys (`KEY_VAULT_SECRET` itself,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_CHAT_ID`) are hard-excluded from syncing.
`/keys` shows masked local status + which keys ride the vault. Replies are
always masked; the carrying Telegram message is deleted.

## Flow in one line

> Improve + commit the engine on either system → SessionEnd (or `/update`, or
> PULL.bat) pushes it → the other machine's SessionStart pulls it (fast-forward
> only). Private data stays home, always.

To move a *specific* improvement without taking everything, `git cherry-pick` that
commit (the agent can do this for you).

---
¹ **Follow-up (not yet done):** brand *content* (`social-studio/brand_kit` assets) is
currently committed, so it would travel. Making per-system brand content private
(git-ignored, each system fills its own) is a known next step — flagged here so it
isn't a silent gap. The memory/context/customer boundary above **is** enforced now.
