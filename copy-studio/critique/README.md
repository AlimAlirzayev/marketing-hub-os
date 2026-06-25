# `critique/` — senior editor audit

After the copy is generated, this layer runs one more pass: I read the
output through the lens of a **senior editor / creative director**, not
the generator. The audit asks five questions any senior copywriter would
ask before sending the piece to print.

The output is either:
- **Approved** — the copy ships
- **Marked for rewrite** with specific notes on what's weak

This is the loop that catches the difference between "voice-compliant
copy" and "copy that actually sings." It's the layer that solves the
user's exact complaint: *"sloqanlar əvvəlkilərdən biraz zəifdir."*

## How it runs

`/post` calls this layer after the copy package is generated. Steps:

1. **Read the copy package** (`output/<slug>/headlines.md`,
   `caption-az-instagram.md`, etc.).
2. Load the audit context:
   - `copy_kit/voice.md` — brand voice rules
   - `copy_kit/lexicon.md` — banned/preferred words
   - `copy_kit/legal_phrases.md` — locked phrases
   - The active `voice_dna/<voice>/dna.md` — the chosen creative voice
   - `swipe_file/<campaign>/extracted.md` if it exists — the user's taste
3. Apply the 5-dimension rubric (see `critique_template.md`).
4. Score and decide.

If approved → ship.
If not → rewrite with the critique's specific notes and re-audit
(one retry max per asset).

## The five dimensions (preview — full rubric in template)

1. **Hook strength** — does the first sentence make me want to read the next?
2. **USP clarity** — what is the one specific thing this copy commits to?
3. **Voice match** — does it land in the chosen `voice_dna`?
4. **Brevity** — is every sentence carrying its weight?
5. **Surprise** — is there ONE element a reader pauses on?

Two or more FAILs → rewrite.
Three or more MARGINALs → rewrite.

## Why text-critique is the missing layer

Same logic as visual critique:

A model that **generates** copy and a model that **edits** copy are
different cognitive modes. Without the edit pass, my generation output
reads reasonable *to me as the generator* — but a senior editor would
catch the same flatness the user complained about ("sloqanlar əvvəlki-
lərdən biraz zəifdir").

Running the edit pass with the voice DNA + swipe file + brand kit as
the rubric forces taste back into the loop. Your curated references
become the standard the copy is measured against.

## Output: audit report per asset

Each campaign run stores its audit at
`copy-studio/output/<slug>/critique-<asset>-<v>.md`. Five dimensions,
PASS / MARGINAL / FAIL per dimension, one-line reasoning each.

The audit reports are themselves training data — over time, the
patterns of FAILs sharpen the voice DNA files.
