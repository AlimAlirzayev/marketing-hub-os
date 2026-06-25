# Flora Video Model Matrix

Last refreshed from `flora models list --type video`: 2026-05-22.

Use this as the account-local decision guide. Refresh it before major
campaigns because Flora's catalog changes.

## Production Tiers

| Tier | Use | Models |
|---|---|---|
| Discovery | Low-cost motion tests, prompt debugging, rough direction | `i2v-kling-2.6`, `i2v-seedance-1.5-pro` |
| Production | Client-facing variants with references and storyboard | `i2v-seedance-2-0-reference-i2v-enhancor`, `i2v-runway-gen-4.5`, `i2v-sora2-pro` |
| Premium cinematic | Hero films where cost/time is acceptable | `i2v-veo3`, `t2v-kling-v3-pro` |
| Fallback | If reference adherence fails | deterministic Remotion/Pillow plate animation |

## Current Model Notes

| Model | Type | Strength | Limitation | Current params |
|---|---|---|---|---|
| `i2v-seedance-1.5-pro` | image-to-video | Fast, cheap, good for first motion exploration | 720p max in current catalog; can mutate text/UI | 9:16, 4-12s, 480p/720p, camera_fixed |
| `i2v-kling-2.6` | image-to-video | Good short motion and commercial polish | Few controls in CLI schema | 5s or 10s |
| `i2v-seedance-2-0-reference-i2v-enhancor` | image-to-video | Best fit for reference-led brand consistency | Higher cost | 9:16, 4-15s, 480p/720p/1080p |
| `i2v-runway-gen-4.5` | image-to-video | Strong high-end motion from reference stills | No explicit resolution param in current CLI schema | 9:16, 5s/8s/10s |
| `i2v-sora2-pro` | image-to-video | Strong temporal storytelling and smooth motion | Slow; 10s unavailable, choose 8s or 12s | 9:16, 720p/1080p, 4s/8s/12s |
| `i2v-veo-3-1-lite-i2v` | image-to-video | High-quality short clips | Max 8s in current catalog | 9:16, 4s/6s/8s, 720p/1080p |
| `i2v-veo3` | image-to-video | Premium cinematic motion | Very high cost; sparse CLI params | aspect_ratio |
| `t2v-kling-v3-pro` | text-to-video | Strong 1080p/4k cinematic generation | No image reference; weaker brand consistency | 9:16, 3-15s, 1080p/4k |

## Selection Rules

1. If the ad must preserve a poster, product, face, card, or object identity,
   start with image-to-video, not text-to-video.
2. If exact text must be readable, do not ask the model to render the text.
   Generate a clean plate and add text as deterministic overlay.
3. If the current reference image already contains text, either:
   - use it only as mood/composition reference, then overlay clean text, or
   - create a textless plate first and animate that.
4. Use at least two production models for final campaigns:
   - one reference-adherence model,
   - one motion-quality model.
5. Save every run with model ID, prompt version, asset IDs, charged cost,
   status, output URL, and QA verdict.

## Recommended Meta Reels Stack

For a 10-second 9:16 paid social ad:

1. Build a textless 9:16 master plate from approved brand assets.
2. Run `i2v-seedance-2-0-reference-i2v-enhancor` at 1080p, 10s.
3. Run `i2v-runway-gen-4.5` at 9:16, 10s as a second creative variant.
4. If the concept needs stronger scene invention, run `t2v-kling-v3-pro`
   at 1080p, 10s, then composite brand assets over it.
5. Finalize in deterministic render with locked typography, logos, CTA,
   campaign terms, and end frame.
