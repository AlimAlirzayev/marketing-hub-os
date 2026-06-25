# Xalq Sigorta - Brand Identity

This is the structured brand kit for the Xalq Insurance Digital OS Social Studio. It is the
single source of truth for any post the system generates. The numbers and
rules here override anything the LLM might improvise.

## Identity in one line

Xalq Sigorta is a premium, trust-led Azerbaijani financial-services brand. Visual
language: corporate red on charcoal-ink, restrained, cinematic. No flashy gradients,
no sci-fi glow, no cartoon styling. Think high-end European financial-services
advertising photography.

## Palette

See [`colors.json`](colors.json) for hex values and usage rules.

- **Red `#E31E24`** - logo, accents, small dividers. Never a fill.
- **Charcoal `#2B2A29`** - logotype on light surfaces.
- **Ink `#1C1B17`** - legal microcopy.
- **White `#FFFFFF`** - reverse-out, headlines on photo.
- **Burgundy fade `#5C0F12`** - edge atmosphere on photo backgrounds only.

## Typography

The exact Xalq Sigorta corporate font is not available in this repo. Until
it is provided, use:

- **Headline:** Inter Tight (700-800), or Manrope (700-800) as fallback.
  Both render Azerbaijani diacritics (Ə, ş, ç, ğ, ı, ö, ü) cleanly. Google Fonts.
- **Body / legal:** Inter (400-500).
- **Numbers (phone, year):** same as headline, tabular figures.

Headlines are tight (line-height 1.05-1.1), all-caps **only** when the line is
short; otherwise sentence case to match the existing post system.

## Logos and footer

Lives in `assets/` (copied from `output/social/assets/`):

- `xalqsigorta-logo-official.svg` - dark logo for light backgrounds.
- `xalqsigorta-logo-white.svg` - white logo for photo/dark backgrounds.
- `xalqsigorta-footer-dark.svg` - locked footer composition, dark variant.
- `xalqsigorta-footer-light.svg` - locked footer composition, light variant.

**Hard rules** (carried over from the Codex post system doc - these are not
optional):

- The logo, the legal microcopy, the contact lockup (☎ 183 + xalqsigorta.az)
  are *never* rendered by the image model. They are added as a vector layer
  on top of the AI-generated background.
- The footer occupies roughly the bottom 150-190 px of a 1080x1350 feed post.
- Right-align the contact lockup to the same safe margin as the logo.
- On photo backgrounds use a subtle dark gradient behind the footer; never a
  hard rectangular band.

## Photo style

The AI generates only the **photographic campaign background** - the world
the brand lives in. The deterministic Remotion layer adds headline + footer.

Style direction:

- Premium advertising-grade realism. Crisp edges, controlled depth of field,
  realistic lens optics, commercial retouching.
- Cinematic corporate daylight; soft, natural skin tones; refined contrast.
- Modern European / Caucasus aesthetic for Azerbaijani-market scenes.
- Subtle red brand atmosphere - never a wash.
- Reserve the upper-left third for the Azerbaijani headline.
- Reserve the bottom 150-180 px clean for the vector footer.

**Always negative-prompt:** fake logos, fake text, random readable marks,
distorted hands, low-quality faces, cartoon styling, fantasy effects, painterly
smearing, muddy compression, oversaturation, sci-fi glow, impossible
architecture, watermarks.

## Tone of voice

Azerbaijani headlines: short, declarative, present-tense, no clickbait. Tone
is calm authority - like a senior financial-services brand, not a startup.

Examples that already work (from the travel-insurance campaign):

- `Gürcüstana qatarla səyahət artıq mümkündür`
- `Səyahət sığortanı unutma.`
- `1 yanvar 2026-dan Gürcüstana giriş üçün səyahət sığortası məcburidir.`

For English captions (LinkedIn international audience), match the same calm
authority - no exclamation marks, no emoji except in casual cross-post copy.

## Mandatory legal microcopy

This text appears on every Xalq Sigorta post footer, exactly as written
(do not paraphrase, do not translate):

```
"Xalq Sigorta" ASC Azərbaycan Respublikası Maliyyə Nazirliyinin
29 Aprel 2010-cu il tarixli 000333 saylı lisenziyası əsasında fəaliyyət göstərir.
Ünvan: Bakı şəhəri, Akademik Həsən Əliyev küçəsi 24.
```

Contact lockup (right side of footer):

```
☎ 183  |  xalqsigorta.az
```
