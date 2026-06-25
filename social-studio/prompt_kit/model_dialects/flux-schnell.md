# Model dialect — FLUX schnell (Pollinations turbo, FLUX.1 schnell)

How FLUX schnell prefers the same content phrased. Use this as a
post-processing layer on the master_template output.

## Hard constraint: URL length

Pollinations.ai serves FLUX schnell via a GET URL. Requests beyond
~4000 characters of URL (about 1500–2000 characters of plain prompt
after URL-encoding) return **404 Not Found**.

The full v2 master-level prompt is ~3500 plain chars → 7600+ URL
encoded → **rejected**. Solution: produce a **compressed dialect**
that retains the constraint layers and drops verbose prose.

## What FLUX schnell responds to

- Comma-separated tags more than sentences.
- Photo recipe shorthand: `50mm f/2.8 ISO 200`, `4800K window light`.
- HEX colors for props.
- One-line negative trail at the end.

## What it ignores

- Style anchors with brand names (Mont Blanc, Hermès) — limited
  training association. Strip these for FLUX; keep for GPT Image 2.
- Multi-sentence emotional direction ("seasoned travelers, not
  first-timers") — usually ignored. Reduce to "relaxed posture".
- Section headers (=== CAMERA ===) — treated as decorative.

## Compression recipe

1. Strip section headers.
2. Strip "=== === === === === HARD CONSTRAINTS === === ===" framing.
3. Collapse multi-sentence layers into single dense sentences.
4. Drop style-anchor brand names unless they're widely-trained
   photographer references (Helmut Newton, Annie Leibovitz survive).
5. Move the exclusion list to one comma-separated line at the end,
   prefixed with `NO `.
6. Target ≤ 1800 plain characters.

## Failure modes specific to FLUX schnell

- Stock-photo composition drift if camera/lens not pinned.
- Color drift on brand red (renders as orange-red without HEX).
- Hand anatomy errors — always include "natural 5-finger hands" or
  similar count cue.
- Stylization creep (illustration/anime) if "photographic" not
  reinforced early.
