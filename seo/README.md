# SEO Engine (`seo/`)

The search-visibility brain of RAMIN OS. A root package (like `brain/`,
`gateway/`, `orchestrator/`) so it imports `llm_router` and `brain` directly and
plugs into the hub / `services.json` / `/seo` skill like every other studio.

**Charter:** free-first (no paid SEO tool), dependency-light (HTML parsed with the
stdlib — runs on the locked-down machine), and it **never fabricates** a number —
anything it can't measure is labelled `ƏLÇATMAZ`.

## Three engines

| Engine | What it does | Status |
|--------|--------------|--------|
| **Audit** | Crawl any URL → score it against the **2026 SEO checklist** → prioritized Azerbaijani fix report | ✅ live |
| **Research** | seed keyword → Google Suggest expansion → LLM clustering + search intent + **SERP content-gap** | ✅ live |
| **Content** | keyword → grounded brief → on-page-perfect AZ article + JSON-LD → self-audit | ✅ live |

## Use it now

```bash
python -m seo audit example.com --html        # full audit + premium HTML report (--pdf for PDF)
python -m seo research "kasko sığorta"        # keyword harvest + AI intent clusters
python -m seo gap "kasko sığorta"             # SERP competitors → table-stakes + ranking gaps + FAQ
python -m seo write "kasko sığorta nədir" --serp --refine  # SERP-grounded article + self-reflection loop
python -m seo pipeline "kasko sığorta" --serp --publish    # durable LangGraph flow; pauses for human
python -m seo pipeline --resume <thread_id> --decision approve  # resume from any process
```

The **pipeline** is the durable form of the whole flow (research→gap→brief→
write+refine→publish gate): every node is checkpointed to SQLite, so a crashed
batch resumes where it died, and publishing always pauses for human approval
(the interrupt survives process death). Deferred work + triggers: `seo/ROADMAP.md`.

### Web panel + skill
- **Panel** (port 8860, `SEO Studiyası`, embedded in the Marketing OS Hub):
  `.venv/Scripts/python -m uvicorn seo.server:app --port 8860`
- **Skill:** `/seo audit <url>` · `/seo research <kw>` · `/seo write <kw>`
- Registered in `services.json` (key `seo`, cat `Kontent`).

The audit gathers **live** signals — page HTML, `robots.txt`, sitemap
reachability, and Core Web Vitals (PageSpeed Insights) — runs ~20 weighted
checks, and prints a `0-100` score + grade with a **kritik → kiçik** fix list.

### What it checks (the 2026 must-haves, codified)

- **İndeksləmə & Crawl** — HTTPS, HTTP status, indexability (meta robots /
  robots.txt), canonical, robots.txt, XML sitemap, clean URLs
- **On-page** — title, meta description, single H1, `html lang`, content depth,
  image alt-text
- **Struktur** — heading hierarchy, Open Graph, favicon, hreflang, breadcrumb
- **Performans & Mobil** — viewport, **Core Web Vitals (LCP / INP / CLS)**
- **Etibar & AI** — **Schema.org / JSON-LD**, AI-bot governance (GEO)

Judgment reflects the 2026 review, not folklore: images are judged by Core Web
Vitals + modern signals (not a hard 150 kb rule); headings are judged as a
semantic hierarchy (not font size); structured data and AI-bot governance are
first-class.

## Public API

```python
from seo import audit_url, audit_report
r = audit_url("example.com")          # -> AuditResult (never raises)
print(audit_report(r))                # Azerbaijani report
print(r.score, r.grade, r.summary())
```

## Layout

```
seo/
  config.py            env + free-first connector config (zero required keys)
  http.py              resilient fetch (never raises)
  htmlparse.py         stdlib HTML → on-page SEO signals
  connectors/
    robots.py          robots.txt + sitemap discovery + AI-bot detection
    pagespeed.py       Core Web Vitals via PageSpeed Insights
  audit/
    checklist.py       the 2026 checklist as scored checks
    auditor.py         gather signals (concurrent) → run checks → AuditResult
  report.py            AuditResult → Azerbaijani report / JSON
  cli.py               `python -m seo audit <url>`
  tests/               network-free, deterministic (12 checks)
```

## Keys (all optional)

| Key | Unlocks | Without it |
|-----|---------|------------|
| `PAGESPEED_API_KEY` | Core Web Vitals (LCP/INP/CLS) | that one row shows `ƏLÇATMAZ` |
| `GEMINI/GROQ` (via `llm_router`) | research clustering + content writing | used in Phase 2/3 |

Everything else — crawling, on-page audit, robots/sitemap, keyword expansion via
Google Suggest — is **100% free, keyless**.
