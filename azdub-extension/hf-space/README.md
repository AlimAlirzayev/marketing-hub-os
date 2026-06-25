---
title: AZDub TTS
emoji: sound
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# AZDub TTS

HTTPS TTS proxy for the AZ Dublyaj Chrome extension.

The default provider is `edge-tts`, which exposes Microsoft's free Azerbaijani
voices (`az-AZ-BabekNeural`, `az-AZ-BanuNeural`) over a simple HTTPS endpoint.
This is useful as a free fallback, but it is not the quality ceiling for natural
dubbing.

For a stronger no-payment path, run this proxy with Google AI Studio / Gemini
TTS free tier. For the highest-quality paid voice cloning path, use ElevenLabs.

## Endpoint

```text
GET /tts?text=<text>&voice=az-AZ-BabekNeural&rate=+0%&pitch=+0Hz
-> audio/mpeg (MP3)
```

The extension does not need to change: point its TTS proxy setting at this Space.
Provider selection happens on the server.

## Free fallback

No environment variables are required.

```text
TTS_PROVIDER=edge
```

## Free-tier Gemini TTS

Gemini TTS supports Azerbaijani (`az-AZ`) in preview and Turkish (`tr-TR`) as a
GA language. It needs a Google AI Studio API key, but can run on the Gemini API
free tier while you stay within the free limits.

```text
TTS_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview
GEMINI_TTS_LANGUAGE=az-AZ
GEMINI_TTS_VOICE=Kore
```

For Turkish output instead of Azerbaijani:

```text
GEMINI_TTS_LANGUAGE=tr-TR
```

## Paid higher-quality Azerbaijani voice

Add these as Hugging Face Space secrets, not as committed files:

```text
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
ELEVENLABS_MODEL_ID=eleven_v3
```

Optional tuning:

```text
ELEVENLABS_LANGUAGE_CODE=az
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
ELEVENLABS_STABILITY=0.45
ELEVENLABS_SIMILARITY=0.85
ELEVENLABS_STYLE=0.35
ELEVENLABS_SPEAKER_BOOST=true
```

Use `ELEVENLABS_VOICE_ID` for the exact voice you want. For the best result,
create or choose a real Azerbaijani voice in ElevenLabs, then paste that voice ID
into the Space secret.

## Local checks

```bash
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 7860
curl "http://127.0.0.1:7860/tts?text=Salam&voice=az-AZ-BabekNeural" --output out.mp3
```

CORS is open (`*`) so the Chrome extension can call the proxy from YouTube.
