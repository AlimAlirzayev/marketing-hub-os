# `moodboard/` — visual taste pipeline

This is where **your eye** becomes part of the system. The static training
data inside me has a fixed aesthetic frozen at my training cutoff. Without
your moodboard, every campaign drifts toward the same competent-but-classic
defaults you already complained about.

The moodboard layer changes that: you drop visuals you like, I extract their
**visual DNA**, and `/post` weaves that DNA into the master prompt. The system
becomes a mirror of *your* current taste, not my default one.

## How you use it (real, simple)

1. Pick the campaign — say `xs-travel-2026`.
2. Make a folder: `moodboard/xs-travel-2026/refs/`
3. Drop 8–20 images into `refs/`. Sources are up to you:
   - Pinterest saves (right-click → Save image)
   - Midjourney Explore screenshots
   - Behance project screenshots
   - Ad campaign hero shots
   - Photographer portfolio screenshots
   - Anything you find yourself stopping at
4. Name them anything (`01-pinterest.jpg`, `magnum-tbilisi.png`, etc.). Order
   doesn't matter. Quality matters more than quantity — 10 carefully chosen
   beats 50 random.
5. Type `/post <intent>` — `/post` will detect the campaign's moodboard,
   read every ref with vision, and extract a structured DNA into
   `extracted.md` before generating anything.

## What I extract (the DNA — see _template/extracted.md schema)

For each ref I read:
- **Subject treatment** — pose, gaze, framing, scale
- **Composition** — rule-of-thirds, leading lines, negative space, depth layering
- **Light** — source direction, hardness, color temperature, key-to-fill ratio
- **Color story** — palette signature, saturation, contrast
- **Material rendering** — texture, surface treatment, fabric/skin/metal
- **Mood vocabulary** — emotional register, pace, intimacy distance

Then I synthesize:
- **Convergent signals** — what every ref shares (these become hard prompt anchors)
- **Divergent signals** — the range you tolerate (these become campaign-mood flexibility)
- **Prompt phrases** — the literal text I'll fold into Layer 9 of the master template
- **Specific exclusions** — what your refs systematically avoid

The output is `<campaign>/extracted.md` — versioned, auditable, editable. You
can correct my read of your taste; the system gets sharper each pass.

## Why this beats "say what style you want"

Words about style ("Mont Blanc 2024", "editorial documentary") sound concrete
but mean different things to different models. A real ref image is unambiguous
— "this exact mood, this exact light." The model's latent space lands where
the refs land, not where my training data drifts.

This is why top studios maintain **physical moodboards** before shooting. The
system now matches that working method.

## Folder layout

```
moodboard/
├── README.md                              this file
├── _template/                             copy this for a new campaign
│   ├── refs/                              (empty — drop images here)
│   └── extracted.md                       (auto-written by /post)
└── <campaign-slug>/                       one per campaign
    ├── refs/
    │   ├── 01-*.jpg
    │   └── ...
    └── extracted.md
```

## What NOT to do

- ✗ Don't drop refs that conflict wildly with each other — pick a coherent
  visual direction. If your refs span "editorial documentary" AND "neon
  cyberpunk", I'll average them and the result will be neither.
- ✗ Don't expect me to handle 100 refs — 8–20 carefully chosen ones produce
  better DNA than a vast unfocused dump.
- ✗ Don't include refs with text/typography you want to emulate. Typography
  decisions live in `brand_kit/`, not here. Moodboard is for **photographic
  and compositional** signals only.
