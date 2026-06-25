# Standard exclusion list — AI tells

The visual signatures that betray "AI-generated" instantly. Append the
relevant ones to Layer 11 of any prompt. Ordered by how often they
appear in raw output.

## Skin & faces

- Plastic skin, smooth-airbrushed faces
- Symmetric features (real faces are asymmetric)
- Double pupils, mismatched eye colors
- Hairline that fades into forehead (no clear edge)
- Eyebrows merging into hairline

## Hands

- Extra fingers, fused fingers
- Knuckles flat / waxy
- Fingernails that grow out of the wrong place
- Holding objects with wrong grip mechanics
- Both hands identical mirror copies

## Text & signage

- Any visible text or readable signage
- Fake brand names on products
- Random Cyrillic / Arabic glyphs mixed with Latin
- Numbers on phone screens
- "Generated" watermarks (Pollinations, Shutterstock, etc.)

## Composition

- Subjects floating with no contact shadows
- Multiple identical clones of the subject in background
- Impossible geometry (M.C. Escher accidents)
- Reflections that don't match the source

## Light & material

- HDR look — every shadow filled, no contrast
- Fake bokeh circles (perfectly round, no aberration)
- Plastic-looking metal
- Glass without realistic distortion
- Halos around backlit subjects

## Stylistic tells

- Cartoon / anime stylization creeping in
- Painterly smearing in low-detail areas
- Oversaturation, especially in skies
- Sci-fi neon glow that wasn't asked for

## How to use

Don't paste the entire list — pick the 8-12 most likely failures for
your specific scene and order them by probability. Example for a
portrait scene:

```
✗ Plastic AI skin
✗ Extra fingers, fused fingers
✗ Symmetric faces
✗ Both eyes mismatched
✗ Floating shadow-less subject
✗ Fake text on visible props
✗ Multiple background clones of subject
✗ HDR-flattened lighting
```
