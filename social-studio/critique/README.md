# `critique/` — vision-based art-director audit

After the visual is generated and composited, this layer runs ONE more
pass: I look at the output **with vision** and audit it as a senior art
director, not as the system that produced it.

The output is either:
- **Approved** — proceed to publishing package
- **Marked for regeneration** with specific notes on what to fix

This is the iterative creative loop. It's what separates a system that
"made an image" from one that "produced a campaign visual."

## How it runs

`/post` calls this layer after compose. Steps:

1. **Read the final composite** via `Read <path.png>` (vision).
2. Load the audit context:
   - `brand_kit/brand.md` + `brand_kit/colors.json` (brand rules)
   - The active `style_dna/<style>/dna.md` (creative voice)
   - The campaign `moodboard/<slug>/extracted.md` if it exists (taste)
3. Apply the audit using `critique/critique_template.md` as the rubric.
4. Score and decide.

If approved → return package.
If not approved → re-prompt with the critique's specific notes and
regenerate (one retry max per variant to keep the loop bounded).

## The score isn't a number

The audit returns a structured verbal report, not a numerical grade. The
rubric has 5 dimensions; each gets PASS, MARGINAL, or FAIL with one-line
reasoning. Two or more FAILs → regenerate. Three or more MARGINALs →
regenerate. Otherwise → ship.

See [`critique_template.md`](critique_template.md) for the rubric.

## Why visual self-critique is the missing layer

A model that generates and a model that judges are different cognitive
modes. Without the critique pass, my generation output looks reasonable
*to me as the generator* — but a senior art director would catch the same
visual clichés that the user complained about ("klassikdir").

Running the judge pass with the moodboard + style DNA as the rubric
forces taste back into the loop. The user's curated reference become the
standard the output is measured against.
