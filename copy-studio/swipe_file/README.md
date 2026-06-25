# `swipe_file/` — copy moodboard

Your **copywriting eye** entered the system. Same idea as
`social-studio/moodboard/` but for words. You drop copy snippets you
find yourself stopping at — print ads, social captions, brand pages —
and I extract their DNA.

## How you use it

1. Pick a campaign — say `xs-travel-2026`.
2. Make `swipe_file/xs-travel-2026/refs/`.
3. Drop 8–20 copy references into `refs/`. Each ref is a single
   `.md` file with:
   - The copy itself (headline + sub + body if available)
   - The brand and where you found it
   - One line on what specifically made you save it

Example ref file `01-hermes-travel.md`:

```markdown
# Source: Hermès "Petit h" 2024 catalog, p.12

## Copy

Bir yolun üstündə bir nəfər. Yastı işıq. Yarpaqlar.

Vaxt — onun cibində.

## Why I saved it

The way "vaxt onun cibində" lands without explaining itself. The
catalog never tells you what the product is doing for you — it shows
you a moment, and you fill in the meaning.
```

4. Type `/post <intent>` — the slash command detects the swipe file,
   reads each ref, extracts a structured DNA into `extracted.md`, and
   uses it alongside the chosen `voice_dna` when generating copy.

## What I extract per ref

For each copy snippet I read:

- **Sentence rhythm** (length variance, breath pattern)
- **Punctuation fingerprint** (does it use em-dashes? semicolons?)
- **Verb register** (active vs passive, sensory vs assertive)
- **Lexical choices** (specific words that signal the voice)
- **Brand presence** (does the brand name appear? where? how often?)
- **Hook style** (how does the first sentence open?)
- **CTA posture** (hard / soft / absent)
- **Hashtag posture** (if visible)

Then I synthesize:

- **Convergent signals** — what every ref shares (these become hard
  prompt anchors)
- **Divergent signals** — the range you tolerate
- **Phrases to fold verbatim** into the master copy prompt
- **Specific exclusions** — words / patterns your refs systematically
  avoid

The output is `<campaign>/extracted.md` — versioned, auditable,
editable. You can correct my read of your taste; the system sharpens
each pass.

## Why this beats "describe the copy style you want"

Words about copywriting style ("crisp", "premium", "considered") sound
concrete but mean different things to different writers. A real
reference passage is unambiguous — *this exact rhythm, this exact
punctuation*. The LLM lands where the references land, not where my
training data drifts.

## Folder layout

```
swipe_file/
├── README.md                                this file
├── _template/                               copy this for a new campaign
│   ├── refs/                                (empty — drop refs here)
│   │   └── .gitkeep
│   └── extracted.md                         (auto-written by /post)
└── <campaign-slug>/                         one per campaign
    ├── refs/
    │   ├── 01-hermes-travel.md
    │   ├── 02-apple-ipod.md
    │   └── 03-ogilvy-rolls-royce.md
    └── extracted.md
```

## What NOT to do

- ✗ Don't drop refs that clash wildly with each other. If your refs
  span "Ogilvy long-copy" AND "Apple two-word headlines", the average
  is muddled. Pick a coherent direction.
- ✗ Don't drop >20 refs — 8 carefully chosen ones produce sharper
  DNA than 30 unfocused ones.
- ✗ Don't include refs in languages other than AZ / EN / RU unless
  you can also describe what makes them work — the LLM otherwise just
  extracts surface features.
- ✗ Don't include visual references — those go in
  `social-studio/moodboard/`. This folder is for words only.
