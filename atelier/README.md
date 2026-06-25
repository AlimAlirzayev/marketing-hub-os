# Atelier — Marketing Cockpit (Creative Lab + Brand Brain)

A simple-but-powerful, browser-based cockpit for the **Xalq Sigorta** marketing
team, built into Xalq Insurance Digital OS. It surfaces the creative power that until now only
lived in CLI slash-commands (`/post`) and markdown files, behind a screen the
non-technical SMM + design team can actually use.

> Zero extra cost. Pure-Python (FastAPI), no Docker, no Node build — runs on the
> locked-down corporate machine exactly like `ads-studio`. The AI runs on the
> free, live **Gemini** key already in the Xalq Insurance Digital OS `.env`.

This is the **MVP**: two modules of the full 6-module vision (Plan, Create,
Creative Lab, Sentiment, Brand Brain, Publish).

## Run

```powershell
.\run.ps1            # first run sets up the venv, then opens http://localhost:8820
.\run.ps1 9000       # custom port
```

## The ChatGPT Bridge flow (why it costs nothing)

The hard, valuable part of a great visual is the **brand-grounded prompt + the
critique** — and both run on the free text LLM. The actual image is generated in
**your ChatGPT Business UI** (no API credits needed):

1. **Brief** → pick a Style DNA, format, model dialect, concept count.
2. Atelier composes N **distinct, copy-paste-ready prompts**, each built on the
   11-layer `master_template`, grounded in the active Style DNA + `brand.md` +
   the `ai-tells` exclusion list + your House Rules.
3. Per concept: **Copy prompt** → **Open ChatGPT** → generate the image →
   **drag it back** into the card.
4. **Critique** (free Gemini vision) scores the uploaded image for brand fit,
   AI-tells, and whether the headline/footer overlay zones are clean.
5. Compare in **Gallery** view, ⭐ the winner, rate, save.

## Modules

| Tab | What it does |
|---|---|
| **Creative Lab** | Brief → N concept prompts → ChatGPT Bridge upload → vision critique → A/B compare. Cards + Gallery views, lightbox, score badges, star rating. |
| **Brand Brain** | Pick the active Style/Voice/Model DNA, set House Rules + extra exclusions, view the live AI-tells filter and brand identity. The humanizer layer. |

## Architecture

```
atelier/
├── app.py          FastAPI: serves the SPA + JSON API
├── config.py       Brand, paths into social-studio/copy-studio, Gemini key, formats
├── brand.py        Brand Brain: reads DNA from the studios; owns brand_state.json
├── lab.py          Creative Lab: the art-director prompt composer (Gemini + fallback)
├── critique.py     Vision critique of uploaded images (Gemini + manual fallback)
├── llm.py          Thin Gemini wrapper (text + vision), bounded retries
├── store.py        SQLite: briefs → concepts → image/critique/rating
├── templates/atelier.html   Single-page cockpit (Tailwind via CDN)
├── static/app.js            All cockpit interactivity (vanilla JS)
└── data/                    atelier.db + uploads/ (created on first run, gitignored)
```

**Single source of truth:** Atelier never copies the curated studio markdown — it
reads `social-studio/` and `copy-studio/` at runtime. The only thing it owns is
`data/brand_state.json` (active selections + House Rules).

**Graceful by design:** every AI call falls back to a deterministic path
(template prompts / manual critique checklist), so the cockpit never shows a raw
error — consistent with the Xalq Insurance Digital OS "no silent drops" rule.

## Growth path

- SQLite → the Postgres already in `docker-compose.yml` is a contained
  `store.py` change (multi-user, history, auth).
- Brand Brain → write edits back to the source markdown (V1).
- Wire **Send to Canva** via the Canva MCP (AI concept → editable brand template).
- Add the remaining modules: Plan/Calendar, Create, Sentiment, Publish & Track.
- Optional upgrade: direct `gpt-image-1` API generation as a second visual engine
  (needs OpenAI API credits, separate from the ChatGPT Business sub).
```
