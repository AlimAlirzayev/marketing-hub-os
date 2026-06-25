# `prompt_kit/` — Xalq Insurance Digital OS Social Studio

Prompt engineering is the highest-leverage layer in visual marketing
production. This folder is where that knowledge lives as **versioned,
reinforced artifacts** — same idea as `brand_kit/`, applied to language.

## Why this folder exists

Top AI marketing studios in 2026 (Lore Machine, Promise Studio, agencies
running ComfyUI internally) treat prompts as **code**, not as one-off
chat input. Prompts are:

- Hierarchically structured (master_template.md)
- Versioned per campaign
- Audited for regressions (notes.md)
- Translated per model dialect (FLUX ≠ Nano Banana ≠ GPT Image 2)
- Decomposed into reusable anchors (style + negatives)

Without this layer, every campaign rebuilds the prompt from memory — and
quality drifts.

## Layout

```
prompt_kit/
├── master_template.md            The 11-layer skeleton every prompt extends
├── campaigns/
│   └── <campaign-name>/
│       ├── brief.md              Strategy, audience, voice
│       ├── prompts/
│       │   ├── v1.md             Each iteration kept as artifact
│       │   ├── v2.md             ...
│       │   └── notes.md          Why we iterated (lessons)
│       └── outputs/              Sample renders per prompt version
├── style_anchors/                Reusable mood/style blocks
│   └── financial-services-editorial.md
├── negative_templates/           Standard exclusion lists
│   └── ai-tells.md
└── model_dialects/               How each model "listens"
    └── gpt-image-2.md
```

## How to start a new campaign

1. `mkdir campaigns/<new-campaign>/prompts/`
2. Write `brief.md` — strategy, audience, voice rules.
3. Copy `master_template.md` skeleton into `prompts/v1.md`.
4. Fill every layer with specifics. Pull from `style_anchors/` and
   `negative_templates/`.
5. Rephrase for target model using `model_dialects/<model>.md`.
6. Generate ≥3 seeds, audit, write `notes.md`.
7. Iterate to `v2.md` / `v3.md` until production-ready.

## How the renderer consumes prompts

`render_post.py` and `run_codex_gpt_image.py` accept a JSON brief
with a `prompt` field. Generate that JSON from a `vN.md` file in two
ways:

- **Manual:** copy-paste the prompt block from the .md file into a
  brief JSON.
- **Automatic** (future): `compile_prompt.py` reads `vN.md`, applies
  the model-dialect transformation, emits brief JSON.

## Versioning rule

Never edit a `vN.md` in place. Always create `vN+1.md`. Old prompts
are training data for the next iteration.
