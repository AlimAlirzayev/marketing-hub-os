"""Voice I/O for the one-microphone co-pilot — hear Alim, and talk back in Azerbaijani.

Two long-standing pain points, fixed here (2026-07-12):
  1. STT quality. ElevenLabs **Scribe** is, on 2026 benchmarks, the most accurate
     Azerbaijani transcriber (≈3.1% WER on FLEURS — it beats Whisper and Gemini),
     so it is the primary. Groq whisper-large-v3 and Gemini stay as fallbacks so a
     voice note is NEVER dropped just because one provider hiccups.
  2. It never talked back. synthesize() renders a reply to an Azerbaijani voice
     note (ElevenLabs multilingual), so a voice message gets a voice answer — the
     system finally feels like a person on the other end, not a text box.

Cost discipline: TTS runs ONLY for voice-originated turns (not every text), the
spoken text is trimmed and de-marked-down, and everything is env-tunable. Keys
already live in .env (ELEVENLABS_API_KEY, GROQ_API_KEY, GEMINI_API_KEY).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import requests

from . import sense

_EL_KEY = lambda: (os.getenv("ELEVENLABS_API_KEY") or "").strip()  # noqa: E731
_EL_STT = "https://api.elevenlabs.io/v1/speech-to-text"
_EL_TTS = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
# A safe, widely-available multilingual voice; override with ELEVENLABS_DEFAULT_VOICE.
_EL_VOICE = lambda: (os.getenv("ELEVENLABS_DEFAULT_VOICE") or "21m00Tcm4TlvDq8ikWAM").strip()  # noqa: E731
_EL_TTS_MODEL = lambda: os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")  # noqa: E731
_TTS_MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "700"))  # keep voice replies short + cheap
_STT_LANG = os.getenv("STT_LANG", "aze")


# ==========================================================================
# speech -> text : ElevenLabs Scribe (best AZ) -> Groq whisper -> Gemini
# ==========================================================================

def _stt_elevenlabs(audio: bytes) -> str | None:
    key = _EL_KEY()
    if not key:
        return None
    r = requests.post(
        _EL_STT,
        headers={"xi-api-key": key},
        data={"model_id": "scribe_v1", "language_code": _STT_LANG},
        files={"file": ("voice.ogg", audio, "audio/ogg")},
        timeout=120,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"scribe HTTP {r.status_code}: {r.text[:120]}")
    return (r.json().get("text") or "").strip() or None


def _stt_groq(audio: bytes) -> str | None:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        return None
    r = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        data={"model": "whisper-large-v3", "language": "az"},
        files={"file": ("voice.ogg", audio, "audio/ogg")},
        timeout=120,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"groq whisper HTTP {r.status_code}: {r.text[:120]}")
    return (r.json().get("text") or "").strip() or None


def _stt_gemini(audio: bytes) -> str | None:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    from google import genai
    from google.genai import types
    prompt = ("Transcribe this voice message verbatim. It is most likely in "
              "Azerbaijani. Return ONLY the exact transcript, no commentary.")
    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=os.getenv("STT_GEMINI_MODEL", "gemini-2.5-flash"),
        contents=[prompt, types.Part.from_bytes(data=audio, mime_type="audio/ogg")],
    )
    return (resp.text or "").strip() or None


# Ordered cascade: best AZ transcriber first, each a graceful fallback.
_STT_CHAIN = (("elevenlabs-scribe", _stt_elevenlabs),
              ("groq-whisper-v3", _stt_groq),
              ("gemini", _stt_gemini))


def transcribe(audio: bytes) -> str | None:
    """Best-effort Azerbaijani transcription. Tries providers in quality order,
    logging each miss, and returns the first real transcript (or None)."""
    if not audio:
        return None
    for name, fn in _STT_CHAIN:
        try:
            text = fn(audio)
            if text:
                sense.emit("stt", f"transcribed via {name}", {"chars": len(text)})
                return text
        except Exception as exc:  # noqa: BLE001 — fall through to the next provider
            sense.emit("stt", f"{name} stt failed: {exc}")
    return None


# ==========================================================================
# text -> speech : ElevenLabs multilingual, delivered as a Telegram voice note
# ==========================================================================

def _despeechify(text: str) -> str:
    """Strip the bits that sound wrong read aloud (markdown, the source tag,
    urls) and trim to a short, natural spoken reply."""
    import re
    t = re.sub(r"^_\[[^\]]*\]_\s*", "", text)          # leading source tag
    t = re.sub(r"[*_`#>]+", "", t)                       # markdown marks
    t = re.sub(r"https?://\S+", "", t)                   # bare urls
    t = re.sub(r"\n{2,}", ". ", t).replace("\n", " ")
    t = re.sub(r"\s{2,}", " ", t).strip()
    if len(t) > _TTS_MAX_CHARS:
        cut = t[:_TTS_MAX_CHARS]
        t = cut[:cut.rfind(".") + 1] if "." in cut[-120:] else cut + "…"
    return t


def replies_enabled() -> bool:
    """Voice REPLIES are gated behind VOICE_REPLIES=1. Reason: as of 2026-07-12
    every FREE Azerbaijani TTS route is blocked (ElevenLabs free tier forbids API
    TTS; the Gemini keys in .env are invalid). Rather than fire a guaranteed-fail
    API call on every voice turn, the talk-back stays OFF until a working TTS is
    configured — a paid ElevenLabs plan or a valid Gemini key — then flip this on.
    Hearing (STT) is always on and needs no flag."""
    return (os.getenv("VOICE_REPLIES") or "0").strip().lower() in {"1", "true", "yes", "on"}


def _tts_gemini(text: str) -> bytes | None:
    """Gemini TTS (Google AI Studio) -> ogg/opus. Free when the key is valid."""
    key = (os.getenv("GEMINI_TTS_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        return None
    from google import genai
    from google.genai import types
    # The SDK prefers GOOGLE_API_KEY from the env even when another key is passed;
    # hide it so the explicit (valid) key is the one actually used.
    saved = os.environ.pop("GOOGLE_API_KEY", None)
    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=os.getenv("GEMINI_TTS_VOICE", "Kore"))))),
        )
        pcm = resp.candidates[0].content.parts[0].inline_data.data
    finally:
        if saved is not None:
            os.environ["GOOGLE_API_KEY"] = saved
    return _pcm_to_ogg(pcm)  # Gemini returns raw 24kHz s16le mono


def _tts_elevenlabs(text: str) -> bytes | None:
    """ElevenLabs multilingual TTS -> ogg/opus. Needs a PAID plan (free tier
    forbids API TTS with library voices)."""
    key = _EL_KEY()
    if not key:
        return None
    r = requests.post(
        _EL_TTS.format(voice=_EL_VOICE()),
        headers={"xi-api-key": key, "accept": "audio/mpeg"},
        params={"output_format": "mp3_44100_128"},
        json={"text": text, "model_id": _EL_TTS_MODEL(),
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=120,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"elevenlabs HTTP {r.status_code}: {r.text[:100]}")
    return _mp3_to_ogg(r.content) or r.content


def synthesize(text: str) -> bytes | None:
    """Render a reply to an OGG/Opus voice note (Telegram-native). Tries Gemini
    TTS (free) then ElevenLabs (paid); returns None if disabled or all fail, so
    a TTS problem NEVER costs the already-delivered text reply."""
    if not replies_enabled():
        return None
    spoken = _despeechify(text or "")
    if not spoken:
        return None
    for name, fn in (("gemini-tts", _tts_gemini), ("elevenlabs", _tts_elevenlabs)):
        try:
            audio = fn(spoken)
            if audio:
                sense.emit("tts", f"voice reply via {name}", {"chars": len(spoken)})
                return audio
        except Exception as exc:  # noqa: BLE001 — try the next engine
            sense.emit("tts", f"{name} tts failed: {exc}")
    return None


def _pcm_to_ogg(pcm: bytes, rate: int = 24000) -> bytes | None:
    """Wrap raw s16le mono PCM (Gemini TTS output) into ogg/opus via ffmpeg."""
    if not pcm or not shutil.which("ffmpeg"):
        return None
    with tempfile.TemporaryDirectory() as d:
        dst = os.path.join(d, "a.ogg")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1",
             "-i", "pipe:0", "-c:a", "libopus", "-b:a", "48k", dst],
            input=pcm, capture_output=True, timeout=60,
        )
        if proc.returncode != 0 or not os.path.exists(dst):
            return None
        with open(dst, "rb") as fh:
            return fh.read()


def _mp3_to_ogg(mp3: bytes) -> bytes | None:
    """Transcode mp3 -> ogg/opus so Telegram shows a real voice bubble. Needs
    ffmpeg; returns None (caller falls back to mp3) if it's missing."""
    if not shutil.which("ffmpeg"):
        return None
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "a.mp3"), os.path.join(d, "a.ogg")
        with open(src, "wb") as fh:
            fh.write(mp3)
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-c:a", "libopus", "-b:a", "48k", dst],
            capture_output=True, timeout=60,
        )
        if proc.returncode != 0 or not os.path.exists(dst):
            return None
        with open(dst, "rb") as fh:
            return fh.read()


# ==========================================================================
# voice-job registry — bot and worker are threads of ONE supervisor process,
# so a module-level set lets the worker know a job came in by VOICE and should
# be answered by voice too. Bounded so it can't grow without limit.
# ==========================================================================

_voice_jobs: set[int] = set()


def mark_voice_job(job_id: int) -> None:
    _voice_jobs.add(int(job_id))
    if len(_voice_jobs) > 500:  # never unbounded
        _voice_jobs.clear()
        _voice_jobs.add(int(job_id))


def take_voice_job(job_id: int) -> bool:
    """True exactly once if this job originated from a voice message (consumes it)."""
    jid = int(job_id)
    if jid in _voice_jobs:
        _voice_jobs.discard(jid)
        return True
    return False
