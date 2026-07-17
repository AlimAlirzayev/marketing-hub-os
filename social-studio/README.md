# Xalq Insurance Digital OS · Social Studio

The marketing-image layer of Xalq Insurance Digital OS. One natural-language brief in →
one finished, brand-audited, art-direction-aware publishing package out.

## Entry point — a single command

```
/post Gürcüstana yeni qatar reysləri açıldı; biz bunu səyahət sığortası
məhsulumuzla sintez edib instagram postu yaratmaq istəyirik
```

Optional flags:
- `--style <name>` — pin a creative voice (see `prompt_kit/style_dna/`).
  Default is `editorial-documentary`.
- `--moodboard <slug>` — use the campaign's curated reference folder.
  Default: auto-detect from the slug.

The system handles everything from there: creative concept, master
prompt assembly with the chosen style DNA, image generation cascade,
brand-locked compositing, vision-based art-director audit, AZ + EN
captions, format variants, and the final publishing package.

The slash command lives in
[`claude-agents/.claude/commands/post.md`](../claude-agents/.claude/commands/post.md)
— read it to see the full flow.

## The seven layers

```
┌─────────────────────────────────────────────────────────────────┐
│  /post  (claude-agents/.claude/commands/post.md)                │
│         natural-language entry point                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ orchestrates ↓
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌──────────────┐  ┌─────────────────┐  ┌────────────────┐
│  brand_kit/  │  │   moodboard/    │  │  prompt_kit/   │
│              │  │                 │  │                │
│  who is the  │  │  what is the    │  │  how is the    │
│   brand?     │  │   visual taste? │  │  prompt built? │
└──────────────┘  └─────────────────┘  └────────────────┘
       │                  │                    │
       │                  │            ┌───────┴────────┐
       │                  │            ▼                ▼
       │                  │     ┌──────────┐    ┌─────────────┐
       │                  │     │ master_  │    │  style_dna/ │
       │                  │     │ template │    │   (5 voices)│
       │                  │     └──────────┘    └─────────────┘
       │                  │            │                │
       └──────────────────┴────────────┴────────────────┘
                                │
                                ▼
                       ┌────────────────────┐
                       │   render_post.py   │
                       │  (composite layer) │
                       └────────┬───────────┘
                                │
                                ▼
                       ┌────────────────────┐
                       │     critique/      │
                       │ (vision audit)     │
                       └────────┬───────────┘
                                │
                                ▼
                       ┌────────────────────┐
                       │     output/<slug>/ │
                       │  publishing package│
                       └────────────────────┘
```

## Module map

### Brand layer — *who is the brand?*

[`brand_kit/`](brand_kit/) — source of truth.
- `brand.md` — voice, footer rules, palette story, mandatory legal copy.
- `colors.json` — exact HEX values with usage rules.
- `logo-white.png`, `xalqsigorta-logo-official.svg`, footer SVGs.

### Taste layer — *what is THIS campaign's taste?*

[`moodboard/`](moodboard/README.md) — your eye in the system.
- Drop 8–20 reference images into `moodboard/<slug>/refs/`.
- On `/post` invocation, vision-extracts DNA into `extracted.md`.
- Convergent signals → hard prompt anchors. Divergent signals →
  tolerable creative range.

### Voice layer — *what creative voice are we shooting in?*

[`prompt_kit/style_dna/`](prompt_kit/style_dna/README.md) — 5 named voices.

| Style | Use for |
|---|---|
| `editorial-documentary` | Xalq Sigorta default. Travel, heritage, real-life products. |
| `soft-maximalist` | Home, lifestyle, gifting. Slow luxury. |
| `financial-restraint` | B2B, investor-facing, serious products. Calm authority. |
| `caucasus-anthropological` | Regional pride, heritage, sustainability. |
| `emerging-ai-luxury` | Younger sub-brand, current-feeling launches. |

Each style is a `dna.md` describing subject treatment, composition,
light, color, material, mood, lens, plus its lineage and exclusions.

### Prompt assembly layer — *how is the master prompt built?*

[`prompt_kit/`](prompt_kit/) — the prompt-engineering infrastructure.
- `master_template.md` — the 11-layer skeleton every prompt extends.
- `model_dialects/` — per-model phrasing rules (FLUX schnell vs
  GPT Image 2 vs Nano Banana).
- `negative_templates/` — reusable exclusion lists.
- `style_anchors/` — reusable mood reference blocks.
- `campaigns/<slug>/prompts/vN.md` — versioned campaign prompts.

### Composite layer — *brand-locked overlays*

[`render_post.py`](render_post.py) — the deterministic Pillow layer.
- Cover-crop instead of stretch (preserves subject proportions).
- Smooth 2D organic gradient (no visible rectangle seams).
- Logo + headline + sub + body + legal microcopy + contact lockup —
  all from the brand kit, never AI-rendered.

[`compose_for_brief.py`](compose_for_brief.py) — the per-campaign wrapper.
- Overrides headline/sub/body per campaign.
- Generates 1080×1350 (feed) + 1080×1080 (square) + 1080×1920 (story).

### Audit layer — *art-director critique*

[`critique/`](critique/README.md) — the vision-based judge.
- Reads each final composite with vision.
- Scores 5 dimensions: brand fidelity, style DNA fidelity, moodboard
  fidelity, creative bar (the cliché check), technical execution.
- 2+ FAILs OR 3+ MARGINALs → regenerate (one retry per variant).
- The "klassik" failure mode is what this layer exists to catch.

### Output layer

`output/<slug>/` — the publishing package per campaign:
- `<variant>-feed-1080x1350.png`
- `<variant>-square-1080x1080.png`
- `<variant>-story-1080x1920.png`
- `critique-<variant>.md` — the audit report
- (caption text returned in the chat response, not as files)

## How to start a new campaign

1. Think 2 sentences about what you want.
2. (Optional) Drop 8–20 visual references into
   `moodboard/<campaign-slug>/refs/`.
3. Type `/post <your 2 sentences>` in Claude Code.
4. Receive the publishing package — concept, visual(s), caption AZ+EN,
   hashtags, alt-text, variants, audit verdict.

## What's already built

- `brand_kit/` — Xalq Sigorta structured (colors HEX, brand voice, logos,
  footer SVGs, white logo PNG).
- `moodboard/` — structure ready, empty (you populate per campaign).
- `prompt_kit/` — master template, style_dna (5 voices), model dialects,
  negative templates, campaigns/travel-insurance with v1 + v2 prompts.
- `render_post.py` + `compose_for_brief.py` — composite layer working,
  cover-crop + organic gradient fixed.
- `critique/` — rubric + template ready.
- `/post` slash command — full creative-vision flow.

## What is NOT yet wired

- IP-Adapter / reference-image conditioning at generation time (real
  style transfer using moodboard refs as image inputs, not just verbal
  DNA). Requires fal.ai or Replicate API. Documented in
  `prompt_kit/style_dna/README.md` as future capability.
- Brand-trained LoRA on FLUX 2 — the next quality leap. Requires
  ~$30 one-off on fal.ai. Documented in the master plan.

These are the "next layer" investments, not blocking the current system.

## When you come back to this

Read the `/post` slash command first
([`claude-agents/.claude/commands/post.md`](../claude-agents/.claude/commands/post.md)).
Everything else is its dependencies. The slash command tells the future
session exactly how to run the pipeline.

## Google / Gemini Canvas media lane

[`google_media/`](google_media/) connects Social Studio to Gemini Canvas, Nano
Banana, Gemini Omni/Veo, Lyria, Audio Overview, and Audio Studio without putting
an API key in browser code. One evidence-locked campaign JSON produces
draft-only handoffs for copy, image, video, music, and voice:

```powershell
python social-studio\google_media\planner.py doctor
python social-studio\google_media\planner.py build social-studio\google_media\campaign.example.json
```

Google-account entitlement lanes are used first. API or paid work remains an
explicit final-asset choice, and publishing always requires owner approval.
