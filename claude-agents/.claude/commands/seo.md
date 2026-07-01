---
description: The SEO Engine — audit a site against the 2026 checklist, research keywords (Google Suggest + AI intent clusters), analyze the SERP content-gap, or write an on-page-perfect Azerbaijani article with structured data. Free-first, never fabricates a number.
argument-hint: audit <url> | research <keyword> | gap <keyword> | write <keyword> [--serp] [--pdf]
---

# /seo

RAMIN OS's search-visibility brain (`seo/`). Three engines over one free-first
core; deliverables are premium HTML/PDF, all text Azerbaijani, every metric
labelled (`CANLI` / `ƏLÇATMAZ`) — never guessed.

`$ARGUMENTS` = one of `audit`, `research`, `write` + its target.

## Route the request

### `audit <url>` — technical SEO audit
Run:
```
python -m seo audit <url> --html
```
Crawls the URL live, scores ~20 weighted checks (İndeksləmə, On-page, Struktur,
Performans, Etibar & AI) → `0-100` + grade, prioritized **kritik→kiçik** fix list,
and a premium HTML report in `output/seo/`. Add `--pdf` for a PDF (headless Edge).
Summarize the score, the top 3 fixes, and link the report file. If the site is
firewall-blocked from this machine, say so — it's the network, not the tool.

### `research <keyword>` — keyword discovery
Run:
```
python -m seo research "<keyword>"
```
Harvests real Azerbaijani long-tail from Google Autocomplete (keyless) and
clusters it by search intent (Məlumat / Kommersiya / Alış / Naviqasiya).
Present the clusters and call out the highest-value primary keyword per cluster.

### `gap <keyword>` — SERP competitor content-gap
Run:
```
python -m seo gap "<keyword>"
```
Pulls the live top competitors (DuckDuckGo SERP), crawls their heading structure,
and the LLM returns: table-stakes subtopics (must-cover), **content gaps** (ranking
opportunities few competitors cover), and real FAQ questions. Present the gaps
first — that's where the ranking upside is.

### `write <keyword>` — SEO article
Run:
```
python -m seo write "<keyword>"          # grounded in Google Suggest
python -m seo write "<keyword>" --serp   # + live SERP competitor gap (stronger)
```
Builds a brief grounded in the real keywords, then writes a full on-page-perfect
article (single H1, meta title/description, semantic H2/H3, FAQ) + JSON-LD
(Article + FAQPage), and **self-audits** the draft against our own checklist.
Report the word count, self-audit pass ratio, and link the article deliverable.
Remind the user to fact-check before publishing (AI-generated).

## Panel
The same engines run as a web panel on port **8860** (`SEO Studiyası`), embedded
in the Marketing OS Hub. Launch: `.venv/Scripts/python -m uvicorn seo.server:app --port 8860`.

## Rules
- **Free-first.** No paid SEO tool is required. Only Core Web Vitals needs an
  optional `PAGESPEED_API_KEY`; without it that row shows `ƏLÇATMAZ`.
- **Never fabricate.** Volumes/difficulty we can't measure are labelled, not invented.
- **Capture learnings.** After a notable audit/research run, persist durable
  takeaways with `python -m brain remember` (per the standing rule).
