# `voice_dna/` — named copywriter voices

A library of versioned **copywriting voices** the system can write in.
Mirrors `social-studio/prompt_kit/style_dna/` for the visual side: each
voice is a real copywriter / tradition / era encoded as a structured DNA
file the generator can pull in.

## When you use each

`/post <intent> --voice <name>` pins the copy voice. If you don't pass
`--voice`, the system picks one based on the campaign type + product
category.

| Voice | When it fits |
|---|---|
| [`ogilvy-product`](ogilvy-product/dna.md) | Product-led campaigns. The brand's flagship "headline = USP" voice. Default for Xalq Sigorta product comms. |
| [`halbert-direct-response`](halbert-direct-response/dna.md) | Deadline-driven, conversion-heavy, time-limited offers. Specific numbers, hard CTAs. |
| [`apple-jobsian`](apple-jobsian/dna.md) | Brand-prestige moments. Headline ≤4 words, period as punctuation, restraint as luxury. |
| [`hermes-quiet-luxury`](hermes-quiet-luxury/dna.md) | Heritage / premium positioning. Sensory, observational, catalog poetry. |
| [`financial-restraint-az`](financial-restraint-az/dna.md) | The Xalq Sigorta default for AZ copy. Sakit professional Azerbaijani, no hype, "siz" form. |

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
