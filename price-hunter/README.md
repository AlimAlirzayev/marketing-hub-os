# Price Hunter — AZ price-intelligence agent

Finds the **cheapest *trustworthy*** price for a product across Azerbaijani
retailers, marketplaces and classifieds — and tells you when the absolute
cheapest listing is a replica/used/grey-market trap rather than a deal.

Not a plain search: it disambiguates the exact model, fans out across many
sources in parallel, extracts offers with an LLM where the HTML is messy, scores
each listing for authenticity, and returns one honest verdict.

## Pipeline

```
query
  └─ resolve.py   LLM builds a canonical ProductSpec: exact variants, model codes,
  │               accessory/replica exclusions, and a fair AZN price window.
  └─ sources.py   async fan-out. Structured sources (Next.js __NEXT_DATA__ / Nuxt /
  │               JSON API) are harvested generically; aggregators return HTML.
  └─ extract.py   LLM turns messy aggregator HTML into offers (regex fallback).
  └─ score.py     resolve.match() keeps only the needle; trust score flags
  │               replicas/used; rank = price * (1.5 - trust)  → cheap AND legit.
  └─ hunt.py      orchestrates + LLM verdict (the single most honest answer).
  └─ report.py    JSON + Markdown on disk; optional Telegram push.
```

## Dashboard (on-demand backend)

A local FastAPI backend + single-page dashboard — run searches with filters
whenever you want, no scheduler.

```bash
run.bat                                  # launches backend + opens the dashboard
# or:  .venv/Scripts/python -m uvicorn server:app --port 8830
```
Open http://localhost:8830 — search box, all filters, market band, best-buy /
cheapest picks, verdict, ranked offers, and the honest source-coverage table.
JSON API: `POST /api/hunt {query, max_price, min_trust, official, condition,
sort, deep}` · `GET /api/health`.

## CLI usage

```bash
.venv/Scripts/python cli.py "airpods pro 2"
.venv/Scripts/python cli.py "airpods pro 3" --limit 15
.venv/Scripts/python cli.py "iphone 15 pro" --json
.venv/Scripts/python cli.py "airpods pro 2" --telegram      # DM the verdict
```

**Filters (pandas layer):**
```bash
--max-price 500 --min-price 300   # price window
--min-trust 0.7                   # only trustworthy listings (0..1)
--official                        # official retailers only
--condition new|used|refurbished  # by condition
--source ispace                   # one source (substring)
--sort deal|price|trust           # ordering
--deep                            # render JS-SPAs (qiymeti.net/ucuzu/umico)
```

Reports are written to `data/reports/<query>-<timestamp>.{json,md}`.

## Data layer & deep engines

- **pandas** ([frame.py](frame.py)) — cross-source dedupe + a **data-driven fair band**
  (robust median/MAD of the scraped cluster, not an LLM guess), so "below/above
  market" flags and the verdict reflect the *actual* distribution. The CLI shows
  `Market (scraped): median … · genuine band …`.
- **Deep render** (`--deep`) picks the strongest available engine automatically:
  **Apify** ([apify_deep.py](apify_deep.py), managed cloud browser, default actor
  `apify/website-content-crawler` — active, token set) → else local **Playwright +
  system Chrome** ([render.py](render.py), no browser download).
- **Honest finding on the last 3 SPAs** (umico/ucuzu/qiymeti.net): they resist
  *every* tier tried — HTTP, TLS-impersonation (curl_cffi), local Playwright, and
  Apify cloud render (web-scraper + website-content-crawler both return an empty
  shell: datacenter-IP anti-bot + interaction-gated search). Cracking them needs
  internal-API reverse-engineering (as done for the high-value ispace + kontakt)
  or residential-proxy interaction. Low marginal value — qiymetleri.az already
  aggregates these same sellers — so they stay surfaced-not-wired by design.

## Configuration

Reuses the repo-root `.env` (no separate keys needed):

| var | role |
|-----|------|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | primary LLM (disambiguation, extraction, verdict) |
| `GROQ_API_KEY` | LLM failover |
| `MODEL_FREE_BULK` | Gemini model id (default `gemini-2.0-flash`) |
| `TELEGRAM_BOT_TOKEN` + `PH_TELEGRAM_CHAT_ID` | optional verdict push |
| `APIFY_API_TOKEN` | reserved for anti-bot source fallback |

With **no** LLM key it degrades gracefully: a built-in fallback spec for known
products + a regex price-scanner.

## Sources & honesty

Every run prints a **source coverage** table. Blocked (e.g. `kontakt.az` 403
anti-bot) or skipped (SPA / unreliable-API) sources are reported, never silently
dropped — so the user never wonders "why isn't X here?".

**Working today (always-on web/API tier):**
- `ispace.az` — official Apple partner, JSON API (`/api/v2/search/products?lang=&query=`); the genuine-price anchor
- `kontakt.az` — Magento **GraphQL** API (`/graphql`), via `curl_cffi` browser-TLS impersonation
- `bakuelectronics.az` — structured `__NEXT_DATA__`
- `qiymetleri.az` — cross-store aggregator (per-product SEO page → LLM digest)
- `irshad.az` — official store (HTML → LLM)
- `tap.az` — used market (structured)
- `lalafo.az` — used market, JSON API (correct param is `q=`, not `query=`)
- `birmarket.az` (Umico) — best-effort HTML → LLM
- `optimal.az` — attempted via impersonation; usually 403 (surfaced honestly)

**Opt-in wide tier (Apify; `--serp` / `--social` / `--wide`):**
- `google-serp` — Google results catch-all: surfaces prices from stores we can't
  reach directly (the JS-SPAs + small shops like w-t.az) straight from the
  snippet; `.az`-filtered, tagged with the real store domain + "via Google — verify".
- `instagram` — **social-commerce sellers with no website at all** (the huge
  Instagram/TikTok slice of AZ retail). Hashtag pages → caption price (picked by
  proximity to the product mention) + seller handle; scored on the low "social"
  tier with "DM to verify, no warranty".

Any plain-httpx `403/429` auto-retries through `curl_cffi` (browser TLS) before
being marked blocked — a free, local WAF bypass (no Apify needed; the repo's
`APIFY_API_TOKEN` is empty).

**Surfaced but not yet wired (each shown in coverage with a reason, never hidden):**
`qiymeti.net` (WP ajax, JS/nonce-gated), `ucuzu.az` / `umico.az` (aggregator SPAs),
`maxi.az` (CF 525), `soliton.az` / `trendyol.az`, `lalafo.az` (API ignores query).
These need a **headless browser** (JS execution) — the only remaining gap.

## Roadmap

- Apify fallback for WAF-protected stores (kontakt, irshad anti-bot tiers).
- Fix lalafo/tap used-market query so second-hand deals are covered cleanly.
- Per-offer deep-links from aggregators (follow through to the actual store).
- Scheduled price-watch → Telegram alert on drop (Xalq Insurance Digital OS autonomous layer).
