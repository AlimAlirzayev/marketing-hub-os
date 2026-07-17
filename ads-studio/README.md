# Ads Studio — Meta Ads Performance Dashboard

A premium, mobile-friendly Meta Ads reporting dashboard for **Xalq Sigorta**,
built into Xalq Insurance Digital OS. It mirrors the LinkedIn reference dashboard and goes a level
beyond it: AI executive summary, anomaly alerts, budget pacing + month-end
forecast, full conversion funnel, and a Gmail↔Meta spend reconciliation.

> Zero extra cost: the AI runs on the free, live **Gemini** key already in the
> Xalq Insurance Digital OS `.env` (no OpenAI). Pure-Python stack — no Docker, no Node build —
> so it runs on the locked-down corporate machine.

## Run

```powershell
.\run.ps1            # sets up venv on first run, opens http://localhost:8800
# or a custom port:
.\run.ps1 9000
```

Then open `http://localhost:8800`.

## What it shows

| Tab | Content |
|---|---|
| **Hesabat** | AI summary · anomaly alerts · budget pacing/forecast · 8 KPI cards with MoM deltas · daily trend · Lead vs Mesaj · conversion funnel · cost analysis. FB/IG filter. |
| **Ödənişlər** | Gmail→Meta payment receipts, totals, and a spend-vs-invoiced reconciliation (unbilled tail). |
| **Satış** | Sales-by-channel (CRM intentionally deferred — clearly flagged as demo). |
| **AI köməkçi** | Floating assistant; grounded Q&A in Azerbaijani over the month's real numbers. |

PDF/print: the **PDF** button renders a clean, board-ready report (logo + period,
chrome hidden) via the browser's print-to-PDF.

## Səyahət YTD rəhbərlik hesabatı

`/travel-report` səyahət sığortasını ayrıca məhsul xətti kimi göstərir. Ekran
cari il üzrə Meta kampaniyalarını açar sözlərlə seçir, Purchase/gəlir olduqda
CPA və ROAS hesablayır, yaş × cins, region, placement və cihaz seqmentlərini
çıxarır. Demo fallback yoxdur: canlı Meta mənbəyi işləmirsə rəqəm əvəzinə
mənbə statusu göstərilir.

Real verilmiş polis sayı CRM CSV-dən brauzerdə hesablanır. Fayl serverə
göndərilmir və PII saxlanmır; yalnız unikal polis sayı, premium cəmi və valyuta
ekranda aqreqatlaşdırılır. Board versiyası brauzerin `PDF / Çap` düyməsi ilə
saxlanır.

## Architecture

```
ads-studio/
├── app.py              FastAPI: serves the SPA + JSON API (/api/report, /api/summary, /api/ask)
├── config.py           Brand, targets (budget/lead goals), currency, data-mode
├── connectors/
│   ├── demo.py         Deterministic demo engine (April 2026 pinned to reference)
│   ├── meta.py         Live Meta Marketing API (Graph Insights) — same output shape
│   ├── gmail.py        Meta receipts from a Gmail cache (MCP- or API-refreshed)
│   └── __init__.py     Dispatcher: picks demo vs live, layers invoices
├── analytics/
│   ├── kpis.py         Funnel + month-over-month deltas (same-elapsed-window)
│   ├── pacing.py       Budget pacing + month-end forecast
│   ├── anomalies.py    Rule-based alerts (CTR drop, frequency, CPM/CPL spike, burn)
│   └── ai.py           Gemini exec summary + grounded Q&A (graceful fallback)
├── templates/dashboard.html   Single-page premium UI (Tailwind + Chart.js via CDN)
├── static/                     app.js + Xalq Sigorta logos
└── data/                       invoices_cache.json + daily snapshots
```

Demo and live data return the **identical report shape**, so flipping the source
changes nothing downstream.

## Going live (real Meta data)

Add to the repo-root `.env`, then restart:

```env
META_ACCESS_TOKEN=EAAB...           # long-lived / system-user token with ads_read
META_AD_ACCOUNT_ID=act_1234567890   # keep the act_ prefix
# optional: ADS_DATA_MODE=live   (auto-detected when the two above are present)
```

`config.DATA_MODE` flips to `live` automatically when both are set; any live
failure falls back to demo so the dashboard never goes blank.

**Resilience.** The live connector pools one HTTPS session, retries Meta's rate
limits (codes 4/17/32/80xxx) and transient 5xx with exponential backoff +
jitter, and fails fast on fatal errors (expired token 190, permissions). It
also caches each Graph response in-process for a short TTL, so the duplicate
month fetches a single dashboard load fans out into (report + baseline +
segments…) collapse to one API call. Any persistent fallback to demo is logged
to stderr — never silent. Tune via `.env`:

```env
ADS_META_MAX_RETRIES=3     # retries per call on throttle/5xx (0 = off)
ADS_META_CACHE_TTL=300     # seconds to cache Graph responses (0 = off)
```

### Real invoices (Gmail)

Meta has no paid-invoice API, so receipts come from Gmail. The server reads
`data/invoices_cache.json`; refresh it either via the Xalq Insurance Digital OS Gmail MCP
(search `from:Meta receipt`, write the cache) or a scheduled Gmail-API job.
Schema matches `connectors/demo._invoices` output.

## Targets (budget pacing)

Set the monthly plan in `.env` (defaults in `config.py`):

```env
ADS_MONTHLY_BUDGET=2500
ADS_TARGET_LEADS=1800
ADS_MAX_CPL=1.80
```

## Roadmap

- Wire the daily AI summary into the Xalq Insurance Digital OS autonomous layer → Telegram morning report.
- Add Google/TikTok ad sources behind the same connector interface.
- Server-side PDF (reportlab) for unattended scheduled exports.
