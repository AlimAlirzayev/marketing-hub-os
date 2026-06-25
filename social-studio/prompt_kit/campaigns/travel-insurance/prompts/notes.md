# Iteration notes — travel-insurance prompt evolution

## v1 → v2 (2026-05-20)

### What broke in v1

| Failure | Frequency | Root cause |
|---|---|---|
| "Couple" interpreted as wrong demographic | ~20% | No age/feature lock |
| Plastic-skin AI face | ~70% | No texture/grain spec |
| Suitcase wrong red (orange-red / maroon) | ~40% | Color named, not HEX'd |
| Stock-photo composition | ~80% | No camera/lens spec |
| Both subjects facing camera | ~50% | No gaze direction spec |
| GPT Image 2 generated entirely off-brief (desk scene) | ~33% | Lead with style not constraint |
| Models drift to "Alps" not "Caucasus" | ~60% | No real-geography anchor |

### What v2 fixed

- Hard constraints come FIRST, before style.
- Subject identity locked at body-text level (hair length, sweater color).
- HEX colors instead of named colors for brand props.
- Camera/lens layer added (50mm f/2.8 ISO 200).
- Lighting layer with Kelvin + ratio.
- Style anchor names real campaigns (Mont Blanc, Hermès), not adjectives.
- Exclusion list ordered by likelihood.

### Known v2 limitations

- Prompt is ~800 words. Some models (older FLUX) truncate at ~300.
  Will need a model-specific compression layer for those.
- "Caucasus viaduct" is still semi-generic — would benefit from a
  proven HF Space LoRA trained on Garabagh / Baku-Tbilisi rail imagery.
- Gaze direction is verbal; for hard adherence we'd need IP-Adapter
  with a reference image (post-MVP).

### What to try in v3

- Add a reference-image conditioning step (when fal.ai or HF-hosted
  IP-Adapter becomes part of the pipeline).
- A/B test removing the "Mont Blanc" anchor — some models drift
  toward "snow mountains" because of that reference.
- Try ordering brand props BEFORE subject identity — see if the
  red suitcase becomes a more reliable anchor.
