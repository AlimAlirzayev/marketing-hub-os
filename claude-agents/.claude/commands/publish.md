---
description: Publish a finished asset to social platforms via the free-first cascade (Postiz → manual). Quota-aware, no silent drops. Runs publisher/run.py.
argument-hint: <asset path or campaign slug> --to tiktok,x,instagram,... [--when now|ISO] [--caption "text"] [--stagger 30] [--dry-run]
---

# /publish

The last halqa: `/post`, `/clip`, and `/edit-video` produce a finished asset and
stop. **`/publish` ships it** — to TikTok, X, Instagram, LinkedIn, Bluesky, etc.
— through the free-first cascade in [capabilities.md](../capabilities.md). It is
a thin driver over `publisher/run.py`, which does the real work.

`$ARGUMENTS` = the asset (a file under `*/output/`, or a campaign slug) + flags.

## Steps

1. **Parse `$ARGUMENTS`.** Asset first; then `--to` (comma list, required),
   `--when` (`now` default, or ISO), `--caption` (override), `--stagger`
   (minutes between platforms), `--dry-run`.

2. **Default to a dry run first.** Unless the user already said "publish it" this
   turn, run with `--dry-run` so they see the exact per-platform package before
   anything goes live:
   ```
   python publisher/run.py "<asset>" --to <platforms> --dry-run
   ```
   Show the report + read back 1–2 of the generated `*.txt` blocks so the user
   can eyeball the captions.

3. **Go live on approval.** Re-run without `--dry-run`. The router
   (`publisher/router.py`) walks the cascade:
   - **Postiz** (free, self-hosted) if `POSTIZ_API_KEY` is set and it's
     reachable — uploads the media once, then creates/schedules one post per
     connected channel.
   - **Manual handoff** for anything Postiz can't deliver (key unset, server
     down, or a channel not connected) — paste-ready `.txt` blocks under
     `output/publish/<slug>/<ts>/`. Labelled, never silently dropped.

4. **Report** exactly what the CLI returned: per platform ✅ posted / ⏰ scheduled
   / ✋ manual / 📝 planned, plus the manual-blocks folder when present. If
   anything fell to manual, that folder is the user's next action — point at it.

## Setup (one-off, to enable live posting)
Postiz is wired but needs Docker:
```
docker compose up -d postiz          # http://localhost:5000
```
Then create an account, connect your socials, make an API key under
**Settings → Public API**, and set `POSTIZ_API_KEY` in `.env`. Until then
`/publish` still runs — it just routes to the manual-handoff tier and says so.
See [publisher/README.md](../../../publisher/README.md).

## Rules
- **Dry-run before live** unless explicitly told to post now.
- **Free-first.** Postiz before anything paid; never spend a credit a free
  provider covers.
- **No silent drops.** Undeliverable platform → labelled manual block.
- **One interface.** New networks plug into `publisher/package.py::PLATFORMS`
  and the cascade — not new commands.

## Examples
```
/publish video-studio/output/clips/<slug>/clip1_score92.mp4 --to tiktok,x --dry-run
/publish xs-georgia-train-new-route --to instagram,linkedin --when now
/publish <slug> --to tiktok,x,instagram --stagger 30 --when 2026-06-09T09:00
```
