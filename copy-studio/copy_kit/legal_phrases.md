# Locked legal phrases

These are **not editable** by the LLM. They appear verbatim in every
output where required, and never appear paraphrased.

## Mandatory legal microcopy (every Xalq Sigorta post footer)

```
*"Xalq Sigorta" ASC Azərbaycan Respublikası Maliyyə Nazirliyinin
29 Aprel 2010-cu il tarixli 000333 saylı lisenziyası əsasında fəaliyyət göstərir.
Ünvan: Bakı şəhəri, Akademik Həsən Əliyev küçəsi 24.
```

Rules:
- Appears in vector footer overlay (NOT rendered by AI), per
  `social-studio/brand_kit/brand.md`.
- Three lines, exactly as above. Line breaks preserved.
- Never translated to EN/RU — Azerbaijani regulatory text is bilingual
  legally optional but cultural-norm always in AZ.
- Never abbreviated. Even on small-format assets, the full text is laid
  out at 12-13 pt minimum or omitted entirely (story 9:16 format may
  abbreviate to the first line only if space-constrained).

## Contact lockup (every post)

```
☎ 183  |  xalqsigorta.az
```

- Phone glyph + space + 183 + space + vertical-bar separator + space + URL.
- No leading zero on 183.
- URL lowercase, no protocol.

## Mandatory disclosures by product

### Travel insurance (current campaign category)

When mentioning Georgia (Gürcüstan) entry requirement, the LLM MUST
include this fact verbatim or near-verbatim somewhere in body or sub:

```
1 yanvar 2026-dan etibarən Gürcüstana giriş üçün
səyahət sığortası məcburidir.
```

EN equivalent (also locked):

```
From January 1, 2026, travel insurance is mandatory for entry to Georgia.
```

### Other product categories (future — to be filled)

- KASKO (auto) — TODO when first KASKO campaign runs
- Mənzil sığortası (home) — TODO
- Sağlamlıq sığortası (health) — TODO

Each future product gets a locked-phrase block added here. The LLM
should always check this file for the active campaign's product
category before generating body copy.

## What is NOT locked (the LLM CAN rewrite)

- Headlines and sub-headlines
- Captions for social media
- Reel/video scripts (within voice rules)
- Email subject lines
- Hashtags
- Alt-text

## Why this file exists

Insurance is a regulated industry. Legal text must be verbatim because
the regulator (Azerbaijan Republic Ministry of Finance, license 000333)
expects it. Marketing creativity stops at this line.

If the LLM is unsure whether a phrase belongs here, it does. Ask in the
critique pass before deviation.
