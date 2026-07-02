# SEO Engine — Roadmap & Deferred Work

**Why this file exists:** chat sessions die; git-tracked files don't. This is the
durable registry of SEO work that was *deliberately deferred with a trigger
condition*. Any agent (Claude Code via `/seo`, Codex, the gateway worker) that
touches the SEO domain must read this file first — and the brain's
`recall("seo")` will surface the same items before any SEO job.

> Update rule: when you complete or re-scope an item, edit it here in the same
> commit as the work. Never delete an item silently — mark it done with a date.

## ✅ Done (context for what's below)

| Date | What |
|------|------|
| 2026-07-01 | Engines live: Audit (2026 checklist) · Research (Suggest+clusters) · Gap (SERP) · Content (brief→article+JSON-LD) · panel :8860 · `/seo` skill |
| 2026-07-02 | Self-reflection loop (`refine.py`): write→critique→revise→re-measure, never-regress guard |
| 2026-07-02 | LangGraph pipeline (`graph.py`): durable checkpointed flow, publish interrupt |

## 🔜 Active next steps (no trigger needed — just build)

1. **GSC connector** (`seo/connectors/gsc.py`) — Search Console API, service-account
   (same pure-REST pattern as ga4-studio). Ground truth: impressions/clicks/position
   per page/query. *This is the prerequisite for item D1 below.*
2. **Full-site audit** — crawl the sitemap (N pages), aggregate scores, one report.
3. **Gateway agent tool** — expose `seo.audit/research/write` to the autonomous
   worker so Telegram tasks can invoke them.

## ⏸️ DEFERRED — with explicit triggers (do NOT forget these)

### D1. GSC "reinforcement" learning loop
- **What:** after an article is published, wait ~28 days → pull its real GSC
  data (clicks/impressions/position) → `brain.reflect` distills "what worked"
  (title patterns, intents, lengths, topics) → future briefs `recall` those
  lessons. The system learns from its own market outcomes.
- **Trigger:** GSC connector exists AND ≥1 article published to a real site.
- **Owner:** whoever builds the GSC connector wires the loop in the same arc.

### D2. Fine-tuning a model on our SEO corpus
- **What:** fine-tune a cheap model (e.g. Gemini Flash tuning) on Azerbaijani
  SEO articles scored by real outcomes, so first drafts start at publish-grade.
- **Trigger:** ≥500 articles with GSC outcome scores collected via D1.
  (Verdict 2026-07-02: NOT before that — no labeled AZ SEO corpus exists; small-N
  tuning wastes money. D1 builds the dataset for free.)
- **Where the dataset will live:** `data/seo/corpus/` (gitignored, private).

### D3. DataForSEO paid tier (optional)
- **What:** gated connector for real search volume / difficulty / backlinks
  (pay-as-you-go, ~$0.05/1k backlinks; 100x cheaper than Ahrefs API).
- **Trigger:** operator explicitly funds it (~$50 deposit) — user said
  2026-07-01: "alətlər zatən çoxdur… indi belə davam edək".

## Who remembers / who executes (the persistence chain)

1. **This file** — travels with git to every machine; readable by every agent.
2. **brain/** — `recall("seo")` injects these items before any SEO job
   (entry: `decision-seo-deferred-work-registry`).
3. **Claude Code session memory** — `project_seo_engine.md` (auto-loaded each session).
4. **Telegram morning report** (when the autonomous layer runs) — surfacing
   triggered-but-unstarted items is exactly its job.
