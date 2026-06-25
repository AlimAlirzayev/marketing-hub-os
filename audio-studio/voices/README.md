# Reference voices for cloning

Drop a **real human voice recording** here, then clone it to speak any text in natural
Azerbaijani (or another language). The cloned output copies the reference speaker's
**timbre and style** — this is the path to natural AZ speech, because the base is a real
person, not a synthetic engine.

## What makes a good reference clip

| Requirement | Why |
|---|---|
| **20-30 seconds** (10s minimum) | Enough for the model to capture the voice. |
| **One speaker, no overlap** | Mixed voices confuse the clone. |
| **Clean — no music / noise / echo** | Background leaks into the clone. |
| **Natural, calm speaking tone** | The clone copies delivery, not just timbre. |
| **Same language as the target** (Azerbaijani in → Azerbaijani out) | Best pronunciation; cross-lingual works but is weaker. |

Any format works (`mp3`, `m4a`, `wav`, `ogg`) — Audio Studio auto-converts it to a clean
24 kHz mono wav before sending. Files here are **git-ignored** (keep voices private; you
need consent to clone a real person).

## Use it

```powershell
# Best fidelity: also pass the transcript of what the reference clip says.
python audio-studio\audio_studio.py clone "Salam, Xalq Sigorta sizin yaninizdadir." `
  --ref audio-studio\voices\my_voice.m4a `
  --ref-text "<exactly what is said in my_voice.m4a>" `
  --lang az
```

Or from Claude Code: `/sound clone "<text>" --ref audio-studio/voices/my_voice.m4a`.

Output lands in `audio-studio/output/clone_*.wav`. Tune with `--speed` (0.8-1.2) and
`--du <seconds>` if the length looks off. Engine: the free OmniVoice HF Space
(`AUDIO_HF_CLONE_SPACE`), which lists Azerbaijani among 600+ languages.

> Quality is judged by **your ear**, not by file size. Generate 2-3 takes and pick the
> most natural — the tool can't hear robotic-ness, you can.
