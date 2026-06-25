# AZ Dublyaj - YouTube Azerbaijani auto-dubbing

Chrome extension that translates YouTube captions to Azerbaijani and plays a
dubbed Azerbaijani voice over the video. Turkish and Azerbaijani source videos
are skipped by default.

## Important quality note

The free Microsoft Edge voices (`az-AZ-BabekNeural`, `az-AZ-BanuNeural`) work as
a fallback, but they are not enough for high-quality dubbing. If the result
sounds robotic or not convincingly Azerbaijani, that is a TTS-provider ceiling,
not only an extension bug.

For a no-payment upgrade path, use the `hf-space` proxy with Google AI Studio /
Gemini TTS free tier. For production-quality paid voice cloning, use ElevenLabs
v3 and a selected or cloned Azerbaijani voice. The extension can keep calling
the same `/tts` endpoint; the server chooses the provider.

## How it works

1. Reads the video's caption tracks from YouTube's player response.
2. Detects the spoken language from the preferred ASR caption track.
3. Skips source languages configured in settings, defaulting to `az` and `tr`.
4. Fetches a timestamped transcript when YouTube exposes one, otherwise falls
   back to live caption scraping.
5. Translates each phrase to Azerbaijani with free translation endpoints.
6. Requests Azerbaijani audio from the configured TTS proxy.
7. Plays the dubbed audio in sync while muting or ducking the original audio.

## Recommended TTS setup

Deploy `hf-space/` as a Hugging Face Docker Space and point the extension's
`TTS server` setting to that Space URL.

Free fallback:

```text
TTS_PROVIDER=edge
```

Free-tier Gemini path:

```text
TTS_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview
GEMINI_TTS_LANGUAGE=az-AZ
GEMINI_TTS_VOICE=Kore
```

Turkish fallback experiment:

```text
GEMINI_TTS_LANGUAGE=tr-TR
```

Paid voice-clone path:

```text
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
ELEVENLABS_MODEL_ID=eleven_v3
```

Store these values as Space secrets. Do not commit API keys.

## Install unpacked

1. Open `chrome://extensions`.
2. Enable `Developer mode`.
3. Click `Load unpacked` and select this `azdub-extension` folder.
4. Open a non-AZ/TR YouTube video and set the TTS proxy URL in the popup.

## Limitations

- YouTube must expose captions or live caption text. Some automated browser
  sessions cannot access caption text even when a human browser can.
- This is phrase-level sync, not true lip-sync.
- Free translation endpoints can be inconsistent.
- Browser `speechSynthesis` fallback is low quality for Azerbaijani and should
  be disabled for serious testing.
- Stable Diffusion-style tools are image generation tools, not TTS engines; they
  do not solve the voice quality issue.
- Full products such as HeyGen, Rask AI, Checksub, and similar tools combine
  stronger TTS or voice cloning with transcript editing, audio separation, and
  sometimes lip-sync. This extension is now structured to use a better TTS
  provider, but it does not yet perform full video post-production.

## Files

- `manifest.json` - MV3 config.
- `background.js` - translation and TTS request routing.
- `inject.js` - MAIN-world bridge that reads the YouTube player response.
- `content.js` - orchestration, sync, and playback.
- `popup.html` / `popup.js` / `popup.css` - settings UI.
- `styles.css` - on-page status badge.
- `hf-space/` - deployable FastAPI TTS proxy.
