# Multi-Platform Acquisition Map

Honest, constraint-filtered map of how each platform's creator data can be
acquired **for free, at zero ban risk, on a corporate Win11 / no-Docker box**.
Connectors plug into `orchestrate.py` (one `Connector` contract, fan-out +
fallback chain). "Buildable now" = no paid infra, no account pool, no App Review.

| Platform | Free production method | Ban/legal risk | Our fit | Status |
|---|---|---|---|---|
| **YouTube** | Official Data API v3 (key) | none | ★★★★★ | ✅ built (`sources_youtube.py`) |
| **Telegram** | Public web preview `t.me/s/<channel>` (anonymous, no MTProto) | none | ★★★★★ | ✅ built (`sources_telegram.py`) |
| **Web / blogs** | Keyless search (DuckDuckGo Lite) + LLM extraction of public listicles | none | ★★★★☆ | ✅ built (`sources_web.py`) — discovery feeder |
| **Instagram** | Apify (paid) · **RapidAPI free tier (built)** · IG Graph Business Discovery (needs app provisioning) · `instagrapi` (account+ban) | med (scraping) | ★★★☆☆ | ✅ Apify built (budget-gated) + RapidAPI fallback built (`sources_rapidapi.py`); add `RAPIDAPI_KEY` |
| **TikTok** | **RapidAPI free tier (built)** · `TikTokApi` (Playwright, fragile) · `yt-dlp` (metadata only) | med | ★★★☆☆ | ✅ built via generic RapidAPI connector; add `RAPIDAPI_KEY` |
| **X / Twitter** | `Scweet` / `twscrape` — require **account pools + cookies** (snscrape is dead) | **high** (account bans) | ★★☆☆☆ | ⛔ needs throwaway accounts; not zero-risk |
| **Threads** | No read API; unofficial libs fragile | med | ★★☆☆☆ | ⛔ deferred |
| **LinkedIn** | Aggressive anti-bot, ToS/legal exposure; official API locked | **high (legal)** | ★☆☆☆☆ | ⛔ not advisable |
| **Snapchat** | No public creator-discovery API; ephemeral content | n/a | ★☆☆☆☆ | ⛔ not viable |

## Principle (why this map looks like this)

The hard part of social scraping is never the code — it is **proxies + aged
accounts + anti-bot maintenance + ToS/legal**. LLMs write the parser; they do not
grant a residential IP pool or an un-bannable account. So instead of fighting a
platform's wall, we go **where public data is legally and freely readable**:

- **Official APIs** (YouTube) — free, legal, no ban.
- **Public anonymous previews** (Telegram `t.me/s`) — no login, no ToS selfbot.
- **Public web** (listicles, blogs) — public pages, fair to parse.

Platforms that *require* an authenticated account pool (X) or App Review
(IG/FB owned comments) or have no read surface (Snapchat) are documented as
**blocked**, not faked. A failing/blocked source degrades honestly in the
coverage table — it never silently drops.

## Generic RapidAPI connector (BUILT — `sources_rapidapi.py`)

One RapidAPI key unlocks every host you subscribe to. The connector is a
**declarative host-adapter registry**: each host is a small field-map, and the
extractor tries several key paths per field, so swapping/adding a host is one
`RapidAdapter` entry — no new code path. It is primarily an **enrichment**
connector (give it handles → real profile + posts), wired as the Instagram
*fallback* (priority 20, after Apify) and as the sole TikTok connector.

User action (≈3 min): create a free RapidAPI account at <https://rapidapi.com/hub>,
subscribe to a free-tier social host (e.g. `instagram-scraper-api2`,
`tiktok-scraper7`), copy the `X-RapidAPI-Key`, set `RAPIDAPI_KEY=...` in `.env`.
Then `python rapidapi_probe.py` reports exactly which hosts the key unlocks.

**Or let `doit` fetch the key for you.** The repo-root [`doit/`](../doit/) agent
drives Chrome/Edge under your own logged-in session, finds the RapidAPI key on the
dashboard, and writes `RAPIDAPI_KEY` into `.env` automatically:
`..\.venv\Scripts\python.exe -m doit rapidapi`. First run opens a window to log in
once; later runs are autonomous.

## Buildable next (no new infra)

1. **Discovery → enrichment chaining** — feed `web` / `telegram`-discovered
   handles as seeds into the RapidAPI/YouTube enrichment connectors automatically,
   so a single `source=all` run discovers *and* enriches in one pass.

## Needs a user/ops decision (not zero-cost or not zero-risk)

- **X / Twitter**: provision 1–2 throwaway accounts for `twscrape`/`Scweet`
  (accept ban-and-replace churn), or pay an X scraping API.
- **Instagram/Facebook owned comments**: Meta App Review for
  `instagram_manage_comments` + `pages_read_engagement` (weeks).
