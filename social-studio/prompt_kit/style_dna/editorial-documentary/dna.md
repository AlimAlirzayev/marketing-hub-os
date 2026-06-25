# Style DNA — `editorial-documentary`

The Xalq Sigorta default voice. Restrained, observed, premium-but-not-loud.
This is what a senior travel-magazine art director would brief: the moment
between moments, captured as if the subject didn't know.

## Lineage

- **Magnum Photos** travel and editorial work, Steve McCurry's Caucasus &
  Central Asia series, Anastasia Taylor-Lind's Tbilisi work.
- **Annie Leibovitz** corporate portrait grammar — controlled lighting,
  retained skin texture, the dignity of stillness.
- **Mont Blanc 2024 travel** campaigns (luggage + journey).
- **Hermès "Petit h"** documentary series (the hand at work).

Avoid as references: Shutterstock, iStock, Getty general stock, lifestyle
catalog photography of any kind.

## Subject treatment

- **Pose:** Mid-action. Seated, walking, holding, reading — captured in the
  one-second moment between two beats. NOT posed. NOT candid. Frozen
  mid-gesture.
- **Gaze:** OFF-frame, never at the camera. Eyes track the environment —
  a view through a window, a door, a piece of paper, the partner's hand.
  Mid-distance focus. Catchlights small, single point.
- **Number:** Solo OR a measured pair. Three is already a crowd in this voice.
- **Scale:** Medium shot, waist-up. Wide enough to read environment.
- **Posture:** Relaxed but alert. Seasoned. "Has done this before."
- **Mouth:** Closed or faintly parted. No teeth-out smiles. The subject is
  thinking, not performing.

## Composition

- **Rule of thirds**, never centered. Subject at 1/3 or 2/3 vertical line.
- **Strong negative space** on one side — for headline overlay if needed,
  for breathing if not.
- **Foreground layering** that adds depth: a doorframe edge, a prop, a
  hand in motion blur, a piece of fabric. The viewer sees layers.
- **Leading line** from environment (a window's edge, a track, a corridor)
  draws the eye toward the subject.
- **Depth:** Shallow but not extreme. f/2.8 equivalent — subject sharp,
  background gently soft but still readable.

## Light

- **Single key**, soft and large source: window, sky-light, north light,
  overcast outdoors. The light has a *direction*. No softbox-everywhere
  HDR look.
- **Color temperature:** 4500-5200K. Late morning or golden afternoon —
  never harsh midday, never the blue hour.
- **Key-to-fill ratio:** 1:4 to 1:5. Shadows present but not deep. The
  subject's off-side cheek and jaw retain modeling.
- **Catchlights:** Small, soft, single source. Mirrors the key light.
- **No artificial rim, no halo backlight.** That's commercial-glossy
  language; this voice is editorial.

## Color story

- **Dominant palette:** Muted earth — charcoal, ink, cream, beige, navy,
  warm gray, soft brown.
- **Accent:** ONE saturated brand color (e.g. Xalq Sigorta red `#E31E24`)
  used as a single anchor — a suitcase, a book spine, a phone case, an
  earring. Never a wash.
- **Saturation register:** Muted overall. The accent gets its impact
  *because* the rest is restrained.
- **Skies:** Hazy, soft. Never saturated postcard blue.

## Material rendering

- **Skin:** Visible pores, faint freckles, natural shine. Light retouch
  only. The subject looks like a real adult, not an airbrushed AI.
- **Fabric:** Weave visible. Cotton looks like cotton. Leather looks like
  leather. Knits show structure.
- **Hard surfaces:** Patina allowed. New plastic discouraged. Brushed metal,
  weathered wood, slight wear on luggage.
- **Glass/reflections:** Photographically rendered with slight distortion.
  No CGI-perfect mirror surfaces.

## Mood vocabulary

- **Pace:** Slow. Suspended. The viewer feels invited to sit with the moment.
- **Intimacy distance:** Observational. The camera is across the room or
  across the table. NOT over the shoulder.
- **Emotional register:** Quiet authority. Calm. The subject is comfortable
  in their world.
- **Story register:** A moment in a longer day. The viewer assumes context
  before and after the frame.

## Lens & camera

- **Focal length:** 50mm full-frame equivalent (35mm acceptable for wider
  environment).
- **Aperture:** f/2.8 (f/4 if more depth wanted).
- **ISO:** 200, subtle organic grain.
- **Camera angle:** Eye-level to slight low — never high or birds-eye.

## Reference phrases (fold verbatim into the master prompt's Layer 9)

```
- "Editorial documentary photography, Magnum Photos travel category,
   Annie Leibovitz corporate portrait grammar."
- "Subject mid-action, gaze off-frame toward the environment, not at the
   camera."
- "Single soft key light from window, 4800K, 1:4 fill ratio, retained
   shadow modeling on off-side cheek and jaw."
- "Muted earth palette with one saturated brand-color accent prop."
- "Visible skin texture, pores allowed, natural hand anatomy, fabric weave
   visible."
- "Slow editorial pace. Quiet observed moment."
```

## Style-specific exclusions

Append to Layer 11 of the master prompt:

```
✗ Subjects facing or looking at the camera
✗ Teeth-out smiles or any "lifestyle catalog" expressions
✗ Studio softbox / softbox-everywhere HDR-flat lighting
✗ Vibrant postcard saturation
✗ Brand red used as wash, band, or background fill
✗ Plastic AI skin or airbrushed faces
✗ Stock-photo composition (centered subject, no foreground layering)
✗ Three or more subjects in frame
✗ Motion blur on subjects (the moment is frozen, not in motion)
✗ Backlit halo / rim light glamour
```

## When to override the brand defaults

This style **is** Xalq Sigorta's default voice — it doesn't override
`brand_kit/`, it embodies it. The brand's "calm authority" voice maps
directly onto this DNA's "quiet observed moment."

The exception: if a campaign explicitly needs to feel YOUNGER (Instagram
Reels for a millennial-targeted product), switch to `emerging-ai-luxury`.
If the campaign needs to feel MORE INSTITUTIONAL (B2B/investor-facing),
switch to `financial-restraint`.
