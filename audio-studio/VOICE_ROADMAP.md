# Personal Azerbaijani Voice — build roadmap (2026 SOTA research)

Goal: our own AZ voice agent that rivals ElevenLabs / Gemini native-audio — natural prosody +
cloning of a specific person. Grounded in a 2026 SOTA sweep (sources at bottom). Constraint:
corporate Win11, **no local ML training** → free hosted GPU (Colab/Kaggle/Fal), HF Spaces.

## The hard truths (why this is the plan)
1. **No 2026 engine natively supports Azerbaijani.** Turkish is the usable Turkic neighbor
   (in XTTS-v2, VoxCPM2, Chatterbox, CosyVoice3). `espeak-ng az` gives AZ→IPA — our key asset.
2. **No usable public AZ voice corpus** (Common Voice az ≈ 0.49 validated hrs). A true personal
   voice **requires recording our own** 20–60 min of the target speaker. Unavoidable.
3. **OmniVoice (current) is real SOTA**, not a dead end — weak prosody is likely under-tuned
   params, fixable before any training.
4. **Auto-judge:** ASR round-trip CER (language-grounded for AZ) is trustworthy; UTMOS-style MOS
   is English-trained → only a *relative* naturalness hint, never an absolute AZ score.

## Phases
| Phase | What | Tools | Cost | Status |
|------|------|-------|------|--------|
| **0 — Tune OmniVoice** | sweep `--ns 64 --gs 2.5 --by-sentence`, correct `du`; A/B vs defaults | existing `clone` | $0 | leverages built flags |
| **1 — Bake-off + auto-judge** | add VoxCPM2 (Turkish slot) + Qwen3-TTS clone rungs; pick best take by ASR-CER | gradio_client, Gemini ASR | $0 (ZeroGPU) | **judge BUILT** (`--best-of N`); rungs TODO |
| **2 — Record the corpus** | 30–60 min clean AZ from the target speaker; segment + transcribe → `wav\|text\|speaker` | mic, ffmpeg, Whisper/Gemini | $0 | **GATING — needs the user** |
| **3 — XTTS-v2 personal finetune** | extend_vocab(az) → finetune GPT on free T4 → wire `xtts-personal` rung | Colab/Kaggle T4, anhnh2002 recipe | $0 | after Phase 2 |
| **4 — Frontier (optional)** | replicate X-Voice (F5-TTS + espeak-ng `az` IPA) on our data; seed-vc timbre polish | X-Voice/F5, espeak-ng | $0 | optional, highest ceiling |
| **5 — Prosody-by-purpose** | style presets (ad/warning/support) via instruct prompts + reference-style bank | already started (`--purpose/--brief`) | $0 | **layer BUILT**, extend |

## What's already built (this round)
- **Gemini 3.1 native-audio TTS** rung (`tts --provider gemini --voice ...`) — most natural
  synthetic AZ; ⚠️ free output not licensed for commercial use.
- **Voice-brief layer** (`--purpose | --style | --brief`) — purpose-driven delivery (Phase 5 start).
- **Auto-judge / best-of-N** (`--best-of N`) — ASR-CER selection of the clearest take (Phase 1 core).
- **OmniVoice clone** with `--by-sentence / --ns / --gs / --du` (Phase 0 levers) + ffmpeg post-processing.

## The one thing only the user can do
**Record 30–60 min of the target Azerbaijani voice** (one speaker, clean, no music), drop it in
`audio-studio/voices/`. Everything in Phases 3–4 (the true personal voice) is gated on this.

## Top-3 free experiments (no training)
1. Tune OmniVoice: `clone "<az>" --ref voices/me.wav --by-sentence --ns 64 --gs 2.5 --best-of 3`
2. Bake-off vs `openbmb/VoxCPM-Demo` (Turkish slot) and `Qwen/Qwen3-TTS` (clone) — same script/ref.
3. Auto-judge everything with `--best-of N` (CER) + the ear for naturalness.

## Sources
X-Voice (arXiv 2605.05611) · OmniVoice (arXiv 2604.00688) · VoxCPM (2509.24650) · XTTS-v2 new-lang
recipe (github anhnh2002/XTTSv2-Finetuning-for-New-Languages) · espeak-ng (az) · UTMOSv2 · seed-vc ·
Common Voice cv-dataset (az 0.49h) · Gemini 3.1 Flash TTS. Full list in the research transcript.
