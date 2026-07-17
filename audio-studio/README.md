# Audio Studio — universal music / sfx / voice generator

The OS's answer to *"add something as powerful as Suno, but universal."* One CLI makes
**music**, **sound effects**, **voice-over**, and a **cloned human voice**, each routed
through a free-first provider cascade (see
[capabilities.md](../claude-agents/.claude/capabilities.md) → `audio-gen`). Everything is
a **hosted API** — no GPU, no native ML runtime — so it runs fine under the corporate-Win11
lockdown.

## What's verified (2026-06-18, live)

We surveyed the 2026 landscape (Suno, Udio, Mureka, Mubert, Lyria, MusicGen, Stable Audio,
ElevenLabs) and tested each rung. **ElevenLabs** is the only *universal* engine (music +
sfx + tts + cloning, one API, official MCP) — but on a **free** key only **sound effects**
work via API; its **music and TTS return HTTP 402 (paid plan required)**. So the working
free stack is Edge/Gemini TTS, Stable Audio 3, ElevenLabs SFX, and OmniVoice cloning.

| Need | Free path (works today) | Premium / upgrade |
|------|-------------------------|-------------------|
| Music bed | **Stable Audio 3** HF Space (instrumental) | ElevenLabs `compose_music` (paid) → Suno/Udio for vocals |
| Sound effect | **ElevenLabs `sound_effect`** (free tier) · Stable Audio 3 | — |
| Voice-over | **Edge Neural TTS** (free, native AZ) · Gemini TTS | ElevenLabs TTS (paid) |
| **Natural** Azerbaijani voice | **OmniVoice clone** from a real human `--ref` clip | paid ElevenLabs clone |

> ⚠️ Synthetic AZ TTS (Edge/Gemini) sounds **robotic** to a native ear — that's the engine
> ceiling, not a bug. The natural path is **voice cloning** (`clone`) from a real human
> recording. Audio quality is a **human-ear** call; this tool reports length/size/provider,
> never "it sounds good."

## Install

```powershell
pip install -r audio-studio\requirements.txt   # all hosted APIs; install only what you need
```

All three free paths are proven live (2026-06-12): **voice-over** via `edge-tts`
(native Azerbaijani), **music** and **sound effects** via the Stable Audio 3 HF Space
(`/infer`, free). ElevenLabs is the premium tier on top — add a free key for
studio-grade music, voice cloning and dubbing:

1. Get a key (10k credits/mo): https://elevenlabs.io/app/settings/api-keys
2. Put `ELEVENLABS_API_KEY=...` in the project-root `.env`.
3. Re-run `powershell scripts\setup-mcp.ps1` so the `elevenlabs` MCP server picks it up.

## Use

```powershell
python audio-studio\audio_studio.py doctor                          # which rungs are READY
python audio-studio\audio_studio.py tts   "Salam, Xalq Sigorta." --lang az   # FREE, works now
python audio-studio\audio_studio.py music "uplifting corporate bed, 120bpm" --duration 30
python audio-studio\audio_studio.py sfx   "glass shatter then coins" --duration 4
python audio-studio\audio_studio.py voices                          # list usable voices
```

### Natural Azerbaijani via voice cloning

The path to a non-robotic AZ voice: clone a **real human** recording.

```powershell
# House voice (voices\ramin_ref.wav + cached transcript) — no --ref needed:
python audio-studio\audio_studio.py clone "Salam, Xalq Sigorta sizin yaninizdadir." --lang az

# Or any other clip: put a 20-30s clean human clip in audio-studio\voices\ and pass it
# (with --ref-text, its transcript, for best fidelity):
python audio-studio\audio_studio.py clone "Salam, Xalq Sigorta sizin yaninizdadir." `
  --ref audio-studio\voices\my_voice.m4a --ref-text "<what the clip says>" --lang az
```

The default reference comes from `AUDIO_DEFAULT_REF` (falls back to `voices\ramin_ref.wav`).

Any container (mp3/m4a/wav/ogg) is auto-converted to a clean 24 kHz mono wav. Tune with
`--speed` (0.8-1.2) and `--du <seconds>`. Engine: free OmniVoice HF Space
(`AUDIO_HF_CLONE_SPACE`). Generate 2-3 takes and pick the most natural by ear.

From Claude Code, use the **`/sound`** slash command — same engine, free-first routing,
honest provider reporting.

Flags: `--duration`, `--out`, `--lang`, `--voice`, `--ref`/`--ref-text` (clone),
`--speed`, `--quality` (best-first), `--provider ...` (force one rung), `--json`.

## How the cascade behaves

It mirrors the OS router contract exactly: it tries each provider cheapest→best, **skips**
an unconfigured one while noting *why*, **logs** any failure and moves on, and ends on a
**manual handoff** (a paste-block of Suno/Udio/ElevenLabs links + your prompt) if nothing
worked. It never silently drops the feature. The output line tells you which provider ran.

## Notes

- HuggingFace Space ids drift; if a music/sfx/clone call fails on a signature mismatch,
  point `AUDIO_HF_MUSIC_SPACE` / `AUDIO_HF_SFX_SPACE` / `AUDIO_HF_CLONE_SPACE` at a
  known-good space (`/scout` does this).
- Clone needs a **non-empty, valid** reference; a 0-byte/corrupt file makes the Space throw
  a server-side `EOFError`. The provider checks size and re-encodes via ffmpeg first.
- Lyria 3 (Gemini) is off by default (`AUDIO_ENABLE_LYRIA=0`) because it can bill.
- `video-studio/render.py` can call this engine to *generate* a bed when its royalty-free
  library has no matching mood (set `AUDIO_STUDIO_GENERATE=1`).
