# Master prompt template

The 11-layer skeleton every Social Studio prompt is built from. Layers are
ordered by **enforcement priority**: things higher up are harder constraints
that the model is reminded of first. Things lower down are stylistic anchors.

This template is model-agnostic. The `model_dialects/` folder explains how
each model (GPT Image 2, Nano Banana, FLUX) prefers the same content rephrased.

---

## Layer 1 — Constraint (hard rules, non-negotiable)

Format, aspect ratio, exact pixel dimensions. Subject count. Scene anchor.
Anything that, if broken, makes the image unusable.

> Format: 4:5 vertical, 1080×1350. Background plate only.
> Subject: ONE couple. Ages 28-34. Caucasus-Azerbaijani features.

## Layer 2 — Camera & Lens

Equivalent focal length, aperture, ISO, camera angle, subject distance.
Photographers think in these terms; models trained on photo datasets respond.

> Equivalent 50mm full-frame, f/2.8, ISO 200. Medium shot, waist-up.
> Slight low angle (~chair-armrest height).

## Layer 3 — Lighting

Key direction, fill ratio, color temperature (Kelvin), catchlights.
This single layer is what separates "AI image" from "ad photography".

> Key: soft window light from camera right, late morning warmth (4800K).
> Fill: 1:4 ratio. Catchlights in subject eyes. No artificial spots.

## Layer 4 — Subject Identity

Age, ethnicity, attire colors (with explicit "NOT red" if a brand prop owns red),
hairstyle, makeup, accessories, posture, gaze direction, mood.

> Woman: shoulder-length dark hair, minimal makeup, small gold studs.
> Man: short well-groomed beard, plain charcoal henley.
> Both: NOT looking at camera. Candid editorial mood.

## Layer 5 — Brand Props (micro-detail)

Every brand-anchor object specified with: position in frame, HEX color,
size, finish, condition. The smaller the brand prop's footprint, the
more specific you must be.

> Red hard-shell suitcase: lower-left foreground, edge-cropped 30%.
> Color HEX #E31E24 (Xalq Sigorta brand red). No visible brand name.

## Layer 6 — Scene Background

The world outside the subject. Geographic anchor, real-world reference,
mid-distance focus point. Avoid "exotic" if the brand is local.

> Outside window: real Caucasus geography. Mid-distance focus.
> Train interior: modern Stadler/CAF-style aluminum + dark navy fabric.

## Layer 7 — Brand Atmosphere (the subtlest layer)

The "feeling" of the brand baked into the photo before any text overlay.
Edge tinting, prop reflection, color-grading bias.

> Red atmospheric tint at far-LEFT edge ONLY (20% width).
> Burgundy fade (#5C0F12 → transparent). NOT a wash.

## Layer 8 — Negative Space (for overlay)

Pixel-precise zones the model must leave clean for headline, sub, footer.
Specify size, location, and what must NOT be there.

> Upper-LEFT third: calm dark zone for Azerbaijani headline.
> Bottom 180px: clean footer zone. No faces, no hands.

## Layer 9 — Style Anchor

Reference real campaigns, photographers, magazines. NOT "stock photo".

> Reference: Mont Blanc travel campaign 2024, Hermès "Petit h" series.
> Editorial documentary, NOT lifestyle stock.

## Layer 10 — Quality Directives

Pore visibility, hand anatomy, fabric weave, film grain. These cues tell
the model to render photographically, not generatively.

> Visible skin texture (pores, light freckles).
> Natural hand anatomy - all 10 fingers correct.
> Film grain ISO 200 equivalent.

## Layer 11 — Exclusion List

Things that must NOT appear. Order from most-likely-to-happen to
least-likely. Models read these in order.

> ✗ Any visible text or readable signage
> ✗ Watermarks
> ✗ Plastic skin, smooth-airbrushed AI faces
> ✗ Multiple couples in frame
> ✗ Heavy red wash across entire frame

---

## How to use

1. Copy this skeleton into a new prompt file under
   `campaigns/<campaign>/prompts/v<N>.md`.
2. Fill every layer with **specifics**. If you cannot specify, the model
   will improvise — usually toward generic stock-photo defaults.
3. Cross-reference `style_anchors/` for reusable mood descriptions and
   `negative_templates/` for the standard exclusion list.
4. Run through `model_dialects/<model>.md` to rephrase for the target model.
5. Generate at least 3 seeds per prompt, audit, iterate.
6. Save lessons in `notes.md` — the prompt is itself a versioned artifact.
