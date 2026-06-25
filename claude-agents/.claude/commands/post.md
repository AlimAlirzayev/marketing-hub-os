---
description: One-shot social post — user describes intent in plain Azerbaijani, the system pulls in moodboard + swipe file, chooses style + voice DNAs, audits as art director + senior editor, returns a finished brand-aligned publishing package
argument-hint: <natural-language brief>  [--style <name>]  [--voice <name>]  [--moodboard <slug>]  [--swipe <slug>]
---

# /post

The user's single command. They write 1–3 sentences of intent. **You**
(Claude Code) do everything else and return a complete, brand-aligned,
dual-audited (visual + copy) publishing package.

This command is the synthesis layer. The system around it (brand_kit,
prompt_kit, moodboard, style_dna, copy_kit, swipe_file, voice_dna,
critique, render_post) does the heavy work; this file tells you how to
weave them.

## Inputs you read every run

**Visual side (social-studio):**
- `social-studio/brand_kit/brand.md`
- `social-studio/brand_kit/colors.json`
- `social-studio/prompt_kit/master_template.md`
- `social-studio/prompt_kit/negative_templates/ai-tells.md`

**Copy side (copy-studio):**
- `copy-studio/copy_kit/voice.md`
- `copy-studio/copy_kit/lexicon.md`
- `copy-studio/copy_kit/legal_phrases.md`
- `copy-studio/copy_kit/translation_rules.md`

**Conditionally (depending on flags + campaign):**
- `social-studio/moodboard/<slug>/refs/*` and `extracted.md`
- `social-studio/prompt_kit/style_dna/<style>/dna.md` + `refs/*`
- `social-studio/prompt_kit/model_dialects/<model>.md`
- `copy-studio/swipe_file/<slug>/refs/*` and `extracted.md`
- `copy-studio/voice_dna/<voice>/dna.md` + `refs/*`

## Steps

### 0. Parse `$ARGUMENTS`

Extract:
- The plain-text brief (everything except flags)
- `--style <name>` — visual style (see `social-studio/prompt_kit/style_dna/`)
- `--voice <name>` — copy voice (see `copy-studio/voice_dna/`)
- `--moodboard <slug>` — visual moodboard
- `--swipe <slug>` — copy swipe file

Defaults if a flag is missing:
- `--style editorial-documentary` (Xalq Sigorta default visual)
- `--voice financial-restraint-az` (Xalq Sigorta default copy)
- If brief implies urgency/deadline → consider `--voice halbert-direct-response`
- If brief implies prestige/launch → consider `--voice apple-jobsian`
- Check `<inferred-slug>/refs/` for both moodboard and swipe; use whichever exists

**Style ↔ voice pairing defaults:**

| Voice | Default visual style |
|---|---|
| `financial-restraint-az` | `editorial-documentary` |
| `ogilvy-product` | `editorial-documentary` |
| `halbert-direct-response` | `emerging-ai-luxury` |
| `apple-jobsian` | `financial-restraint` |
| `hermes-quiet-luxury` | `soft-maximalist` |

If `--voice` is given but `--style` isn't, apply the pairing default.

### 1. Slugify the campaign

From the brief, derive a kebab-case slug. Example:
"Gürcüstana yeni qatar reysləri..." → `xs-georgia-train-new-route`.
This slug identifies the campaign across moodboard, swipe_file,
prompt_kit/campaigns, output folders.

### 2. Moodboard ingestion (visual taste step)

If `social-studio/moodboard/<slug>/refs/` exists and contains images:

a. List every file in `refs/`.
b. Read each ref via vision (`Read <path>` returns rendered image).
c. For each ref, extract verbally: subject treatment, composition,
   light, color story, material rendering, mood vocabulary.
d. Synthesize across all refs using `moodboard/_template/extracted.md`
   as the schema. Write to `moodboard/<slug>/extracted.md`.
e. Pull verbatim "Prompt phrases" — fold into Layer 9 in step 5.

If no refs, skip — style DNA carries direction alone.

### 3. Style DNA load

Read `prompt_kit/style_dna/<style>/dna.md` fully. Note:
- "Reference phrases" → fold verbatim into Layer 9 of master template
- "Style-specific exclusions" → append to Layer 11
- Lineage + DNA layers (camera, light, palette) → override master defaults

If `style_dna/<style>/refs/` has images, read 2-3 for additional signals.

### 4. Creative concept generation

Produce **3 distinct creative concepts** for the brief. Each one short
paragraph naming: subject moment, scene, foreground prop, mood, why
it's topical. Each is a *different angle* — not three variations.

- Mark the strongest as **selected**.
- Note why the other two are reserves.
- The selected concept must fit the active style DNA.

### 5. Master prompt assembly (v2-style)

Build using `master_template.md`'s 11-layer skeleton:
- Layers 1, 4–8: selected concept + brand defaults
- Layers 2–3, 9–10: active style DNA (camera, lighting, anchor, quality)
- Layer 11: stack master ai-tells + style exclusions + moodboard exclusions

Fold moodboard "Prompt phrases" into Layer 9 alongside the style DNA's
lineage block.

Save as `prompt_kit/campaigns/<slug>/prompts/v1.md`. Create
`campaigns/<slug>/brief.md` + empty `notes.md` if needed.

### 6. Model dialect translation

Pick the image-gen channel (see step 7's cascade) and read
`prompt_kit/model_dialects/<model>.md`. Translate v1.md into the dialect:
- GPT Image 2 → structured headers, long form OK
- FLUX 1 dev → tolerates ~2000 chars, comma-or-paragraph hybrid
- FLUX schnell (Pollinations turbo) → compress to ≤1800 chars
- Nano Banana → multi-paragraph natural language, HEX preserved

Save as `experiments/<slug>_brief.json`.

### 7. Visual generation cascade

Try in order, stop at the first success:

a. **Codex CLI** (if `~/.codex/logs_2.sqlite-wal` quiet for 5 min).
   Run: `python social-studio/experiments/run_codex_gpt_image.py
   --brief <slug>_brief.json --out <slug>_raw_<seed>.png`.
   Harvest newest `ig_*.png` from `~/.codex-cli/generated_images/`.
   **Top quality, subscription-leveraged.**

b. **gradio_client → FLUX.1-dev HF Space** — FREE, programmatic,
   no API key. Use longer master prompt (FLUX dev tolerates ~2000 chars).
   Run: `python social-studio/experiments/run_flux_dev_gradio.py
   --brief <slug>_brief.json --seeds 42 1337 7890`.
   ZeroGPU queue 1-2 min idle, up to 10 min peak.
   See `prompt_kit/model_dialects/flux-dev.md`.
   **7.5-8/10 quality. Try BEFORE falling back to Pollinations.**

c. **Pollinations turbo (FLUX schnell)** — use FLUX-compressed brief.
   Three seeds in sequence (parallel triggers 402 rate limit).
   **5-6/10 quality, last automated resort.**

d. **Manual handoff fallback** — save master prompt to
   `social-studio/handoff/<slug>-paste-into-codex.md`.

State the channel used in the response.

### 8. Composite

For each successful raw, run composite layer with campaign-specific
top_tag / headline / subhead / body (drafted in Step 9):

```python
import sys
sys.path.insert(0, "social-studio")
from compose_for_brief import compose_with_text, make_square, make_story
```

Override CAMPAIGN dict with the campaign-specific text.

### 9. Copy package (copy-studio invocation, parallel to visual)

Full copy-studio pass — not a one-line caption generation.

a. **Swipe-file ingestion** — if `copy-studio/swipe_file/<slug>/refs/`
   exists with refs, read each `.md` file and synthesize a DNA into
   `extracted.md` using `swipe_file/_template/extracted.md` as schema.

b. **Voice DNA load** — read `copy-studio/voice_dna/<voice>/dna.md`
   fully. Note lineage, voice fingerprint, headline structure,
   reference phrases, anti-patterns, example block.

c. **Generate the copy package** in the chosen voice. Each asset uses
   the voice DNA's punctuation discipline + lexicon preferences:

   - `headlines.md` — 8-12 headline options ranked
   - `caption-az-instagram.md` — 80-150 words AZ
   - `caption-az-linkedin.md` — slightly longer LinkedIn AZ
   - `caption-en-international.md` — adapted (not translated) EN
   - `caption-ru.md` — if Russian-speaking AZ segment is in scope
   - `reel-script-30s.md` and `reel-script-15s.md` — if reel needed
   - `email-subjects.md` — 5-8 options
   - `hashtags.md` — 3-5 strong, brand + topic + region
   - `alt-text.md` — accessibility text matching the visual

   Cross-check every asset against `copy_kit/lexicon.md` banned-words.
   Verify `copy_kit/legal_phrases.md` mandatory phrases appear
   verbatim where required.

d. **Headline → overlay handoff** — pick the top-ranked headline from
   `headlines.md` + matching sub for the composite overlay step. Pass
   these to `compose_with_text()` in Step 8.

Save all under `copy-studio/output/<slug>/`.

### 10. Variant export

For each composited primary 1080×1350, produce:
- Square 1080×1080 — centered crop
- Story 1080×1920 — primary on canvas with blurred-extended backdrop

Save under `social-studio/output/<slug>/`.

### 11. Dual audit — art-director + senior editor

**Visual side** (per finished composite variant):

a. Open `social-studio/critique/critique_template.md` for the rubric.
b. Read the composite via `Read <path.png>` (vision).
c. Score each of the 5 dimensions (PASS / MARGINAL / FAIL).
d. Decision tree: 2+ FAILs OR 3+ MARGINALs → regenerate (one retry max).
e. Save as `social-studio/output/<slug>/critique-<variant>.md`.

**Copy side** (per copy asset — at minimum headline-set and AZ caption):

a. Open `copy-studio/critique/critique_template.md` for the rubric.
b. Read the asset file directly (text — no vision needed).
c. Score the 5 dimensions: **hook, USP, voice match, brevity, surprise**.
d. Decision tree: 2+ FAILs OR 3+ MARGINALs → rewrite (one retry max).
e. Save as `copy-studio/output/<slug>/critique-<asset>-<v>.md`.

The two audits run independently. A copy rewrite does NOT trigger a
visual regeneration and vice versa. The final response includes both
audit verdicts side-by-side.

### 12. Return the package — one response

Format the response as a publishing package, not a status update:

1. **3 creative concepts** with the chosen one marked
2. **Style DNA + Voice DNA used** (links to dna.md files)
3. **Moodboard + swipe-file signals** (one line each)
4. **Each finished visual displayed inline** (`Read` the PNG)
5. **Channel + quality tier** (Codex / FLUX 1 dev / Pollinations / manual)
6. **AZ caption** in code fence (copy-paste ready)
7. **EN caption** in code fence
8. **Hashtags** + **Alt-text**
9. **Variants list** with file paths
10. **Dual audit verdict** — visual + copy verdicts side-by-side
11. **Notes for next iteration** — what audits revealed to feed back
    into style_dna / voice_dna / moodboard / swipe_file

End with: **"Publish it, or tell me what to change."**

## Rules of engagement

- **Never ask clarifying questions mid-flow.** Interpret. If you guessed
  wrong, the user corrects on the next turn — re-run with the correction.
- **Never tell the user to disable an extension or paste a key.** If the
  cascade has to fall back to manual handoff, that's ONE block to paste.
- **Be brutal in both audits.** "Klassik" (visual) and "voice-compliant
  but forgettable" (copy) are the failure states. Be merciless.
- **Versioning matters.** Every `prompts/vN.md` and copy asset is an
  artifact. Increment, don't overwrite.
- **Treat this command as the only interface.** New capabilities plug
  into the cascade or library — they don't add new commands.

## Example invocations

```
/post Gürcüstana yeni qatar reysləri açıldı, biz bunu səyahət sığortası
məhsulumuzla sintez edib instagram postu yaratmaq istəyirik
```

```
/post Yeni KASKO endirim kampaniyası, son 30 gün  --voice halbert-direct-response
```

```
/post Şəki çayçılığı heritage kampaniyası  --voice hermes-quiet-luxury
       --style caucasus-anthropological  --moodboard xs-sheki-2026
```

```
/post Xalq Sigorta 20 illik yubileyi  --voice apple-jobsian  --style financial-restraint
```
