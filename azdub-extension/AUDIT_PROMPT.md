# Audit & Test Task: "AZ Dublyaj" Chrome Extension + HF TTS proxy

> Codex: read this whole file and execute it. All paths are relative to the repo
> root; the extension lives in `azdub-extension/`. Produce the audit report
> described at the end. Be skeptical and evidence-driven — do not assume anything
> works without proving it.

You are auditing a Manifest V3 Chrome extension that auto-dubs YouTube videos into
Azerbaijani in real time, plus its companion edge-tts HTTPS proxy. Your job is to
**rigorously verify whether it actually works, find every real bug, and report
precisely** — with evidence, not assumptions. Fix bugs only after listing them.

## Repo layout
```
azdub-extension/
  manifest.json          # MV3 config (permissions, content_scripts, host_permissions)
  background.js          # service worker: translation + Edge TTS (WSS) + HTTPS proxy TTS
  content.js             # isolated-world orchestrator: detect lang, transcript, sync playback
  inject.js              # MAIN-world bridge: reads movie_player, enable/disable captions, mute
  styles.css             # status badge + caption-hide CSS
  popup.html/js/css      # settings UI (voice, rate, skip langs, mute, TTS proxy URL)
  README.md
  hf-space/              # the TTS proxy (deploys to a Hugging Face Docker Space)
    Dockerfile
    app.py               # FastAPI: GET /tts?text=&voice=&rate=&pitch= -> audio/mpeg
    requirements.txt
    README.md
```

## Intended behavior (the spec to verify against)
1. On a `youtube.com/watch` page, detect the spoken language from the caption
   tracks (the `asr` track's `languageCode`).
2. If language starts with `az` or `tr` → do nothing (configurable skip list).
3. Otherwise obtain the transcript via a 3-layer fallback:
   (a) capture YouTube's own `/api/timedtext` request URL via `webRequest` and
   re-fetch with `fmt=json3`; (b) the raw player-response `baseUrl`; (c) **live
   DOM caption-scraping** (read `.ytp-caption-segment` text, dedup the rolling
   window with `deltaWords`).
4. Translate each phrase to Azerbaijani (free Google gtx endpoint, MyMemory
   fallback).
5. Synthesize Azerbaijani neural speech, TTS order: **HTTPS proxy (HF Space
   edge-tts) → direct Edge WebSocket → browser speechSynthesis**.
6. Play the audio in sync, mute the original (via `video.muted` AND the player
   API `movie_player.mute()`); hold the picture when the dub backlog grows so no
   content is lost.

## Established facts (already discovered — do NOT re-litigate, just confirm)
- YouTube `/api/timedtext` now returns HTTP 200 + empty body without a `pot`
  token, even for the player's own fully-signed request → the live DOM-scraping
  path is the working one for such videos.
- Browser-direct Edge TTS WebSocket fails (`WebSocket error`) because Microsoft
  validates handshake Origin/headers a browser WebSocket can't set, and/or the
  network blocks `speech.platform.bing.com`. Hence the server-side HF proxy.
- Translation and muting were observed working in a real browser.

## Environment setup
- Use Node.js (for JS static checks + unit tests) and Python 3.11 (for the proxy).
- Do NOT read, modify, commit, or print the repo's `.env` file or any secrets.
  This project needs **no API keys**.

## Verification tasks — produce evidence for each

### A. Static integrity
1. `node --check` every `.js` file; confirm zero syntax errors.
2. Validate `manifest.json` parses and that every file it references exists, that
   `host_permissions` cover every URL fetched in code (youtube.com, translate.
   googleapis.com, api.mymemory.translated.net, speech.platform.bing.com, *.hf.space),
   and that `world: "MAIN"` + `webRequest` are present and consistent.
3. Grep for undefined identifiers / mismatched message `type`s between
   `content.js` ↔ `background.js` and the `__azdub` postMessage protocol
   between `content.js` ↔ `inject.js`. List any mismatch.

### B. Unit-test the pure logic (write real tests, run them)
Extract and test these functions in Node:
4. `generateSecMsGec` (background.js) — **token parity**: install Python
   `edge-tts`, monkeypatch/pin the clock to a fixed epoch, and assert the JS
   output EXACTLY equals Python `edge_tts.drm.DRM.generate_sec_ms_gec()` for the
   same timestamp (and across a few 5-minute boundaries). The JS uses IEEE-double
   math + `toFixed(0)` to mimic Python `float` + `:.0f`; verify they truly match,
   including the large-number formatting. Report PASS/FAIL with the actual values.
5. `deltaWords` / `lastWords` (content.js) — feed simulated rolling-ASR caption
   sequences (window scrolls word-by-word) and assert no words are dropped and
   none are spoken twice.
6. `buildPhrases` — assert sentence/gap/length splitting is sane.
7. `parseJson3` and `parseXmlTranscript` — feed real json3 and srv1/srv3 samples
   and assert correct `{startMs,durMs,text}` extraction and HTML-entity decoding.

### C. The TTS proxy (run it for real)
8. `cd azdub-extension/hf-space && pip install -r requirements.txt && uvicorn app:app --port 7860`.
9. `curl "http://localhost:7860/tts?text=Salam,%20bu%20Bab%C9%99k%20s%C9%99sidir&voice=az-AZ-BabekNeural" -o out.mp3`
   — assert HTTP 200, `Content-Type: audio/mpeg`, non-empty valid MP3 (check magic
   bytes / `ffprobe`), and audible duration > 0. Repeat for `az-AZ-BanuNeural`.
10. Confirm CORS headers are present and the Dockerfile builds (`docker build .`).

### D. End-to-end in a real browser (the decisive test)
11. Using Playwright or Puppeteer with the unpacked extension loaded
    (`--load-extension`, non-headless or `headless: "new"`), open a **narrated**
    English YouTube video and a known **az** and **tr** video. Capture all
    `[AZDUB]` page-console logs and `[AZDUB-bg]` service-worker logs.
12. Assert: az/tr videos are skipped; the English video reaches `tr ok=true` (AZ
    text) and `tts ok=true via:"proxy"` (point `ttsProxyUrl` at the running local
    proxy from step 8), the `<video>` element is muted, and dub audio elements are
    created and play. Note any phrase loss, overlap, or desync.
13. Verify SPA navigation: navigate between videos without reload and confirm the
    session tears down and re-evaluates correctly (no leaked intervals/listeners,
    no double audio).

### E. High-risk areas to scrutinize specifically
- MV3 service-worker `WebSocket` lifetime and whether async `sendResponse`
  (returning `true`) ever drops the message port → silent `tts/translate` failure.
- `Audio.play()` autoplay-policy rejection without a user gesture.
- Current YouTube DOM: confirm `#movie_player.getPlayerResponse()`,
  `setOption("captions","track",...)`, `.ytp-caption-window-container`,
  `.ytp-caption-segment` still exist; flag if YouTube changed them.
- `bridge()` 1500 ms timeout vs. how long `enableCaptions` actually takes.
- Drift-guard auto-pause/resume races (user pause vs our pause) in both
  `DubSession` and `LiveDubSession`.
- GET URL length for `/tts` with long phrases; proxy cold-start (HF sleeps).
- Memory leaks: `setInterval`/event listeners cleared on `destroy()`.

## Deliverable
Output a single audit report:
- **Verdict:** does it work end-to-end? (yes / partly / no) with the strongest
  evidence (log excerpts, test results, mp3 validation).
- **Findings table:** each issue → severity (blocker/major/minor) → `file:line` →
  what's wrong → concrete fix.
- **Test artifacts:** the unit tests you wrote and their pass/fail output.
- Only after reporting, apply fixes for blocker/major issues and re-run the
  relevant checks, showing before/after.
Be precise and skeptical: if you cannot verify something (e.g., real YouTube
behavior in CI), say so explicitly rather than assuming it works.
