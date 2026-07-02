# `voice_dna/` — named copywriter voices

A library of versioned **copywriting voices** the system can write in.
Mirrors `social-studio/prompt_kit/style_dna/` for the visual side: each
voice is a real copywriter / tradition / era encoded as a structured DNA
file the generator can pull in.

## When you use each

`/post <intent> --voice <name>` pins the copy voice. If you don't pass
`--voice`, the system picks one based on the campaign type + product
category.

| Voice | Category | When it fits |
|---|---|---|
| [`ogilvy-product`](ogilvy-product/dna.md) | house | Product-led campaigns. The brand's flagship "headline = USP" voice. Default for Xalq Sigorta product comms. |
| [`halbert-direct-response`](halbert-direct-response/dna.md) | direct-response | Deadline-driven, conversion-heavy, time-limited offers. Specific numbers, hard CTAs. |
| [`apple-jobsian`](apple-jobsian/dna.md) | brand-story | Brand-prestige moments. Headline ≤4 words, period as punctuation, restraint as luxury. |
| [`hermes-quiet-luxury`](hermes-quiet-luxury/dna.md) | brand-story | Heritage / premium positioning. Sensory, observational, catalog poetry. |
| [`financial-restraint-az`](financial-restraint-az/dna.md) | house | The Xalq Sigorta default for AZ copy. Sakit professional Azerbaijani, no hype, "siz" form. |
| [`joanna-wiebe`](joanna-wiebe/dna.md) | conversion | Landing/sales pages, sign-up flows. Voice-of-customer led, clarity-first. |
| [`chase-dimond`](chase-dimond/dna.md) | email | Retention email flows + campaigns. Framework-built, single-goal, mobile-first. |
| [`cole-schafer`](cole-schafer/dna.md) | brand-story | Hero lines, manifestos. Reads like poetry, sells like Ogilvy. |
| [`eddie-shleyner`](eddie-shleyner/dna.md) | craft-hooks | Hooks, micro-essays, captions. One idea per sentence, bucket brigades. |
| [`justin-welsh`](justin-welsh/dna.md) | personal-brand | Thought-leadership / founder content for the feed. Hook-led, one lesson per post. |
| [`nicolas-cole`](nicolas-cole/dna.md) | craft-hooks | Structured long-form digital writing. 1-3-1 rhythm, 5-line intro, data-driven. |
| [`dickie-bush`](dickie-bush/dna.md) | craft-hooks | Atomic essays — one idea, ~250 words, complete. Ship over polish. |
| [`laura-belgray`](laura-belgray/dna.md) | email | Personality-driven list email. Story-first, funny in the details. |
| [`chris-orzechowski`](chris-orzechowski/dna.md) | email | Back-end retention email. Big promise + objections, no-discount recovery. |
| [`chris-do`](chris-do/dna.md) | brand-story | Consultative brand narrative. Sell without selling, customer as hero. |
| [`sahil-bloom`](sahil-bloom/dna.md) | brand-story | Framework storytelling. Story opens, named framework carries. |
| [`vikki-ross`](vikki-ross/dna.md) | brand-story | Brand voice systems. Talk *to* someone; also the meta-voice for TOV guidelines. |
| [`jasmin-alic`](jasmin-alic/dna.md) | personal-brand | Community-first LinkedIn. Last-line-first hooks; comments as the stage. |
| [`ana-paula-picasso`](ana-paula-picasso/dna.md) | niche | Fintech/finance explainers. Complex made accessible, data-anchored. |

> **Universal library, two layers + a registry.** Voices describe *how a
> copywriter sounds*. The principles that hold *regardless of voice*
> (awareness stages, voice-of-customer, Sutherland's psycho-logic, hook
> discipline, copy structures, the editorial bar) live one level down in
> [`copy_kit/frameworks.md`](../copy_kit/frameworks.md) — loaded alongside
> whichever voice is active. The full catalog (grounded + planned) is the
> machine-readable [`index.json`](index.json), the single source of truth
> any product can query by `category` and `status`.
>
> The library is seeded from the "Top 40 LinkedIn copywriters" source: the
> grounded voices above are built from each author's real public work; the
> rest are categorized as `status: "planned"` in `index.json` — a
> documented roadmap, not invented files. **Rule: never fabricate a voice
> — ground every one in the real author's published material.**

## Folder per voice

```
<voice-name>/
├── dna.md            the full voice direction (this is the contract)
├── refs/             swipe-file references — populate as you collect
│   └── .gitkeep
```

Each `dna.md` describes: lineage, headline rules, body rules, lexicon
fingerprint, rhythm patterns, what to avoid, and reference examples.

## How a voice DNA enters the copy generation

When `/post` invokes copy generation with a chosen voice:

1. Read `<voice>/dna.md` — the full voice description.
2. Read any examples in `<voice>/refs/` — additional signals.
3. Compose all copy assets (headline, sub, body, caption AZ + EN,
   hashtags, alt-text, reel scripts) **in that voice**.
4. Run critique pass against the voice DNA + `copy_kit/voice.md` brand
   rules + `copy_kit/lexicon.md` banned-words list.

The result: same brief, dramatically different copy depending on voice.

## Pairing voices with visual styles

Each copywriter voice has a natural visual partner from
`social-studio/prompt_kit/style_dna/`:

| Copy voice | Pairs with visual style |
|---|---|
| `ogilvy-product` | `editorial-documentary` |
| `halbert-direct-response` | `emerging-ai-luxury` (urgency + new energy) |
| `apple-jobsian` | `financial-restraint` (restraint × restraint) |
| `hermes-quiet-luxury` | `soft-maximalist` |
| `financial-restraint-az` | `editorial-documentary` or `financial-restraint` |
| `joanna-wiebe` | `editorial-documentary` or `financial-restraint` |
| `chase-dimond` | `editorial-documentary` or `soft-maximalist` |
| `cole-schafer` | `hermes-quiet-luxury` or `soft-maximalist` |
| `eddie-shleyner` | `editorial-documentary` or `financial-restraint` |
| `justin-welsh` | `editorial-documentary` or `financial-restraint` |
| `nicolas-cole` | `editorial-documentary` |
| `dickie-bush` | `editorial-documentary` or `financial-restraint` |
| `laura-belgray` | `soft-maximalist` |
| `chris-orzechowski` | `editorial-documentary` |
| `chris-do` | `financial-restraint` or `editorial-documentary` |
| `sahil-bloom` | `editorial-documentary` |
| `vikki-ross` | brand-dependent (consistency within the brand first) |
| `jasmin-alic` | `editorial-documentary` or `financial-restraint` |
| `ana-paula-picasso` | `financial-restraint` or `editorial-documentary` |

`/post` will respect these pairings unless overridden with both
`--voice` and `--style` flags.

## Adding a new voice

1. `mkdir <new-voice>/refs && touch <new-voice>/refs/.gitkeep`
2. Write `<new-voice>/dna.md` following the structure used by the existing
   voices. Be SPECIFIC — "more casual" is useless; "average sentence
   length 6 words, no semicolons, contractions allowed" is a voice DNA.
3. Add the row to the table above and the pairing table.
4. Test: `/post <some-intent> --voice <new-voice>`.

## Versioning

Each voice is one DNA file. Edit `dna.md` directly — git tracks history.
For a major fork, make a new voice folder. Old voices stay queryable.
