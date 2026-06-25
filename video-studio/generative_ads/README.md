# Generative Ads Studio

This folder is the production layer for AI-generated advertising video. It
extends `social-studio/` into motion work: brand assets, reference images,
storyboard, model choice, prompt dialects, deterministic overlays, and QA.

The core rule is simple: the generative model creates the visual plate and
motion. Exact brand text, legal copy, logos, CTA buttons, prices, dates, and
campaign terms are added by a deterministic render layer. Even strong video
models can mutate letters frame to frame, so production work never depends on
AI-rendered copy.

## Workflow

1. Write a campaign brief in `campaigns/<slug>/brief.json`.
2. Attach brand assets and references by role:
   - `brand_logo`
   - `partner_logo`
   - `product_reference`
   - `campaign_key_visual`
   - `motion_reference`
   - `style_reference`
   - `overlay_lockup`
3. Write a scene-by-scene storyboard in `campaigns/<slug>/storyboard.md`.
4. Compile the Flora prompt:

   ```powershell
   python scripts\compile_generative_ad.py video-studio\generative_ads\campaigns\<slug>\brief.json
   ```

5. Generate 2-4 model variants in Flora using the model strategy in the brief.
6. Reject any AI output that mutates text, logos, UI, car anatomy, hands, or
   product geometry.
7. Composite exact copy, logos, legal text, CTA, and captions in Remotion,
   Pillow, or FFmpeg.
8. Export platform variants and save the QA report next to the final MP4.

## Folder Map

```text
generative_ads/
  brief.schema.json              contract for campaign briefs
  model_matrix.flora.md          current Flora model decision guide
  templates/
    meta-reels-10s.json          starting brief for 9:16 Meta ads
  campaigns/
    <slug>/
      brief.json
      storyboard.md
      prompts/
        flora-video-v1.md
      qa_checklist.md
```

## Quality Gates

Every final ad must pass these gates:

- Brand identity: logo lockups, palette, typography, and tone match the
  approved brand kit.
- Asset fidelity: referenced product, partner brand, vehicle, card, and gift
  visuals stay recognizable.
- Text safety: all readable Azerbaijani copy is deterministic overlay text,
  not generated pixels.
- Storyboard fidelity: each beat is visible at the intended second range.
- Platform fitness: 9:16 safe areas, thumb-stopping first second, clear CTA in
  the final two seconds.
- Compliance: offer dates, eligibility limits, and legal microcopy match the
  approved campaign brief.

## Model Policy

Use the cheapest model only for pipeline tests or motion exploration. For
client-facing production, generate at least two premium variants and select
against the QA checklist. See `model_matrix.flora.md`.
