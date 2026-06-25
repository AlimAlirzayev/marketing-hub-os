# Xalq Sigorta Travel Insurance Post System

## Master Format

- Primary feed export: 1080x1350 px, 4:5.
- Square adaptation: 1080x1080 px.
- Story/Reels adaptation: 1080x1920 px.
- Keep headline and footer inside a 52-72 px safe margin.
- Do not generate logo, legal text, contact text, or campaign copy inside the AI image. These must be added as vector/text layers in post-production.

## Brand Footer Component

Use this footer on Xalq Sigorta social posts as a fixed brand component, not as a newly designed element.

Reusable files:

- `assets/xalqsigorta-logo-official.svg`
- `assets/xalqsigorta-logo-white.svg`
- `assets/xalqsigorta-footer-dark.svg`
- `assets/xalqsigorta-footer-light.svg`

Footer contains:

1. Bottom-left official Xalq Sigorta logo lockup.
2. Mandatory legal/requisite microcopy directly below the logo:
   `*"Xalq Sigorta" ASC Azərbaycan Respublikası Maliyyə Nazirliyinin 29 Aprel 2010-cu il tarixli 000333 saylı lisenziyası əsasında fəaliyyət göstərir.`
   `Ünvan: Bakı şəhəri, Akademik Həsən Əliyev küçəsi 24.`
3. Bottom-right contact lockup:
   phone icon + `183` + vertical divider + `xalqsigorta.az`.

Footer color variants:

- Dark/photo background: white logo, white legal text, white contact lockup.
- Light background: red/black logo, dark legal text, red contact lockup.

Footer behavior:

- Use vector/SVG or editable text layers whenever possible.
- Do not let AI render this footer.
- Use a subtle dark gradient fade behind the footer on photo backgrounds.
- Avoid heavy opaque footer bars unless the image is too busy.
- For 1080x1350 feed posts, the footer component should occupy roughly the bottom 150-190 px.
- Keep the legal/requisite text exactly as written unless compliance or brand updates it.
- Right-align the contact lockup to the same safe margin used by the logo.
- Footer fade must start well above the logo area and must not reveal a visible horizontal boundary.
- Red diagonal texture should be very low-opacity and only visible in the deepest footer zone.

## Red Overlay And Gradient Rules

- Do not use a heavy opaque red wash across the whole post.
- Red overlay should support readability, not dominate the image.
- Use soft feathered gradients with long transitions; avoid visible linear edges, hard rectangular bands, or obvious red-to-photo boundaries.
- On photo backgrounds, keep red as a brand atmosphere: dark burgundy at the edges, transparent toward the subject.
- If a generated background already contains a bottom red strip, crop it out before applying the deterministic footer component.
- Prefer black/burgundy footer fade over saturated red footer blocks.

## Final AI Background Prompt Logic

Generate only the photographic campaign background. The final image should be advertising-grade, sharp, clean, and suitable for a vector/text overlay.

Prompt rules:

- State the output as a final-production social background, not a finished poster.
- Reserve upper-left negative space for Azerbaijani headline.
- Reserve the bottom 150-180 px for the brand footer.
- Include brand-color props: red suitcase, red-white insurance UI, subtle shield reflection.
- Avoid fake text, fake logos, random readable marks, distorted hands, low-quality faces, overdone glow, and cheap stock-photo composition.
- Use high pixel clarity language: crisp edges, controlled depth of field, realistic lens optics, refined commercial retouching, no muddy compression, no painterly smearing.

Recommended final-production prompt:

```text
Use case: ads-marketing
Asset type: final-production photographic background for Xalq Sığorta Instagram/Facebook campaign.
Generate background only; no headline text, no logo, no contact text, no legal text, no random readable writing.

FINAL PRODUCTION QUALITY DIRECTIVE:
Create a premium advertising-grade image with high pixel clarity, crisp edges, clean realistic faces and hands, controlled depth of field, realistic lens optics, refined commercial retouching, no muddy compression, no painterly smearing, no warped objects. Think high-end financial-services campaign photography, prepared for a 1080x1350 social media export with post-production text and vector footer added later. Keep the image sharp enough for typography overlay and avoid noisy or busy areas where copy will sit.

Brand art direction:
Xalq Sığorta / Xalq Bank social media family: deep corporate red, white, charcoal black, polished financial-services advertising, restrained premium mood. Include subtle red gradient wash and dark-to-transparent overlay behavior on the lower and left zones. The final brand footer will be added separately, so reserve a clean footer area at the bottom.

Scene:
A realistic Azerbaijan-to-Georgia train travel moment, suggesting Baku-Tbilisi route. Interior of a modern intercity passenger train beside a large window. Outside: scenic Caucasus mountains, railway bridge, and soft daylight, realistic regional international rail travel, not futuristic.

Foreground:
A stylish young Azerbaijani couple seated by the window, calm and confident. They hold passports and travel documents. Include a red hard-shell suitcase as a strong brand-colored travel prop. Add a clean travel-insurance prop: smartphone or document folder with abstract red-and-white insurance UI shapes only, no readable fake text.

Protection concept:
A very subtle transparent shield reflection on the train window, integrated as a realistic glass reflection. Minimal and elegant, almost invisible; no fantasy glow or sci-fi effect.

Composition:
Vertical 4:5 feed composition. Leave the upper-left third as calm red/dark negative space for Azerbaijani headline text. Keep the couple and travel props in the right/lower-right visual focus. Reserve the bottom 150-180 px as a clean zone for vector footer overlay. Do not place faces, hands, suitcase handles, or important details in the bottom footer zone.

Lighting and style:
Cinematic corporate daylight, soft window light, premium contrast, realistic skin tones, sharp but natural details, modern European/Caucasus travel aesthetic. Subtle red reflections, elegant dark tones, realistic glass and metal.

Negative constraints:
No fake logo, no generated text, no random letters, no watermark, no low-quality faces, no distorted hands, no clutter, no cheap stock-photo look, no cartoon style, no exaggerated shield, no excessive glow, no oversaturation, no fantasy train, no impossible architecture, no visible brand names except abstract unrecognizable UI marks.
```

## Current Campaign Copy

Headline:
`Gürcüstana qatarla səyahət artıq mümkündür`

Subheadline:
`Səyahət sığortanı unutma.`

Supporting text:
`1 yanvar 2026-dan Gürcüstana giriş üçün səyahət sığortası məcburidir.`
