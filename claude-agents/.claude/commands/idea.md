---
description: Creative-direction pass — one sentence of intent in, N scored big-idea concepts out; the winner becomes the creative brief that /post and mediaforge execute
argument-hint: <natural-language intent>  [--tradition <slug>]  [--count <n>]  [--for <post|video|both>]
---

# /idea

The concept layer. `/post` makes assets; `/idea` decides **what is worth
making**. The user gives one sentence; you return genuinely different,
scored concepts and expand the winner into a creative brief the
execution studios accept.

## Inputs you read every run

- `idea-studio/creative_dna/index.json` — pick 2–3 traditions (never
  enumerate from memory; the registry is the truth)
- The chosen traditions' `dna.md` files — devices + anti-patterns
- `idea-studio/critique/idea_rubric.md` — the scoring contract
- `idea-studio/idea_kit/*` — whatever exists (frameworks, harmony,
  evidence; some are research-pending per index.json)
- Active brand config + `copy-studio/copy_kit/lexicon.md` (banned words
  constrain concepts too)
- `idea-studio/swipe_file/adsworld-<industry>.md` — real, current campaign
  reference (Ads of the World; insurance is the home industry). If missing or
  stale, refresh: `python idea-studio/adsworld.py --deep 5`. Use it two ways:
  **freshness check** (has a major brand already shipped this idea?) and
  **craft theft** (structures, devices, tensions worth adapting) — never copy
  an execution.
- `python -m brain recall "<intent>"` — past lessons before ideating

## Steps

### 1. Parse `$ARGUMENTS`

- The intent (everything except flags)
- `--tradition <slug>` pins a creative tradition; otherwise choose 2–3
  by job type: product truth → `bernbach-ddb`; brand feeling →
  `wieden-kennedy`; small budget/big noise → `droga-provocation`;
  owned-channel building → `internet-native-meme`; warmth/care →
  `caring-hand-miniature`
- `--count <n>` concepts (default 5), `--for` target (default both)

### 2. Find the insight before the ideas

Write down, in two lines each: the **human truth** (what the audience
actually feels — not what the brand wants them to feel) and the
**product truth** (the verifiable fact worth dramatizing). If no product
truth exists, STOP and say so — do not polish a lie (Bernbach rule).

### 3. Generate N concepts — genuinely different

Each concept uses a **different device** (from the traditions' device
tables), not the same idea re-skinned. Format per concept:

```
CONCEPT <n>: <one-line pitch>
insight / tension / device+tradition
execution sketch: visual (social-studio style), video (mediaforge, 2-3
scene beats), copy angle (copy-studio voice), sound cue (audio-studio)
meme potential: <what's remixable about it>
```

### 4. Score with the rubric — and actually kill

Apply `critique/idea_rubric.md` honestly. Show the scores. Kill the
killed. If everything survives, you scored dishonestly — the rubric
exists to say no.

### 5. Expand the winner into the creative brief

One page: the idea, the one truth, the device, per-studio direction
(`/post --style X --voice Y` flags included, mediaforge scene grammar if
video, audio brief), and what would make it fail (the anti-patterns to
watch from the tradition's dna.md).

Save everything to `idea-studio/output/<slug>/concepts.md`. Never
auto-render; the user picks what goes to execution.

## Rules

- **Grounded devices only** — name the device and tradition; no
  freestyle "creativity" unmoored from the library.
- **One tension per concept** (sacrifice-and-focus).
- **The rubric's kills are real.** Weak ideas die here, cheaply.
- Concepts in Azerbaijani for the user; file content EN per repo
  convention (user-facing deliverables AZ).
