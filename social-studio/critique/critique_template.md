# Critique template — art-director audit rubric

When `/post` calls this layer, Claude reads the final composite with
vision and writes the audit using this template. Each campaign run
stores its audit at `social-studio/output/<slug>/critique-<variant>.md`.

The audit is harsh on purpose. The senior art director's job is to
catch what the brief writer missed.

---

## Audit context

- **Campaign:** `<slug>`
- **Variant:** `<filename>`
- **Style DNA in effect:** `<style>` (link to dna.md)
- **Moodboard used:** `<slug>` if any (link to extracted.md)
- **Brand kit:** `social-studio/brand_kit/brand.md`

## Dimension 1 — Brand fidelity

Does the composite obey the rules in `brand_kit/`?

- [ ] Brand red used as accent, never as wash (per `colors.json` usage_rules)
- [ ] Footer occupies bottom 150-190 px
- [ ] Headline lives in upper-left calm zone
- [ ] Logo + 183 + xalqsigorta.az + legal microcopy all present and legible
- [ ] No fake text in the AI-generated background

**Verdict:** PASS / MARGINAL / FAIL  
**One-line note:** ...

## Dimension 2 — Style DNA fidelity

Does the photographic background match the `<style>/dna.md` specification?

Pull 3 specific signals from the DNA and check them:

- [ ] Subject treatment (pose, gaze, scale) matches DNA's spec
- [ ] Lighting (direction, hardness, color temp) reads as the DNA specifies
- [ ] Color story / palette is within DNA's stated range
- [ ] None of the DNA's exclusion-list items appear

**Verdict:** PASS / MARGINAL / FAIL  
**One-line note (cite the specific DNA line that's met or violated):** ...

## Dimension 3 — Moodboard fidelity (skip if no moodboard)

Does the result land where the user's curated refs land?

- [ ] Convergent signals from `extracted.md` are present
- [ ] No divergent-signal extremes (e.g. went too far toward the
       adventurous end when the campaign called for conservative)

**Verdict:** PASS / MARGINAL / FAIL / N/A  
**One-line note:** ...

## Dimension 4 — Creative bar (the hardest one)

This is the question that catches "klassik" outputs. Three sub-checks:

a. **Cliché check** — is this a frame I have seen in 100 stock-photo
   sets? If yes → MARGINAL or FAIL.

b. **Surprise check** — is there ONE element (composition, light,
   gesture, color, foreground prop) that makes the viewer pause? If
   nothing → FAIL.

c. **Senior-AD vocabulary** — could I describe this image with
   specifics a senior art director would use, or only with generic
   adjectives ("nice", "professional", "premium")? Generic → FAIL.

**Verdict:** PASS / MARGINAL / FAIL  
**One-line note naming the surprise element OR the cliché:** ...

## Dimension 5 — Technical execution

The mechanical checks that are easy to miss in self-review:

- [ ] Anatomy correct (10 fingers, no warped hands, no double pupils)
- [ ] No visible AI tells (plastic skin, smearing, impossible reflections)
- [ ] Negative-prompt items absent (per `negative_templates/`)
- [ ] Composite quality: cover-crop preserved subject proportions, no
       visible rectangle in the gradient overlay

**Verdict:** PASS / MARGINAL / FAIL  
**One-line note:** ...

---

## Final decision

| | Count |
|---|---|
| PASS | __ |
| MARGINAL | __ |
| FAIL | __ |

**Decision tree:**

- 2+ FAILs → **regenerate** (loop back; this is failure)
- 3+ MARGINALs → **regenerate** (the threshold for "competent but
  clichéd" — the exact problem we're trying to escape)
- Otherwise → **ship** (with notes on the marginal items for next pass)

**Decision:** SHIP / REGENERATE  
**If regenerate, the prompt adjustment is:** (one-sentence delta to the
master prompt, citing the specific failed dimensions)

---

## Notes for next campaign iteration

What did this audit teach us about the style DNA or moodboard that we
should write back into the prompt_kit?

- ...
