# Xalq Insurance Digital OS · Copy Studio

The marketing-copy layer of Xalq Insurance Digital OS. Mirror of `social-studio/` for
words. One natural-language brief → one finished, voice-aligned,
senior-edited copy package out.

## Entry point — same single command

```
/post Gürcüstana yeni qatar reysləri açılıb...  --voice ogilvy-product
```

Optional copy flags:
- `--voice <name>` — pin a copywriter voice (see `voice_dna/`)
- `--swipe <slug>` — use the campaign's curated copy references

`/post` invokes copy-studio in parallel with social-studio. Visual and
copy are produced from the same brief but through independent DNA
libraries, then merged at the publishing-package step.

## The five layers (same pattern as social-studio)

```
┌─────────────────────────────────────────────────────────────────┐
│  /post  (claude-agents/.claude/commands/post.md)                │
│         natural-language entry point                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
┌──────────────┐                       ┌─────────────────┐
│ social-studio│                       │  copy-studio    │
│              │                       │                 │
│ visual       │                       │ words           │
└──────────────┘                       └────────┬────────┘
                                                │
            ┌───────────────────┬───────────────┼─────────────────┐
            ▼                   ▼               ▼                 ▼
       ┌──────────┐       ┌──────────┐    ┌──────────┐      ┌──────────┐
       │ copy_kit │       │swipe_file│    │ voice_dna│      │ critique │
       │          │       │          │    │          │      │          │
       │ rules    │       │ your eye │    │ 5 voices │      │ editor   │
       │ + lexicon│       │ on copy  │    │          │      │ audit    │
       └──────────┘       └──────────┘    └──────────┘      └──────────┘
                                                │
                                                ▼
                                       ┌────────────────┐
                                       │ output/<slug>/ │
                                       │ copy package   │
                                       └────────────────┘
```

## Module map

### Knowledge layer — *what are the brand's copy rules?*

[`copy_kit/`](copy_kit/) — source of truth.

- [`voice.md`](copy_kit/voice.md) — Xalq Sigorta tone-of-voice rules
  (headline structure, sentence rules, tonal range, three-language posture)
- [`lexicon.md`](copy_kit/lexicon.md) — preferred + banned words AZ/EN/RU,
  word-count guardrails per asset type
- [`legal_phrases.md`](copy_kit/legal_phrases.md) — locked legal microcopy
  (mandatory, verbatim, per regulatory requirement)
- [`translation_rules.md`](copy_kit/translation_rules.md) — AZ ↔ EN ↔ RU
  adaptation rules

### Taste layer — *what is THIS campaign's copy taste?*

[`swipe_file/`](swipe_file/README.md) — your eye on copy.
- Drop 8–20 reference copy snippets into `swipe_file/<slug>/refs/`
- On `/post` invocation, I read each and extract a structured DNA into
  `extracted.md`
- Convergent signals → hard prompt anchors. Divergent signals →
  tolerable creative range.

### Voice layer — *what creative voice are we writing in?*

[`voice_dna/`](voice_dna/README.md) — 5 named copywriter voices.

| Voice | When it fits |
|---|---|
| [`financial-restraint-az`](voice_dna/financial-restraint-az/dna.md) | Xalq Sigorta default. Sakit professional Azerbaijani, "siz" form, specifics. |
| [`ogilvy-product`](voice_dna/ogilvy-product/dna.md) | Product-led campaigns. Headline = USP, body = evidence. |
| [`halbert-direct-response`](voice_dna/halbert-direct-response/dna.md) | Deadline-driven, conversion-heavy. Specific numbers, P.S. signature. |
| [`apple-jobsian`](voice_dna/apple-jobsian/dna.md) | Brand-prestige moments. ≤4 word headlines. Period as luxury. |
| [`hermes-quiet-luxury`](voice_dna/hermes-quiet-luxury/dna.md) | Heritage / craft positioning. Sensory, observational, slow. |

Each voice is a `dna.md` describing lineage, headline rules, body rules,
lexicon fingerprint, rhythm patterns, examples, and anti-patterns.

### Audit layer — *would a senior editor ship this?*

[`critique/`](critique/README.md) — the senior editor audit.

- Reads each generated copy asset
- Scores 5 dimensions: hook strength, USP clarity, voice match, brevity,
  surprise element
- 2+ FAILs OR 3+ MARGINALs → rewrite (one retry per asset)
- The "voice-compliant but forgettable" failure mode is what this layer
  exists to catch — the user's exact complaint about weak slogans

### Output layer

`output/<slug>/` — the copy package per campaign:
- `headlines.md` — 8-12 headline options ranked
- `caption-az-instagram.md`
- `caption-az-linkedin.md`
- `caption-en-international.md`
- `caption-ru.md` (when relevant)
- `reel-script-30s.md` / `reel-script-15s.md`
- `email-subjects.md`
- `hashtags.md`
- `alt-text.md`
- `critique-<asset>-<v>.md` — per-asset audit reports

## How copy-studio pairs with social-studio

Each `voice_dna` has a natural visual partner from `social-studio/prompt_kit/style_dna/`:

| Copy voice | Visual style |
|---|---|
| `financial-restraint-az` | `editorial-documentary` or `financial-restraint` |
| `ogilvy-product` | `editorial-documentary` |
| `halbert-direct-response` | `emerging-ai-luxury` |
| `apple-jobsian` | `financial-restraint` |
| `hermes-quiet-luxury` | `soft-maximalist` |

`/post` respects these pairings unless overridden.

## Adding a new voice

1. `mkdir copy-studio/voice_dna/<new-voice>/refs && touch <...>/refs/.gitkeep`
2. Write `<new-voice>/dna.md` following the structure used by the existing
   voices. Be SPECIFIC.
3. Add the row to the table above and the pairing table.
4. Test: `/post <some-intent> --voice <new-voice>`.

## Why this folder exists

Top AI marketing studios in 2026 treat copy as code, not as one-off
prompt input. Without the same reinforcement we built for visual, every
caption falls back to my default LLM tone — competent but generic.

This folder is where copy taste becomes a reusable, auditable, versioned
artifact.
