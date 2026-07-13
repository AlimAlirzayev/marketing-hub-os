# `idea-studio/` — the creative-direction layer

The **big-idea brain** of the marketing OS. Every other studio *executes*
(social-studio renders images, copy-studio writes words, mediaforge
directs video, audio-studio makes sound). This studio decides **what is
worth executing**: the insight, the tension, the artistic device, the
emotional arc — the concept that makes a piece feel like art and travel
like a meme.

Born from a simple complaint: *"we can execute, but where is the creative
spark — the bədii hiss, the meme, the aesthetic harmony, all fused?"*
This layer is the answer. Brand-agnostic, like the rest of the OS.

## Where it sits in the pipeline

```
intent (1 sentence)
   │
   ▼
┌─────────────────────────────────────────────┐
│ idea-studio  →  N scored CONCEPTS           │   /idea
│ (insight → tension → device → concept)      │
└─────────────────────────────────────────────┘
   │  winning concept = the creative brief
   ▼
social-studio (image) · copy-studio (words) · mediaforge (video) · audio-studio (sound)
   │
   ▼
critique layers → output → /publish
```

`/post` and mediaforge keep working without it (a concept is optional),
but any campaign that needs to *feel* rather than just inform should
start here.

## The layers (same pattern as the other studios)

| Layer | What lives there |
|---|---|
| [`creative_dna/`](creative_dna/) | Named creative **traditions** — real schools of advertising art, each a structured `dna.md` (grounded in the actual people/work, never invented). The idea-level mirror of `copy-studio/voice_dna/`. |
| [`idea_kit/`](idea_kit/) | The universal toolbox under every tradition: artistic **devices**, **meme mechanics**, **audiovisual harmony** rules, and the **effectiveness evidence** (why emotion wins — with numbers). |
| [`critique/`](critique/) | The idea rubric — concepts are scored before anything is rendered. Kill weak ideas while they're still cheap. |
| [`output/`](output/) | Generated concept packages per campaign (`<slug>/concepts.md`). |

## How `/idea` uses it

1. Read the brief + active brand config; recall `brain/` lessons.
2. Read `idea_kit/frameworks.md` (the ideation process) + relevant
   `creative_dna/` traditions (2–3, chosen by campaign type or flags).
3. Generate **5+ genuinely different concepts** — each one: insight,
   tension, device, one-line pitch, execution sketch across studios,
   meme potential.
4. Score every concept with `critique/idea_rubric.md`. Kill the weak.
5. Expand the winner into a **creative brief** the execution studios
   accept (`/post`, mediaforge director, audio).

## Registry

`creative_dna/index.json` — machine-readable list of traditions with
`category` and `status` (`grounded` | `planned`), same philosophy as
`copy-studio/voice_dna/index.json` and `services.json`: single source of
truth, no enumeration from memory.

## Rules

- **Grounded, never invented.** Every tradition's `dna.md` traces to the
  real school's published work and words. Verbatim quotes only when
  actually sourced.
- **The idea is judged before the pixels.** Nothing goes to render
  without passing the rubric.
- **One tension per concept.** A concept that says two things says
  nothing (sacrifice-and-focus — see `idea_kit/frameworks.md`).
- **Meme potential is a scored dimension, not an afterthought.**
