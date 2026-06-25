# Model dialect — FLUX.1-dev (via gradio_client → HF Space)

The free-tier hidden gem discovered 2026-05-21. Significantly better than
FLUX schnell, comparable to GPT Image 2, FREE and programmatic, no API key.

## How it's accessed

Direct call to the public HuggingFace Space `black-forest-labs/FLUX.1-dev`
via `gradio_client`. No MCP dependency (bypasses the `gradio=none` lock on
this Claude install). No API key. ZeroGPU queue — typically 1-2 minutes
when uncongested, up to 10 minutes at peak.

```python
from gradio_client import Client
client = Client("black-forest-labs/FLUX.1-dev", verbose=False)
result = client.predict(
    prompt=prompt_text,
    seed=42,
    randomize_seed=False,
    width=1080,
    height=1350,
    guidance_scale=3.5,
    num_inference_steps=28,
    api_name="/infer",
)
# result = (image_path, seed)
```

Runner: `social-studio/experiments/run_flux_dev_gradio.py`.

## What FLUX.1-dev responds to

- **Long structured prompts** (up to ~2000 tokens), unlike schnell which
  prefers comma-separated tags.
- **Camera/lens recipes** — 50mm f/2.8 ISO 200 is honored visibly.
- **Lighting direction + color temperature** — actually rendered.
- **HEX colors** — landed reliably.
- **Style anchor brand names** (Mont Blanc, Magnum) — limited training
  association but still tonally useful.
- **Hand anatomy** — significantly better than schnell. Counts 5 fingers.
- **Skin texture** — visible pores, real material rendering. No plastic AI
  default.

## What it still misses

Tested empirically on the Xalq Sigorta Georgia-train brief, 3 seeds:

- **"NOT looking at camera" / "gaze tracks the view" DNA rule** — honored
  ~33% of the time. Two of three seeds had subjects looking at each other
  or at phones together (intimate inward, not editorial-environmental).
- **Brand semiotic anchor** — e.g. a red phone shape can drift to a
  HEART icon (seed 1337 result) reading as a dating-app screen. Must be
  caught in critique pass; regenerate.
- **Specific geography** — "Caucasus viaduct" rendered as generic European
  rail-yard or countryside, not the actual Garabagh/Tbilisi-style steel
  bridge. Specific landmark prompts are still hard.
- **No teeth smile** rule — held ~66% of the time; one seed produced
  visible smile.

Mitigation: generate 3+ seeds, run critique pass, ship only the variant
that passes all DNA dimensions.

## Recommended cascade position

```
Cascade order (`/post` flow, Step 7):
  1. Codex CLI (if extension idle)       — top quality, subscription
  2. → gradio_client FLUX.1-dev           — FREE, 7.5-8/10 quality  ← THIS DIALECT
  3. → Pollinations FLUX schnell          — FREE, 5-6/10 quality
  4. → manual handoff fallback            — copy prompt to chat app
```

The gap between (2) and (3) is large enough that gradio_client should
always be tried before Pollinations when the Space is reachable.

## Failure modes specific to gradio_client path

- **ZeroGPU queue full** — request times out or queues for >10 min. Detect
  via `gradio_client` exception; fall through to (3) Pollinations.
- **Space restarted / down** — HuggingFace cycles free Spaces; if
  `Client("black-forest-labs/FLUX.1-dev")` fails to connect, try the
  mirrored space `multimodalart/FLUX.1-merged` or fall through.
- **Image saved to local temp** — `gradio_client` writes to a `gradio/`
  temp dir; the runner copies to our experiments folder. Cleanup happens
  automatically.

## When to choose this dialect

- ANY campaign where the Codex CLI path is blocked (extension active,
  quota exhausted).
- Bulk variant generation — 3 seeds in ~3 minutes total.
- Initial creative exploration before committing to a Codex high-quality
  final.

## When NOT to choose this dialect

- World-brand-quality final commercial output — still recommend Codex CLI
  GPT Image 2 or fal.ai paid FLUX 2 Pro for premium delivery.
- Time-critical (< 2 min) requests — queue uncertainty makes this
  unreliable for sub-minute turnarounds.
- Specific geography or landmark fidelity needs — FLUX.1-dev still
  generalizes.
