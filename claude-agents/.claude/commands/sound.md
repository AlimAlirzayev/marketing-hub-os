---
description: Generate original music, sound effects, voice-over, or a cloned human voice from a text prompt — the universal "Suno but also SFX and speech" engine. Free-first cascade.
argument-hint: <music|sfx|tts|clone> "<prompt>" [--ref clip] [--duration 30] [--lang az] [--voice ID] [--quality] [--provider ...]
---

# /sound

The OS's universal audio generator. One command makes **music**, **sound effects**,
**voice-over**, and a **cloned human voice** — the goal was "as powerful as Suno, but
universal." It runs on `audio-studio/audio_studio.py` and routes every job through the
free-first cascade in [capabilities.md](../capabilities.md): free paths first, premium
when quality demands it, manual handoff if everything is exhausted. Never a silent drop.

`$ARGUMENTS` = a kind (`music` | `sfx` | `tts` | `clone`), a quoted prompt, then flags.

## The engine (audio-gen cascade)
- **music** — Stable Audio 3 HF Space (free, instrumental) → ElevenLabs `compose_music`
  (**paid plan only** — verified 402 on free) → Lyria (opt) → manual (Suno/Udio for vocals).
- **sfx** — ElevenLabs `sound_effect` (**works on free tier**, gold standard) → Stable Audio 3 (free).
- **tts** — Edge Neural TTS (free, unlimited, native **Azerbaijani**) → ElevenLabs
  (**paid only** for its voices) → Gemini TTS (free).
- **clone** — OmniVoice HF Space (free, 600+ langs incl. **Azerbaijani**): clones a real
  human voice from a `--ref` clip. **The path to natural Azerbaijani** — base is a real person.

> Verified free-tier reality: on a free ElevenLabs key only **SFX** works via API; its
> **music and TTS need a paid plan**. So natural AZ speech = `clone` (free) or paid.
> ElevenLabs is also a raw **MCP server** (`elevenlabs`) for dubbing/transcription.

## Steps
1. **Parse `$ARGUMENTS`** — first token is the kind, then the quoted prompt, then flags:
   `--duration` seconds (music default 30, sfx 4), `--lang` (tts; default `az`),
   `--voice` (tts voice id/name), `--quality` (best-first instead of free-first),
   `--provider` to force one rung, `--out` (default `audio-studio/output`).

2. **Pre-flight.** Run `python audio-studio/audio_studio.py doctor` to see which rungs
   are READY. For `music`/`sfx` with no ElevenLabs key and no working HF Space, say so and
   offer to either add the free key or fall through to the manual handoff — don't pretend.

3. **Run it.**
   ```
   python audio-studio/audio_studio.py music "uplifting corporate ad bed, warm piano, 120bpm" --duration 30
   python audio-studio/audio_studio.py sfx   "glass shatter then coins on a desk" --duration 4
   python audio-studio/audio_studio.py tts   "Salam, Xalq Sigorta sizin yaninizdadir." --lang az
   python audio-studio/audio_studio.py clone "Salam, Xalq Sigorta sizin yaninizdadir." \
       --ref audio-studio/voices/my_voice.m4a --ref-text "<what the clip says>" --lang az
   ```
   `clone` needs a real human `--ref` clip (20-30s, clean) in `audio-studio/voices/`;
   passing `--ref-text` (the clip's transcript) improves fidelity. The clip is
   auto-converted to a clean wav. See `audio-studio/voices/README.md`.

4. **Report** which provider actually ran and why the ones above it were skipped (the CLI
   prints this). Give the output path. **State only what's verifiable** (provider, length,
   size). For voice quality (natural vs robotic) say it needs the user's ear — don't claim
   it sounds good. If it ended in a manual handoff, surface the paste-block.

5. **Offer the handoffs.**
   - Use the bed in a video → `/edit-video` (or drop it in `video-studio/music/`).
   - Natural Azerbaijani voice → `clone` with a real human `--ref` (generate 2-3 takes).
   - Best vocal song → Suno/Udio via the handoff, or a paid ElevenLabs plan.

## Rules
- **Free-first.** Don't spend an ElevenLabs credit when a free rung will do.
- **No silent drops.** A dead HF Space or a missing key → say it and try the next rung.
- **Never call audio "good" from metrics.** Quality (robotic-ness, prosody) needs a human
  ear; report length/size/provider and hand samples to the user to judge.
- **Azerbaijani voice-over is free.** Edge `az-AZ-BabekNeural` / `az-AZ-BanuNeural`; for
  *natural* AZ use `clone` with a real human reference.

## Examples
```
/sound music "cinematic insurance brand intro, hopeful strings, 15s sting" --duration 15
/sound sfx "notification chime, soft, premium fintech" --duration 2
/sound tts "Bayram təbrikinizi Xalq Sığorta ilə paylaşın." --lang az --voice az-AZ-BanuNeural
/sound clone "Sığortanız bir kliklə uzadıldı." --ref audio-studio/voices/agent.m4a --lang az
```
