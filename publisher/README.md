# Publisher — the auto-publish layer

The missing last halqa of Xalq Insurance Digital OS marketing: `/post`, `/clip`, and
`/edit-video` make the asset; **Publisher ships it** to TikTok, X, Instagram,
LinkedIn, Bluesky, and more. Free-first, quota-aware, no silent drops — the
provider cascade lives in
[`claude-agents/.claude/capabilities.md`](../claude-agents/.claude/capabilities.md).

```
asset (clip / image / campaign slug)
   │  package.py   → per-platform caption (trimmed to each limit) + media + time
   ▼
router.py ──▶ Postiz (self-hosted, FREE)         live posting / scheduling
          └─▶ manual handoff (always works)       paste-ready .txt blocks
```

## Why Postiz
Postiz is AGPL-3.0, self-hostable for free, ships a public API + its own MCP
server, and posts to 20+ networks. The paid alternative (Blotato, $29/mo) is the
cascade's fallback only. See the gap analysis in capabilities.md.

## Layout
```
publisher/
├── package.py   assemble the per-platform plan (captions, limits, schedule)
├── postiz.py    Postiz public-API client (integrations, upload, posts)
├── manual.py    write paste-ready blocks  (the always-works fallback)
├── router.py    the cascade dispatcher (Postiz → manual, no silent drops)
└── run.py       CLI entry point
```

## Usage
```powershell
# See the package without touching the network (always works):
python publisher/run.py "video-studio/output/clips/<slug>/clip1_score92.mp4" `
       --to tiktok,x,instagram --dry-run

# Go live (needs Postiz running + POSTIZ_API_KEY):
python publisher/run.py "<asset>" --to tiktok,x --when now

# Schedule, staggered across the day:
python publisher/run.py "<slug>" --to tiktok,x,instagram --stagger 30 `
       --when 2026-06-09T09:00
```

From Claude Code the intended entry point is `/publish` (which drives this).

### Captions
Resolved in order: `--caption` override → the campaign's
`copy-studio/output/<slug>/caption-*.md` → a clip's title from its `clips.json`
→ a slug placeholder. Each is trimmed to the platform's character limit; the
report names the source so nothing is invented silently.

### Output
Manual / dry-run blocks land in `output/publish/<slug>/<timestamp>/`:
`plan.json` + one `<platform>.txt` per channel.

## Going live — stand up Postiz (free)
```powershell
docker compose up -d postiz          # http://localhost:5000
```
Then: create an account → connect your socials → **Settings → Public API** →
make an API key → set `POSTIZ_API_KEY` in `.env`. `POSTIZ_JWT_SECRET` and
`POSTIZ_API_URL` are already in `.env`. The Postiz service is defined in
[`docker-compose.yml`](../docker-compose.yml).

> Until Postiz is up, `/publish` and `run.py` still work — they route to the
> manual-handoff tier and tell you so. Nothing is half-broken; the live API call
> is the only piece that waits on Docker.
```

## Privacy guard (child / family / real-person safety)

Publishing to a public channel is outward and hard to reverse, so before a live
post the plan passes through `privacy_guard.enforce`. It flags — with no model
call — when a **minor or an identifiable real person** may appear:

- person-signal words (AZ + EN: uşaq, körpə, ailə, child, baby, family, kid, ugc,
  testimonial, …) in the slug, any caption, or a media filename;
- a `privacy.json` sidecar in the media folder — an authoritative human override:
  `{"minors": true}` or a `"people": [...]` list without `"consent": true`.

When flagged, the **live publish is held** and a checklist is written to
`output/publish/<slug>/PRIVACY-CHECKLIST.md` (consent · audience scope · necessity
· safer substitution). Release it deliberately:

```
python publisher/run.py <asset|slug> --to tiktok,instagram --privacy-ack
```

`--dry-run` is never blocked (it contacts no network) but still surfaces the flag.
Any scan error fails safe — the guard holds rather than letting content through.
Editing a minor's image with an external AI model stays blocked without an explicit
ack (`minor_edit_allowed()` is the reusable predicate for media_studio/atelier).
