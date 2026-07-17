# Brand Dossier Engine

Weekly brand + competitor intelligence for Xalq Sığorta. A standalone RAMIN OS
**job** (not a service): no port, no schedule, no services.json entry. It
follows the `gateway/radar.py` architecture — free mechanical collection,
smart-tier synthesis only for judgement, and honest ƏLÇATMAZ labeling instead
of silent drops or invented facts.

- Engine: `scripts/brand_dossier.py`
- Tests: `tests/test_brand_dossier.py` (offline, part of the root suite)
- Governance: `config/agent_permissions.json` → `brand_dossier` (read-only +
  sandbox; no posting, no login-walled scraping, no fabricated data)

## Run

```powershell
python scripts/brand_dossier.py --run       # live: Gemini google_search grounding + public pages
python scripts/brand_dossier.py --dry-run   # offline: bundled DEMO fixtures, zero network
python scripts/brand_dossier.py --dry-run --out <dir>   # custom output directory
```

Live data path:

1. **Public page signals** — plain HTTPS GET of insurer sites
   (xalqsigorta.az + competitor homepages). Login walls and Instagram are out
   of scope by design. A dead site becomes an ƏLÇATMAZ entry, never a gap.
2. **Grounded research** — direct REST `generateContent` call with
   `tools:[{"google_search":{}}]` (llm_router has no tool support). The key is
   read from env (`GEMINI_API_KEY` / `GOOGLE_API_KEY`), sent only in the
   `x-goog-api-key` header, never printed or logged. Model override:
   `BRAND_DOSSIER_GEMINI_MODEL` (default `gemini-2.5-flash`).
3. **Opportunity synthesis** — "rəqiblərin demədiyi bucaqlar" is a judgement
   task, so it runs on `llm_router` `tier="smart"` (Claude-subscription first,
   free floor after), exactly like `radar.digest()`.

## Outputs (`output/brand-dossier/`)

| File | Role |
|------|------|
| `dossier_YYYY-MM-DD.md` | **Primary, human.** Full Azerbaijani dossier: brand position, competitor moves, market/regulatory news, opportunity angles. Every fact carries source + date + label. |
| `dossier_latest.json` | **Primary, machine.** Stable structured export (schema below) for other RAMIN OS organs and a future brand-intelligence panel. |
| `canvas_paste.txt` | Secondary compact summary block (≤ 2500 chars) — a paste-ready digest for any narrow text field. |

## JSON schema (v1) — the consumer contract

`dossier_latest.json` is versioned via `schema_version`. Additive changes keep
`1`; breaking changes bump it. A future FastAPI panel should key off this file
only — never parse the markdown.

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-07-16T07:04:11+00:00",   // UTC ISO-8601
  "mode": "live",                                 // "live" | "dry-run"
  "brand": "Xalq Sığorta",
  "competitors": ["Paşa Sığorta", "Atəşgah Sığorta", "Meqa Sığorta", "A-Qroup Sığorta"],
  "models": { "grounded": "gemini-2.5-flash", "digest": "claude-code/subscription" },

  // Per-section honesty label: CANLI (live-sourced) | DEMO (fixture) | ƏLÇATMAZ (failed)
  "section_status": {
    "brand_position": "CANLI",
    "competitor_moves": "CANLI",
    "market_news": "CANLI",
    "opportunity_angles": "CANLI"
  },

  // One fact item — the atom every consumer renders:
  //   { "text": "...", "source": "xalqsigorta.az" | null,
  //     "date": "2026-07-08" | null, "label": "CANLI" | "DEMO" | "ƏLÇATMAZ" }

  "brand_position": {
    "status": "CANLI",
    "summary": "raw Azerbaijani bullet block for direct display",
    "items": [ /* fact items */ ]
  },
  "competitor_moves":   [ /* fact items */ ],
  "market_news":        [ /* fact items */ ],
  "opportunity_angles": [ /* fact items — each cites the section it derives from */ ],

  // Flat, deduplicated source list (grounding chunks + fetched official pages)
  "sources": [
    { "title": "...", "url": "https://...", "date": "2026-07-16", "section": "brand_position" }
  ],

  // Unreachable sources / failed steps — surfaced, never hidden
  "failures": [ "mega.az: HTTPSConnectionPool(...)" ]
}
```

## Hard rules

- **No fabricated data.** Prompts explicitly forbid inventing facts, numbers,
  names, or dates; anything unfound is marked ƏLÇATMAZ. Dry-run output is
  labeled DEMO throughout — it can never masquerade as CANLI.
- **Free-first, zero budget.** Grounded Gemini + public HTTPS only; the
  premium tier is touched once, for the opportunity synthesis.
- **Read-only.** The engine writes only under `output/brand-dossier/` (or
  `--out`). It never posts, sends, logs in, or touches `.env`.
