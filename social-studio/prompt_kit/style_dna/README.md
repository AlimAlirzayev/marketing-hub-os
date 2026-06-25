# `style_dna/` — named creative voices

A library of versioned **creative directions** the system can take. Each
style is a self-contained voice: a real photographer/era/movement encoded
as a structured DNA file the master prompt can pull in.

Where `brand_kit/` answers *"who is the brand?"* and `moodboard/` answers
*"what is the visual taste for THIS campaign?"*, `style_dna/` answers
*"what creative voice are we shooting in?"*. You can argue between styles
the way an art director argues with their team.

## When you use each

`/post <intent> --style <name>` pins the creative voice. If you don't pass
`--style`, the system picks one based on campaign intent + brand defaults.

| Style | When it fits |
|---|---|
| [`editorial-documentary`](editorial-documentary/dna.md) | Travel, real-life products, heritage moments. The Xalq Sigorta default — restrained, observed, premium. |
| [`soft-maximalist`](soft-maximalist/dna.md) | Premium home products, lifestyle, gift-giving moments. Slow luxury. |
| [`financial-restraint`](financial-restraint/dna.md) | Corporate communications, B2B, investor-facing, serious products. Calm authority. |
| [`caucasus-anthropological`](caucasus-anthropological/dna.md) | Regional pride, heritage stories, anything tying to local geography. Rooted. |
| [`emerging-ai-luxury`](emerging-ai-luxury/dna.md) | Younger sub-brand, new product launch, anything that should signal "we're the next thing." |

## Folder per style

```
<style-name>/
├── dna.md           the full creative direction (this is the contract)
├── refs/            reference images — populate as you collect them
│   └── .gitkeep
└── exclusions.md    (optional) style-specific things to avoid
```

The `refs/` folders are seeded empty. As you save Pinterest pulls, MJ
explorations, or campaign references that exemplify each style, drop them
in the corresponding `refs/`. The DNA description is the immediate value;
ref images make it sharper over time.

## How a style DNA enters the master prompt

When `/post` runs with a chosen style:

1. Read `<style>/dna.md` — the full DNA description.
2. Read any images in `<style>/refs/` via vision — pull additional signals.
3. **Override** Layer 9 (Style Anchor) of `master_template.md` with the
   DNA's lineage + reference phrases.
4. **Inject into** Layers 2-7 (camera, lighting, subject, brand props,
   scene, atmosphere) the DNA's specifications where they conflict with
   the campaign defaults. The DNA's voice wins.
5. **Append** the DNA's exclusion list to Layer 11.

The result: same brief, dramatically different image, depending on which
voice you chose.

## Adding a new style

1. `mkdir <new-style>/refs && touch <new-style>/refs/.gitkeep`
2. Write `<new-style>/dna.md` following the structure used by the existing
   styles. Be SPECIFIC. "Soft lighting" is useless; "single key from camera
   left, 4800K, 1:4 ratio, retained shadow modeling on the off-side cheek"
   is a style DNA.
3. Add the row to the table above.
4. Test: `/post <some-intent> --style <new-style>`.

## Versioning

Each style is one file. If you want to evolve the voice, edit `dna.md`
directly — git tracks history. If you want a major fork (e.g. "soft-
maximalist-2027" diverging significantly from the original), make a new
style folder. Old styles stay queryable.
