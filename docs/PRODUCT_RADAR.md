# Product Radar — architecture & workflow watchlist

Sources we mine for **how they are built** — product architecture, workflows,
UX patterns, AI orchestration — not for their content. The counterpart of
`idea-studio/swipe_file/` (which steals *creative craft*); this file steals
*product craft* for our own Marketing OS (Atelier/hub, studios, gateway).

Rules: study public pages/docs/demos only; map every stolen pattern to the
Ramin-OS organ that would absorb it; a pattern graduates from this list into
a real backlog item (brain decision / project doc) or gets dropped — no
zombie rows. Added 2026-07-16 (user request, alongside the AOTW swipe organ).

| Product | What it is | What to mine (architecture / workflow) | Maps to | Status |
|---|---|---|---|---|
| **Predis.ai** | All-in-one AI social content hub: prompt or e-commerce URL in → brand-cohesive posts out (statics, carousels, reels, captions, hashtags) for IG/TikTok/LinkedIn/FB | URL → **brand-kit auto-extraction** flow; multi-brand **workspaces**; team **approval pipelines**; built-in scheduling calendar; AI **competitor-analysis dashboard** — the "one front door" product shape | Atelier/hub (workspace + approval model), social-studio (brand_kit auto-fetch), ads-studio (competitor panel), /publish (calendar) | research-pending |
| **Holo AI** (tryholo.ai) | "Always-on content engine": enter brand URL → maps the whole website → high-volume ads, newsletters, social posts | **Site-mapping ingestion** (website as the brand corpus); **swipe-to-approve** curation UI (human approves at card speed); always-on generation loop | Brand Brain / knowledge core (site → corpus), Atelier Creative Lab (approve UI), autonomous layer (always-on loop) | research-pending |
| **HOLA AI** | Personalized AI video communications: training videos, product demos, visual marketing (e-commerce, healthcare) | **Personalized-video pipeline** (data → per-recipient video); template + variable architecture for video at scale | media_studio (directed video), meta-capi/CRM data as personalization source | research-pending |
| **Halo AI** | Creator/influencer collaboration hub: onboard brands, recruit pre-screened local creators, manage briefs, live engagement dashboards | **Brief → creator → live-metrics** loop; creator pre-screening/scoring model; real-time campaign dashboard shape | influencer-hunter (next phase: from *finding* to *managing* creators), ads-studio dashboard patterns | research-pending |

## How to run a deep-dive (when a row is picked)

1. `url-content-access` chain on the product's site/docs/demo videos
   (WebFetch → yt-dlp → ffmpeg frames → LOOK — never trust text alone).
2. Write findings as: the pattern, why it works, the Ramin-OS organ that
   absorbs it, smallest free-first version we could build.
3. Persist: `python -m brain remember` (type `pattern`) + update the row's
   status; graduate real build ideas into the project's own doc/backlog.
