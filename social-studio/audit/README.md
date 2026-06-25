# Creative Audit System

The Creative Audit is a multi-layer quality-control system for Xalq Insurance Digital OS Social
Studio. It combines deterministic checks with an art-director style review
rubric. The deterministic script is a gate, not the final creative judge.

## What It Checks

- Brand fit: palette discipline, Xalq Sigorta tone, footer and logo rules.
- Art direction: composition, negative space, footer safety, visual hierarchy.
- Marketing clarity: first-second meaning, message strength, campaign relevance.
- Compliance risk: legal claims, dates, mandatory text, risky wording.
- Production readiness: export dimensions, aspect ratios, visual busyness, red
  wash risk, and safe zones.

## Files

- `creative_audit.py` - deterministic audit CLI and final-score combiner.
- `creative_auditor_prompt.md` - LLM review prompt for subjective art direction.
- `rubric.json` - scoring dimensions and weights.
- `manifests/` - campaign manifests that list exports and copy.
- `reviews/` - optional human or vision-LLM creative review JSON files.
- `learning/` - feedback memory for improving future prompt patches.

## Run

```powershell
python social-studio\audit\creative_audit.py `
  --manifest social-studio\audit\manifests\xalqsigorta-travel-insurance.json `
  --rubric social-studio\audit\rubric.json `
  --out-dir output\social\audit
```

With a creative review:

```powershell
python social-studio\audit\creative_audit.py `
  --manifest social-studio\audit\manifests\xalqsigorta-travel-insurance.json `
  --rubric social-studio\audit\rubric.json `
  --creative-review social-studio\audit\reviews\template-review.json `
  --out-dir output\social\audit
```

Outputs:

- `creative-audit-report.json`
- `creative-audit-report.md`

Shortcut:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-social-audit.ps1
```

## Reading Scores

Scores are heuristic, not legal or brand approval by themselves. The automated
gate only checks measurable things. Final approval requires a creative review.

- automated `85-100` - technically strong candidate, pending creative review.
- final `90-100` - approval candidate.
- final `70-89` - usable direction, needs revision.
- `55-69` - needs major revision.
- `<55` - reject or regenerate.

Any `critical` finding blocks approval even if the weighted score is high.
