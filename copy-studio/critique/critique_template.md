# Critique template — senior editor audit rubric

When `/post` calls this layer for a copy asset, Claude reads the
generated text and writes the audit using this template. One audit per
asset (headline-set, caption-AZ, caption-EN, reel-script, etc.).

The audit is harsh on purpose. The senior editor's job is to catch what
the generator missed.

---

## Audit context

- **Campaign:** `<slug>`
- **Asset:** `<filename or label>`
- **Voice DNA in effect:** `<voice>` (link to dna.md)
- **Swipe file used:** `<slug>` if any (link to extracted.md)
- **Date:** `<YYYY-MM-DD>`

---

## Dimension 1 — Hook strength

The first sentence is the entire piece's fight to be read. Does it win?

- **PASS** — first sentence makes me want to read the next line. Either
  by a specific (number, name, image) or by a curiosity gap.
- **MARGINAL** — first sentence is voice-compliant but generic. I could
  read it or not.
- **FAIL** — first sentence is brand-led ("Xalq Sigorta ilə..."), or a
  cliché ("Bu gün biz...") or a rhetorical question that doesn't
  earn the reader's time.

**Verdict:** PASS / MARGINAL / FAIL
**One-line note (quote the opening + why it works or doesn't):** ...

---

## Dimension 2 — USP clarity

What is the ONE specific thing this copy commits to? If you can't name
it in one sentence, neither will the reader.

- **PASS** — one specific commitment is clear (a date, a duration, a
  number, a service guarantee). Removing it would change the meaning.
- **MARGINAL** — there's a vague benefit named (e.g. "calm journey")
  but no specific anchor. The reader could substitute any insurance
  brand.
- **FAIL** — multiple competing claims, or no claim, or only adjectives.

**Verdict:** PASS / MARGINAL / FAIL
**One-line note (state the USP you can extract — or note its absence):** ...

---

## Dimension 3 — Voice match

Does this copy actually land in the chosen `voice_dna/<voice>/dna.md`?

Pull 3 specific signals from the voice DNA's "Voice fingerprint" section
and check them:

- [ ] Sentence length / rhythm pattern matches
- [ ] Punctuation discipline matches (especially: exclamation marks)
- [ ] Lexical choices align (use the voice's preferred / avoided words)
- [ ] None of the voice's anti-pattern phrases appear

Cross-check against `copy_kit/lexicon.md` banned words.

- **PASS** — voice is recognizable; could be attributed to this voice DNA
  blind.
- **MARGINAL** — voice-shaped but missing 1-2 signature signals.
- **FAIL** — could be from any voice; or contains anti-pattern words.

**Verdict:** PASS / MARGINAL / FAIL
**One-line note (cite the voice DNA signal that's met or violated):** ...

---

## Dimension 4 — Brevity

Is every sentence carrying its weight? If you cut a word, would the
piece be worse?

- **PASS** — no padding. Each sentence has a specific job. The copy
  could be 10% longer or 10% shorter and the cuts would hurt.
- **MARGINAL** — voice-compliant length, but 1-2 sentences are saying
  the same thing twice. Could lose 15% without loss.
- **FAIL** — adjective stacking, repetition, filler ("As you can see...",
  "It's important to note that..."). 25%+ could be cut.

Also check against `copy_kit/lexicon.md` word-count guardrails for the
asset type.

**Verdict:** PASS / MARGINAL / FAIL
**One-line note (name the sentence that's not earning its place — or
confirm nothing is wasted):** ...

---

## Dimension 5 — Surprise

Is there ONE element a reader pauses on? An unexpected word, a turn of
phrase, a specific image that elevates the piece from "competent" to
"considered"?

This is the dimension that catches the user's exact complaint: "sloqanlar
zəifdir." Voice-compliant + brand-compliant + brief copy can STILL fail
this dimension if there's nothing for the reader to land on.

- **PASS** — one element makes me re-read it. A specific number that's
  oddly precise, a verb that lands harder than expected, a piece of
  geography that anchors the piece, a sub-headline that recasts the
  headline.
- **MARGINAL** — voice and craft are clean but nothing stops me. I
  read it once and move on.
- **FAIL** — generic. Could be any insurance brand. Reads as a
  template.

**Verdict:** PASS / MARGINAL / FAIL
**One-line note (point at the surprise element OR confirm absence):** ...

---

## Final decision

| | Count |
|---|---|
| PASS | __ |
| MARGINAL | __ |
| FAIL | __ |

**Decision tree:**

- 2+ FAILs → **REWRITE** (loop back; this is failure)
- 3+ MARGINALs → **REWRITE** (the threshold for "competent but
  forgettable" — exact problem we're trying to escape)
- Otherwise → **SHIP** (note any marginal items for next pass)

**Decision:** SHIP / REWRITE
**If rewrite, the prompt adjustment is:** (one-sentence delta naming the
specific failed dimension and the voice-DNA fix to apply)

---

## Notes for next campaign iteration

What did this audit teach us about the voice DNA or swipe file that we
should write back into the system?

- ...
