# Flora Video Prompt Dialect

Use this dialect for Flora video generations. It is written for paid social
ads where brand consistency matters more than uncontrolled visual invention.

## How Flora Video Models Listen

- Put format, duration, aspect ratio, and reference role first.
- Describe motion in short timeline beats, not only as a single mood.
- Repeat brand-preservation constraints near the top and near the negative
  section.
- Keep exact overlay copy out of the generative ask unless the text is already
  burned into a reference image and acceptable as a background detail.
- For Meta/TikTok/Reels, ask for clean negative space and stable end frame.

## Prompt Order

1. Job definition:
   - "Create a 10-second vertical 9:16 Meta Reels advertisement."
   - "Use the provided image as composition/product reference."
2. Brand and asset fidelity:
   - name the brand,
   - name partner/product assets,
   - define what must remain recognizable.
3. Storyboard:
   - `0.0-1.5s`: hook
   - `1.5-4.0s`: product/benefit reveal
   - `4.0-7.5s`: offer proof or terms cards
   - `7.5-10.0s`: CTA settle
4. Motion language:
   - parallax,
   - controlled push-in,
   - light sweep,
   - product glow,
   - ribbon/card motion,
   - no shaky camera.
5. Text policy:
   - "Do not generate new readable text."
   - "Leave clean zones for deterministic overlay."
6. Negative list:
   - text mutations,
   - fake logos,
   - new brands,
   - extra people,
   - wrong car geometry,
   - distorted fuel pump/card,
   - warped UI,
   - compression artifacts.

## Copy-Safe Rule

For Azerbaijani, Turkish, and other diacritic-heavy campaign text, prefer:

```text
Generate a textless or low-text motion plate. Do not create new readable
letters, numbers, prices, dates, legal terms, or CTA text. The final campaign
copy will be added in post-production as vector/text overlay.
```

If the source image contains approved text and the brief intentionally uses it
as a visual card, add:

```text
The source card may remain visible as a graphic object, but do not invent or
rewrite any visible letters. Any readable foreground copy must be left for
post-production overlay.
```

## Good Flora Video Prompt Shape

```text
Create a 10-second vertical 9:16 paid social ad for [brand]. Use the provided
[asset role] as the product and composition reference. Preserve [objects] and
brand colors. Generate a clean motion plate, not final typography.

Storyboard:
0.0-1.5s: ...
1.5-4.0s: ...
4.0-7.5s: ...
7.5-10.0s: ...

Motion style: ...
Brand style: ...
Text policy: ...
Negative constraints: ...
```
