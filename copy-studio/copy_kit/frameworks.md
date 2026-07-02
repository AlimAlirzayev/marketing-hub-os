# `frameworks.md` — the principles layer (universal)

Voices in `voice_dna/` describe **how a copywriter sounds**. This file
describes **what's true about persuasion regardless of voice**. It is the
lens that sits *under* every voice: a Wiebe landing page and a Schafer
brand line are written in different voices but obey the same underlying
laws.

Brand-agnostic by design — one codebase serves every brand (see the
central BRAND config). When `/post` or any future product generates copy,
it loads the chosen `voice_dna/` **and** these frameworks; the voice sets
the surface, the frameworks set the structure and the psychology.

> Grounded, not invented. Each principle traces to a named source. Where a
> living author is cited, the claim is from their public, published work.

---

## 1. Awareness — match the message to the reader (Eugene Schwartz)

The single most important decision before writing a word: *how aware is
the reader of their problem and your solution?* You cannot sell at the
same intensity to a stranger and to someone with their card out.

| Stage | Reader knows… | The copy leads with… |
|---|---|---|
| **Unaware** | nothing — no felt problem | a story / a tension they recognize |
| **Problem-aware** | the pain, not the fix | the problem, named vividly |
| **Solution-aware** | fixes exist, not yours | how your category wins |
| **Product-aware** | your product, not convinced | proof, differentiation, offer |
| **Most-aware** | everything — needs a nudge | the offer + the reason to act now |

**Rule:** every headline is written *for a stage*. A most-aware offer
shown to an unaware reader feels pushy; an unaware story shown to a
most-aware reader wastes their time. (Schwartz, *Breakthrough
Advertising*.)

---

## 2. Voice of Customer — assemble, don't invent (Joanna Wiebe)

The best line in any piece is usually one the customer already said.

- **Listen, don't write.** Mine reviews, support tickets, sales calls,
  interviews. The reader's own words out-convert anything written at the
  desk.
- **Anchor to the moment of highest tension** — the hyper-contextual,
  three-dimensional scene where the problem is felt most vividly. Not the
  category ("data loss"), the scene ("the report's due in an hour and the
  file won't open").
- **Specific beats vague.** "Details earn trust." Numbers, names, real
  scenarios — never "amazing", "seamless", "world-class".

---

## 3. Psycho-logic — sell the perception, not the product (Rory Sutherland)

"Logic is what you use when you want to be right; psycho-logic is what you
use when you want to be successful." (*Alchemy*.)

- **Reframe, don't restate.** Change the perception without changing the
  facts. The premium option beside the economy option turns a price into
  a *feeling of value*.
- **Small changes solve huge problems.** A word, an order, a default
  often beats an expensive "real" fix. Test the cheap psychological lever
  before the costly engineering one.
- **The opposite of a good idea can be another good idea.** Don't assume
  the rational benefit is the selling point — often it's the irrational,
  emotional, or signaling value that moves people.
- **For insurance / finance specifically:** people don't buy cover, they
  buy *the absence of dread*. Sell peace of mind and loss-aversion
  framing, not feature lists.

---

## 4. Hook discipline — earn the second sentence

Every sentence's only job is to get the next one read (the "slippery
slide", Joe Sugarman).

- **The first line is a door, not a summary.** It creates a gap the
  reader needs to close. Write the body first, *then* write the hook
  (Justin Welsh's practice — it's easier to hook what already exists).
- **Bucket brigades** (Eddie Shleyner / Sugarman's "seeds of curiosity"):
  drop a short, conversational line every few paragraphs — "Here's the
  thing." "But it gets worse." "So what happened?" — to keep momentum.
- **One idea per sentence.** Vivid, concrete, emotional. Clarity is the
  cornerstone of persuasion; if they have to decode it, you lost them.

---

## 5. Copy structures — never write from scratch (Chase Dimond's rule)

Reach for a proven skeleton, then fill it in the chosen voice.

- **PAS** — Problem → Agitate → Solve. The default for problem-aware copy.
- **PASTOR** — Problem, Amplify, Story, Testimony, Offer, Response.
- **AIDA** — Attention, Interest, Desire, Action. The classic funnel.
- **BAB** — Before → After → Bridge. Great for transformation offers.
- **4 Ps** — Promise, Picture, Proof, Push.

The framework guarantees the structure is sound; the voice and the VOC
data make it *theirs*. Structure is universal; voice is the fingerprint.

---

## 6. Editorial standard — the quality bar (Ann Handley)

Before anything ships:

- **Clarity sweep first** (Wiebe): is the one thing this must say
  unmistakable? Cut everything fighting it.
- **Useful + empathetic + inspired + brave** (Handley's bar for "good"):
  does it help the reader, see from their side, sound human, and dare to
  be specific?
- **Show the work, don't claim it.** Replace adjectives with evidence.
- **Read it aloud.** If you stumble, the reader stumbles.

---

## How a generation uses this file

1. Decide the reader's **awareness stage** (§1) → it gates everything.
2. Pull **VOC** language if available (§2); if not, flag the gap.
3. Choose a **structure** (§5) appropriate to the stage and medium.
4. Apply a **psycho-logic reframe** (§3) to the core promise.
5. Write in the active `voice_dna/` voice, with **hook discipline** (§4).
6. Run the **editorial standard** (§6) as the critique pass, alongside
   `copy_kit/voice.md` and `copy_kit/lexicon.md`.

## Sources

- Eugene Schwartz, *Breakthrough Advertising* — five stages of awareness.
- Joanna Wiebe / Copyhackers — voice of customer, moment of highest
  tension, clarity sweep. https://copyhackers.com/conversion-copywriting-defined/
- Rory Sutherland, *Alchemy* — psycho-logic, reframing, small changes.
- Eddie Shleyner / VeryGoodCopy — bucket brigades, one idea per sentence.
  https://www.verygoodcopy.com/microlessons
- Justin Welsh — write the body first, then the hook.
  https://www.justinwelsh.me/newsletter/my-writing-process-for-162-597m-impressions-on-linkedin
- Chase Dimond — "never write copy from scratch; use a framework."
  https://www.chasedimond.com/10-proven-copywriting-frameworks
- Ann Handley, *Everybody Writes* — the editorial quality bar.
