#!/usr/bin/env python3
"""
Audio Studio - the universal audio/music/voice generator for Xalq Insurance Digital OS.

One CLI, four capabilities (music, sound effects, speech, voice), each routed through a
free-first provider cascade exactly like claude-agents/.claude/capabilities.md prescribes:

    for provider in cascade(capability):     # cheapest -> best
        if not provider.configured:  skip (note why)
        try:    return provider.run(job)      # success -> stop
        except: log + try next                # NEVER drop silently
    return manual_handoff(job)                # cascade exhausted

The headline engine is ElevenLabs (compose_music + sound_effect + text_to_speech +
voice cloning, one API, 10k free credits/month) - the "Suno-class but universal" pick.
Free paths (HuggingFace Spaces, Microsoft Edge Neural TTS) come first so we only spend
ElevenLabs credits when a free path can't do the job.

Usage:
    python audio-studio/audio_studio.py music "uplifting corporate ad bed, warm piano, 120bpm" --duration 30
    python audio-studio/audio_studio.py sfx   "glass shatter then coins falling on a desk" --duration 4
    python audio-studio/audio_studio.py tts   "Salam, Xalq Sigorta sizin yaninizdadir." --lang az
    python audio-studio/audio_studio.py voices                      # list usable voices
    python audio-studio/audio_studio.py doctor                      # show which providers are ready

Flags:
    --duration N      length in seconds (music/sfx)
    --out DIR         output directory (default: audio-studio/output)
    --provider NAME   force one provider (hf | elevenlabs | lyria | edge | gemini)
    --quality         put the best provider first instead of free-first
    --lang CODE       tts language hint (az, en, ru, tr ...)
    --voice ID|NAME   tts voice override
    --json            print a machine-readable result line

All keys are read from the project-root .env. Nothing here needs a GPU or a native ML
runtime - every provider is a hosted API, matching the corporate-Win11 constraints.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- paths / env

ROOT = Path(__file__).resolve().parent.parent          # ramin-os/
STUDIO = Path(__file__).resolve().parent               # ramin-os/audio-studio/
DEFAULT_OUT = STUDIO / "output"


def _load_env() -> None:
    """Load ramin-os/.env into os.environ without overwriting already-set vars."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(ROOT / ".env")
        return
    except Exception:
        pass
    # Minimal fallback parser so the studio runs even without python-dotenv.
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_env()

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
HF_TOKEN = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
GOOGLE_KEY = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()

# Configurable HF Spaces (the market moves weekly - keep these in .env, not hardcoded).
HF_MUSIC_SPACE = os.environ.get("AUDIO_HF_MUSIC_SPACE", "stabilityai/stable-audio-3").strip()
HF_SFX_SPACE = os.environ.get("AUDIO_HF_SFX_SPACE", "stabilityai/stable-audio-3").strip()
ENABLE_LYRIA = os.environ.get("AUDIO_ENABLE_LYRIA", "").strip().lower() in {"1", "true", "yes"}

# ElevenLabs voice defaults. "Rachel" is a stock multilingual voice present on every account.
ELEVEN_DEFAULT_VOICE = os.environ.get("ELEVENLABS_DEFAULT_VOICE", "21m00Tcm4TlvDq8ikWAM").strip()

# Microsoft Edge Neural TTS voices per language (free, unlimited, same engine the
# azdub-extension already uses). Azerbaijani is natively supported.
EDGE_VOICES = {
    "az": "az-AZ-BabekNeural",
    "az-f": "az-AZ-BanuNeural",
    "en": "en-US-AriaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "tr": "tr-TR-EmelNeural",
}

# Voice cloning: a free HF Space that clones a real human voice from a reference clip.
# OmniVoice (k2-fsa) confirmed to list 'Azerbaijani' + a /_clone_fn endpoint. This is the
# path to *natural* Azerbaijani speech: the timbre comes from a real human sample, not a
# synthetic engine. The lang code -> the Space's dropdown label.
HF_CLONE_SPACE = os.environ.get("AUDIO_HF_CLONE_SPACE", "k2-fsa/OmniVoice").strip()
CLONE_LANG_NAMES = {
    "az": "Azerbaijani", "en": "English", "ru": "Russian", "tr": "Turkish",
    "auto": "Auto",
}

# Gemini native-audio TTS (the family from the Ozan Sihay reel). 3.1 Flash TTS is far more
# natural than the old 2.5 preview and our key has access; it speaks Azerbaijani. 30+
# prebuilt voices, prompt-steerable. ⚠️ free-tier audio output is NOT licensed for
# commercial use — route final commercial renders through paid Cloud Billing.
GEMINI_TTS_MODEL = os.environ.get("AUDIO_GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview").strip()
GEMINI_TTS_FALLBACK = "gemini-2.5-flash-preview-tts"
GEMINI_DEFAULT_VOICE = os.environ.get("AUDIO_GEMINI_VOICE", "Kore").strip()
GEMINI_VOICES = ["Kore", "Aoede", "Leda", "Zephyr", "Charon", "Puck", "Fenrir", "Orus"]

# The voice BRIEF layer. Gemini native-audio TTS is prompt-steerable: a leading delivery
# instruction changes intonation/tone/pacing for the SAME text. Purpose drives delivery, so
# each marketing purpose maps to a crafted instruction + a recommended voice. (Keys in AZ+EN.)
PURPOSE_PRESETS = {
    "reklam": {"voice": "Puck",   "instruct": "Deliver like a polished, upbeat radio-ad voiceover: warm, confident and persuasive, with energy and a subtle smile, building to a clear call to action"},
    "ad":     {"voice": "Puck",   "instruct": "Deliver like a polished, upbeat radio-ad voiceover: warm, confident and persuasive, with energy and a subtle smile, building to a clear call to action"},
    "izah":   {"voice": "Charon", "instruct": "Speak clearly and calmly like a friendly expert explaining something simply: measured, patient and reassuring"},
    "explainer": {"voice": "Charon", "instruct": "Speak clearly and calmly like a friendly expert explaining something simply: measured, patient and reassuring"},
    "tebrik": {"voice": "Aoede",  "instruct": "Speak joyfully, warmly and heartfelt, celebrating a happy occasion, with genuine emotion"},
    "congrats": {"voice": "Aoede","instruct": "Speak joyfully, warmly and heartfelt, celebrating a happy occasion, with genuine emotion"},
    "xeberdarliq": {"voice": "Kore", "instruct": "Speak in a serious, clear, calm-but-urgent and authoritative tone, reassuring rather than alarming"},
    "warning": {"voice": "Kore",  "instruct": "Speak in a serious, clear, calm-but-urgent and authoritative tone, reassuring rather than alarming"},
    "destek": {"voice": "Aoede",  "instruct": "Speak softly and empathetically, caring and reassuring, like a supportive customer-care agent"},
    "support": {"voice": "Aoede", "instruct": "Speak softly and empathetically, caring and reassuring, like a supportive customer-care agent"},
    "elan":   {"voice": "Charon", "instruct": "Speak formally and authoritatively, like an official announcement: clear, composed and dignified"},
    "xeber":  {"voice": "Kore",   "instruct": "Speak like a professional news anchor: neutral, clear and well-paced"},
    "news":   {"voice": "Kore",   "instruct": "Speak like a professional news anchor: neutral, clear and well-paced"},
}


def _craft_style_instruction(brief: str) -> str:
    """Turn a freeform purpose (any language) into a concise English delivery instruction for
    Gemini TTS. This is the 'powerful prompt' layer: purpose -> how it should sound. Falls
    back to the brief itself if no LLM is reachable."""
    brief = (brief or "").strip()
    if not brief or not GOOGLE_KEY:
        return brief
    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=GOOGLE_KEY)
        prompt = (
            "You direct a voice actor. Turn the following creative brief into ONE concise "
            "English delivery instruction describing tone, emotion, pace and energy (no quotes, "
            "no preamble, max 30 words). It must NOT include the words to be spoken.\n\n"
            f"Brief: {brief}"
        )
        r = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        out = (r.text or "").strip().strip('"')
        return out or brief
    except Exception:
        return brief


def _voice_steer(job: dict) -> tuple[str, str | None]:
    """Resolve the delivery instruction + a recommended voice from the job's style controls.
    Priority: explicit --style > --purpose preset > --brief (LLM-crafted)."""
    style = (job.get("style") or "").strip()
    if style:
        return style, None
    purpose = (job.get("purpose") or "").strip().lower()
    if purpose:
        preset = PURPOSE_PRESETS.get(purpose)
        if preset:
            return preset["instruct"], preset["voice"]
        return _craft_style_instruction(purpose), None   # unknown purpose → treat as a brief
    brief = (job.get("brief") or "").strip()
    if brief:
        return _craft_style_instruction(brief), None
    return "", None


# --------------------------------------------------------------------------- cascade core

class ProviderSkipped(Exception):
    """Provider not configured / unavailable - skip and note why (not an error)."""


class ProviderFailed(Exception):
    """Provider was configured but the call failed - log and try the next one."""


def log(msg: str) -> None:
    print(f"   {msg}", file=sys.stderr)


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (s[:n] or "audio").strip("-")


def _out_path(out_dir: Path, kind: str, prompt: str, ext: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return out_dir / f"{kind}_{stamp}_{_slug(prompt)}.{ext}"


def run_cascade(capability: str, providers: list, job: dict) -> dict:
    """Walk the ordered providers; return the first success or a manual handoff.

    Mirrors the capabilities.md algorithm: skip unconfigured providers (noting why),
    try each configured one, never drop silently, end on a labelled manual handoff.
    """
    print(f"==> {capability}: routing through {len(providers)} provider(s)", file=sys.stderr)
    skipped: list[str] = []
    for name, fn in providers:
        try:
            log(f"-> trying '{name}' ...")
            result = fn(job)
            print(f"==> {capability}: produced by '{name}'", file=sys.stderr)
            if skipped:
                log(f"(skipped above: {', '.join(skipped)})")
            result["provider"] = name
            result["capability"] = capability
            return result
        except ProviderSkipped as e:
            skipped.append(f"{name} ({e})")
            log(f"   skip '{name}': {e}")
        except ProviderFailed as e:
            skipped.append(f"{name} (failed: {e})")
            log(f"   FAIL '{name}': {e}")
        except Exception as e:  # defensive: never let one provider crash the cascade
            skipped.append(f"{name} (error: {e})")
            log(f"   ERROR '{name}': {e}")
    return _manual_handoff(capability, job, skipped)


def _manual_handoff(capability: str, job: dict, skipped: list[str]) -> dict:
    """Cascade exhausted: print one paste-block with the best web tools. No silent drop."""
    prompt = job.get("prompt", "")
    links = {
        "music": [
            ("Suno (best song quality)", "https://suno.com/create"),
            ("Udio (UMG/WMG licensed)", "https://www.udio.com"),
            ("ElevenLabs Music", "https://elevenlabs.io/music"),
        ],
        "sfx": [("ElevenLabs SFX", "https://elevenlabs.io/sound-effects")],
        "tts": [("ElevenLabs TTS", "https://elevenlabs.io/text-to-speech")],
    }.get(capability, [])
    print(f"\n==> {capability}: cascade exhausted - MANUAL HANDOFF", file=sys.stderr)
    if skipped:
        log("why each provider was skipped:")
        for s in skipped:
            log(f"   - {s}")
    print("\n----- paste this prompt into one of these -----")
    for label, url in links:
        print(f"  {label}: {url}")
    print(f"\nPrompt:\n  {prompt}\n----------------------------------------------")
    return {"capability": capability, "provider": "manual", "path": None, "prompt": prompt}


# --------------------------------------------------------------------------- providers: MUSIC

def music_hf(job: dict) -> dict:
    """Free: a HuggingFace Space (MusicGen by default). Needs gradio_client; HF_TOKEN optional."""
    try:
        from gradio_client import Client  # type: ignore
    except ImportError:
        raise ProviderSkipped("gradio_client not installed (pip install gradio_client)")
    space = job.get("hf_space") or HF_MUSIC_SPACE
    # gradio_client renamed/dropped the token kwarg across versions; pass it only when
    # we actually have one, and fall back to a tokenless client on any signature error.
    try:
        client = Client(space, hf_token=HF_TOKEN) if HF_TOKEN else Client(space)
    except TypeError:
        client = Client(space)
    except Exception as e:
        raise ProviderFailed(f"cannot reach HF Space '{space}': {e}")
    prompt, duration = job["prompt"], float(job.get("duration", 15))
    kind = job.get("kind", "music")
    variant = job.get("variant") or ("small-sfx" if kind == "sfx" else "small-music")

    def _land(res) -> dict:
        src = res[0] if isinstance(res, (list, tuple)) else res
        if isinstance(src, dict):
            src = src.get("value") or src.get("path") or src.get("name")
        out = _out_path(job["out"], kind, prompt, "wav")
        _copy_or_download(src, out)
        return {"path": str(out)}

    # Stable Audio 3's /infer is the primary target (the default space). Space APIs drift
    # weekly, so we keep generic named + positional fallbacks; /scout re-points the space.
    attempts = [
        dict(variant_key=variant, prompt=prompt, duration=duration, steps=8,
             cfg_scale=1.0, sampler_type="pingpong", seed=0, api_name="/infer"),
        dict(text=prompt, duration=int(duration), api_name="/predict"),
        dict(prompt=prompt, duration=int(duration), api_name="/predict"),
    ]
    last = None
    for kwargs in attempts:
        try:
            return _land(client.predict(**kwargs))
        except Exception as e:
            last = e
    raise ProviderFailed(f"HF Space '{space}' API not matched: {last} "
                         f"(set AUDIO_HF_MUSIC_SPACE to a known-good space; run /scout)")


def music_elevenlabs(job: dict) -> dict:
    """ElevenLabs compose_music - studio-grade, commercially cleared, 10k free credits/mo.

    The Music API lives in the elevenlabs 2.x SDK (client.music.compose). We pin to 1.x
    (2.x trips Windows Long Path limits here), so fall back to the REST endpoint, which
    is SDK-version-independent.
    """
    if not ELEVEN_KEY:
        raise ProviderSkipped("ELEVENLABS_API_KEY not set")
    prompt = job["prompt"]
    length_ms = max(3000, int(job.get("duration", 30)) * 1000)

    # Preferred path: SDK (2.x). Use it only if this SDK actually exposes music.
    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
        client = ElevenLabs(api_key=ELEVEN_KEY)
        if hasattr(client, "music"):
            audio = client.music.compose(prompt=prompt, music_length_ms=length_ms)
            out = _out_path(job["out"], "music", prompt, "mp3")
            _write_stream(audio, out)
            return {"path": str(out)}
    except Exception as e:
        # SDK present but failed - fall through to REST rather than dropping the rung.
        log(f"   (ElevenLabs SDK music path unavailable: {e}; trying REST)")

    # REST path: POST /v1/music returns the composed audio as binary.
    try:
        import requests  # type: ignore
    except ImportError:
        raise ProviderSkipped("requests not installed (pip install requests)")
    try:
        resp = requests.post(
            "https://api.elevenlabs.io/v1/music",
            headers={"xi-api-key": ELEVEN_KEY, "Accept": "audio/mpeg"},
            json={"prompt": prompt, "music_length_ms": length_ms, "model_id": "music_v1"},
            timeout=180,
        )
        if resp.status_code != 200:
            raise ProviderFailed(f"REST /v1/music -> HTTP {resp.status_code}: {resp.text[:200]}")
        out = _out_path(job["out"], "music", prompt, "mp3")
        out.write_bytes(resp.content)
        if out.stat().st_size == 0:
            raise ProviderFailed("REST /v1/music returned empty audio")
        return {"path": str(out)}
    except ProviderFailed:
        raise
    except Exception as e:
        raise ProviderFailed(f"ElevenLabs music REST failed: {e}")


def music_lyria(job: dict) -> dict:
    """Google Lyria via Gemini API. Experimental + may bill - off unless AUDIO_ENABLE_LYRIA=1."""
    if not ENABLE_LYRIA:
        raise ProviderSkipped("Lyria disabled (set AUDIO_ENABLE_LYRIA=1; may incur cost)")
    if not GOOGLE_KEY:
        raise ProviderSkipped("GEMINI_API_KEY / GOOGLE_API_KEY not set")
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
    except ImportError:
        raise ProviderSkipped("google-genai not installed (pip install google-genai)")
    prompt = job["prompt"]
    try:
        client = genai.Client(api_key=GOOGLE_KEY)
        resp = client.models.generate_music(  # API surface may vary by SDK version
            model=os.environ.get("AUDIO_LYRIA_MODEL", "lyria-3-clip-preview"),
            prompt=prompt,
            config=types.GenerateMusicConfig() if hasattr(types, "GenerateMusicConfig") else None,
        )
        data = getattr(resp, "audio", None) or getattr(resp, "data", None)
        if not data:
            raise ProviderFailed("Lyria returned no audio (check SDK version / model id)")
        out = _out_path(job["out"], "music", prompt, "wav")
        out.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
        return {"path": str(out)}
    except ProviderFailed:
        raise
    except Exception as e:
        raise ProviderFailed(f"Lyria call failed: {e}")


# --------------------------------------------------------------------------- providers: SFX

def sfx_elevenlabs(job: dict) -> dict:
    """ElevenLabs sound_effect - the gold standard; ~tiny credits per clip."""
    if not ELEVEN_KEY:
        raise ProviderSkipped("ELEVENLABS_API_KEY not set")
    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
    except ImportError:
        raise ProviderSkipped("elevenlabs SDK not installed (pip install elevenlabs)")
    prompt = job["prompt"]
    dur = job.get("duration")
    try:
        client = ElevenLabs(api_key=ELEVEN_KEY)
        kwargs = {"text": prompt}
        if dur:
            kwargs["duration_seconds"] = float(dur)
        audio = client.text_to_sound_effects.convert(**kwargs)
        out = _out_path(job["out"], "sfx", prompt, "mp3")
        _write_stream(audio, out)
        return {"path": str(out)}
    except Exception as e:
        raise ProviderFailed(f"ElevenLabs sound_effect failed: {e}")


def sfx_hf(job: dict) -> dict:
    """Free fallback: the Stable Audio 3 Space (small-sfx variant) for sound effects."""
    job = {**job, "kind": "sfx", "hf_space": job.get("hf_space") or HF_SFX_SPACE}
    return music_hf(job)          # same Space-calling machinery, sfx variant


# --------------------------------------------------------------------------- providers: TTS

def tts_edge(job: dict) -> dict:
    """Free + unlimited: Microsoft Edge Neural TTS. Native Azerbaijani voices."""
    try:
        import asyncio
        import edge_tts  # type: ignore
    except ImportError:
        raise ProviderSkipped("edge-tts not installed (pip install edge-tts)")
    text = job["prompt"]
    lang = job.get("lang", "az")
    voice = job.get("voice") or EDGE_VOICES.get(lang) or EDGE_VOICES["en"]
    out = _out_path(job["out"], "tts", text, "mp3")
    try:
        async def _go():
            await edge_tts.Communicate(text, voice).save(str(out))
        asyncio.run(_go())
        return {"path": str(out), "voice": voice}
    except Exception as e:
        raise ProviderFailed(f"edge-tts failed for voice '{voice}': {e}")


def tts_elevenlabs(job: dict) -> dict:
    """Premium multilingual TTS / voice cloning (free tier covers 10k credits/mo)."""
    if not ELEVEN_KEY:
        raise ProviderSkipped("ELEVENLABS_API_KEY not set")
    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
    except ImportError:
        raise ProviderSkipped("elevenlabs SDK not installed (pip install elevenlabs)")
    text = job["prompt"]
    voice = job.get("voice") or ELEVEN_DEFAULT_VOICE
    try:
        client = ElevenLabs(api_key=ELEVEN_KEY)
        audio = client.text_to_speech.convert(
            voice_id=voice, text=text, model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        out = _out_path(job["out"], "tts", text, "mp3")
        _write_stream(audio, out)
        return {"path": str(out), "voice": voice}
    except Exception as e:
        raise ProviderFailed(f"ElevenLabs TTS failed: {e}")


def _pcm_to_wav(data, mime: str, out: Path) -> None:
    """Wrap Gemini's raw PCM in a RIFF/wav header. Gemini returns headerless PCM (the mime
    varies: 'audio/L16;rate=24000', 'audio/pcm;rate=24000', etc.), so we wrap by default and
    only pass bytes through when the mime clearly names a real container."""
    import wave
    data = data if isinstance(data, (bytes, bytearray)) else bytes(data)
    rate = 24000
    m = re.search(r"rate=(\d+)", mime or "")
    if m:
        rate = int(m.group(1))
    mime_l = (mime or "").lower()
    is_container = any(c in mime_l for c in ("wav", "ogg", "opus", "mpeg", "mp3", "flac", "m4a", "aac"))
    if is_container:
        out.write_bytes(data)
    else:
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)   # 16-bit
            w.setframerate(rate)
            w.writeframes(data)


def tts_gemini(job: dict) -> dict:
    """Gemini native-audio TTS — the natural family from the reel (gemini-3.1-flash-tts).
    70+ languages incl. Azerbaijani, 30+ prebuilt voices. Far more natural than the old 2.5
    preview. ⚠️ free-tier audio output is NOT licensed for commercial use (paid billing for
    production renders). `--voice` picks a Gemini voice (e.g. Kore, Charon, Aoede)."""
    if not GOOGLE_KEY:
        raise ProviderSkipped("GEMINI_API_KEY / GOOGLE_API_KEY not set")
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
    except ImportError:
        raise ProviderSkipped("google-genai not installed (pip install google-genai)")
    text = job["prompt"]
    # Voice brief: a delivery instruction (from --style/--purpose/--brief) steers intonation
    # for the SAME text. A purpose preset can also recommend a voice.
    steer, preset_voice = _voice_steer(job)
    # --voice may carry an Edge id (az-AZ-..) or ElevenLabs id from another rung; only accept
    # a real Gemini prebuilt voice. Explicit --voice wins; else preset voice; else default.
    voice = job.get("voice") or ""
    if not voice or "-" in voice or len(voice) > 20:
        voice = preset_voice or GEMINI_DEFAULT_VOICE
    if steer:
        log(f"   voice brief -> {steer}")
    contents = f"{steer}: {text}" if steer else text
    client = genai.Client(api_key=GOOGLE_KEY)
    cfg = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
    )
    last = None
    for model in (GEMINI_TTS_MODEL, GEMINI_TTS_FALLBACK):
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=cfg)
            part = resp.candidates[0].content.parts[0]
            raw = _out_path(job["out"], "tts_raw", text, "wav")
            _pcm_to_wav(part.inline_data.data, getattr(part.inline_data, "mime_type", ""), raw)
            if raw.stat().st_size == 0:
                raise ProviderFailed("Gemini returned empty audio")
            out = _out_path(job["out"], "tts", text, "wav")
            if job.get("no_post"):
                import shutil
                shutil.copyfile(raw, out)
            else:
                _postprocess_voice(raw, out)   # trim edge silence + normalize loudness
            log("   note: Gemini free-tier audio is not licensed for commercial use")
            return {"path": str(out), "voice": voice, "model": model, "style": steer}
        except Exception as e:
            last = e
            log(f"   gemini tts '{model}' failed: {e}; trying fallback")
    raise ProviderFailed(f"Gemini TTS failed: {last}")


# --------------------------------------------------------------------------- providers: VOICE CLONE

def voice_clone_omnivoice(job: dict) -> dict:
    """Clone a real human voice from a reference clip and speak new text in it (free HF).

    This is the path to *natural* Azerbaijani: the timbre comes from a real human sample,
    not a synthetic engine. Needs a 20-30s clean reference recording (job['ref']) and,
    ideally, its transcript (job['ref_text']) for best fidelity.
    """
    try:
        from gradio_client import Client, handle_file  # type: ignore
    except ImportError:
        raise ProviderSkipped("gradio_client not installed (pip install gradio_client)")

    ref = job.get("ref")
    if not ref:
        raise ProviderSkipped("no reference audio (pass --ref <20-30s human voice clip>)")
    ref_path = Path(ref)
    if not ref_path.is_file():
        raise ProviderFailed(f"reference audio not found: {ref}")
    if ref_path.stat().st_size == 0:
        raise ProviderFailed(f"reference audio is empty (0 bytes): {ref}")

    # ref_text MUST match ref_aud or the clone garbles the words (verified). If the caller
    # didn't supply it, auto-transcribe the reference (free, Gemini) and cache it next to
    # the original so the transcript always matches the audio.
    ref_text = job.get("ref_text", "") or ""
    if not ref_text:
        ref_text = _auto_ref_text(ref_path, job.get("lang", "az"))

    # The Space wants a clean wav; real samples arrive as m4a/mp3/ogg. Normalize to
    # 24 kHz mono wav so an unusual container/codec never trips a server-side error.
    ref_path = _normalize_audio(ref_path, job["out"])

    text = job["prompt"]
    lang = CLONE_LANG_NAMES.get(job.get("lang", "az"), "Azerbaijani")
    space = job.get("hf_space") or HF_CLONE_SPACE
    instruct = job.get("instruct", "") or ""
    ns = float(job.get("ns", 48))
    gs = float(job.get("gs", 2.0))
    speed = float(job.get("speed", 1.0))

    def _du_for(t: str) -> float:
        """Target length ~ the natural spoken duration. Too short drops/repeats words;
        too long lets the model add trailing filler (the 'AD' artifact)."""
        if job.get("du"):
            return float(job["du"])
        words = max(1, len(t.split()))
        return max(3.5, round(words * 0.75 + 1.5, 1))

    try:
        client = Client(space, hf_token=HF_TOKEN) if HF_TOKEN else Client(space)
    except TypeError:
        client = Client(space)
    except Exception as e:
        raise ProviderFailed(f"cannot reach clone Space '{space}': {e}")

    def _gen(piece: str) -> Path:
        """Synthesize one chunk, land it, and return the raw wav path."""
        res = client.predict(
            text=piece, lang=lang, ref_aud=handle_file(str(ref_path)), ref_text=ref_text,
            instruct=instruct, ns=ns, gs=gs, dn=bool(job.get("dn", True)),
            sp=speed, du=_du_for(piece), pp=True, po=True, api_name="/_clone_fn",
        )
        src = res[0] if isinstance(res, (list, tuple)) else res
        if isinstance(src, dict):
            src = src.get("value") or src.get("path") or src.get("name")
        if not src:
            status = res[1] if isinstance(res, (list, tuple)) and len(res) > 1 else "no output"
            raise ProviderFailed(f"clone returned no audio (status: {status})")
        raw = _out_path(job["out"], "clone_raw", piece, "wav")
        _copy_or_download(src, raw)
        return raw

    try:
        # Per-sentence pacing: each sentence gets its own natural duration, then we stitch.
        # This fixes the cram/rush of one du over a long paragraph (better intonation).
        if job.get("by_sentence"):
            pieces = _split_sentences(text)
            log(f"   by-sentence: {len(pieces)} sentence(s)")
            parts = [_gen(p) for p in pieces if p.strip()]
            raw = _concat_wavs(parts, job["out"]) if len(parts) > 1 else parts[0]
        else:
            raw = _gen(text)

        # Post-process: trim leading/trailing silence + spurious tail, normalize loudness.
        out = _out_path(job["out"], "clone", text, "wav")
        if job.get("no_post"):
            import shutil
            shutil.copyfile(raw, out)
        else:
            _postprocess_voice(raw, out)
        return {"path": str(out), "ref": str(ref_path)}
    except ProviderFailed:
        raise
    except Exception as e:
        raise ProviderFailed(f"OmniVoice clone failed: {e}")


# --------------------------------------------------------------------------- io helpers

def _ffmpeg_exe() -> str | None:
    """Locate ffmpeg: the bundled portable build first, then PATH."""
    bundled = ROOT / "video-studio" / "tools" / "ffmpeg-8.1.1-essentials_build" / "bin" / "ffmpeg.exe"
    if bundled.is_file():
        return str(bundled)
    import shutil
    return shutil.which("ffmpeg")


def _auto_ref_text(ref_path: Path, lang: str = "az") -> str:
    """Transcribe a reference clip (free, Gemini) so ref_text matches ref_aud. Cached to a
    sibling .txt. Returns "" if no key / fails (the clone still runs, just less faithfully)."""
    cache = ref_path.with_suffix(".txt")
    if cache.is_file():
        t = cache.read_text(encoding="utf-8").strip()
        if t:
            return t
    if not GOOGLE_KEY:
        log("   no GEMINI key to auto-transcribe ref; pass --ref-text for best fidelity")
        return ""
    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=GOOGLE_KEY)
        f = client.files.upload(file=str(ref_path))
        lname = CLONE_LANG_NAMES.get(lang, "Azerbaijani")
        r = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[f"Transcribe this audio verbatim. Output ONLY the spoken text, in {lname}.", f],
        )
        text = (r.text or "").strip()
        if text:
            cache.write_text(text, encoding="utf-8")
            log(f"   auto-transcribed reference ({len(text.split())} words) for ref_text")
        return text
    except Exception as e:
        log(f"   ref auto-transcribe failed ({e}); proceeding without ref_text")
        return ""


def _split_sentences(text: str) -> list[str]:
    """Split into sentences on . ! ? : ; … keeping the delimiter. Falls back to the whole
    text if there is nothing to split."""
    parts = re.split(r"(?<=[.!?…:;])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()] or [text.strip()]


def _postprocess_voice(raw: Path, out: Path) -> None:
    """Polish a generated voice clip: trim leading/trailing silence (kills stray tail
    artifacts like a trailing blip) and normalize loudness. Falls back to a copy if
    ffmpeg is unavailable - never drop the result."""
    ff = _ffmpeg_exe()
    if not ff:
        import shutil
        shutil.copyfile(raw, out)
        return
    af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
          "areverse,"
          "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
          "areverse,"
          "loudnorm=I=-16:TP=-1.5:LRA=11")
    try:
        import subprocess
        r = subprocess.run([ff, "-y", "-i", str(raw), "-af", af,
                            "-ar", "24000", "-ac", "1", str(out)],
                           capture_output=True, timeout=120)
        if r.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            return
    except Exception:
        pass
    import shutil
    shutil.copyfile(raw, out)


def _concat_wavs(parts: list[Path], out_dir: Path) -> Path:
    """Concatenate per-sentence wavs into one (resampled to a common 24k mono)."""
    ff = _ffmpeg_exe()
    dst = _out_path(out_dir, "clone_joined", "parts", "wav")
    if not ff or len(parts) == 1:
        import shutil
        shutil.copyfile(parts[0], dst)
        return dst
    inputs: list[str] = []
    filt = ""
    for i, p in enumerate(parts):
        inputs += ["-i", str(p)]
        filt += f"[{i}:a]aresample=24000,aformat=channel_layouts=mono[a{i}];"
    filt += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]"
    try:
        import subprocess
        r = subprocess.run([ff, "-y", *inputs, "-filter_complex", filt, "-map", "[out]", str(dst)],
                           capture_output=True, timeout=180)
        if r.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
            return dst
    except Exception:
        pass
    import shutil
    shutil.copyfile(parts[0], dst)
    return dst


def _normalize_audio(src: Path, out_dir: Path, rate: int = 24000) -> Path:
    """Re-encode a reference clip to 24 kHz mono wav. Returns src unchanged if ffmpeg
    is missing or the convert fails (better to try the raw file than to drop the rung)."""
    ff = _ffmpeg_exe()
    if not ff:
        return src
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"_ref_{_slug(src.stem)}.wav"
    try:
        import subprocess
        r = subprocess.run(
            [ff, "-y", "-i", str(src), "-ar", str(rate), "-ac", "1", str(dst)],
            capture_output=True, timeout=120,
        )
        if r.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
            return dst
    except Exception:
        pass
    return src


def _write_stream(audio, out: Path) -> None:
    """Write an ElevenLabs response (bytes, or an iterator of byte chunks) to disk."""
    with open(out, "wb") as f:
        if isinstance(audio, (bytes, bytearray)):
            f.write(audio)
        else:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
    if out.stat().st_size == 0:
        raise ProviderFailed("provider returned an empty audio stream")


def _copy_or_download(src, out: Path) -> None:
    """src is a local path (gradio download) or a URL; land it at out."""
    src = str(src)
    if src.startswith("http"):
        import urllib.request
        urllib.request.urlretrieve(src, out)
    else:
        import shutil
        shutil.copyfile(src, out)
    if not out.is_file() or out.stat().st_size == 0:
        raise ProviderFailed("downloaded file is empty")


# --------------------------------------------------------------------------- auto-judge (best-of-N)
# The "reinforcement" the agent can actually run on this locked box (no torch): generate N
# takes, transcribe each back with Gemini ASR, score CER vs the target text, keep the best.
# CER (intelligibility) is language-grounded for Azerbaijani; naturalness stays a human-ear
# call (we never claim it). Speaker-similarity / MOS are Phase-2 once we can run those models.

def _norm_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _cer(ref: str, hyp: str) -> float:
    """Character error rate (Levenshtein / len), spaces removed. 0 = perfect, 1 = no match."""
    a, b = _norm_text(ref).replace(" ", ""), _norm_text(hyp).replace(" ", "")
    if not a:
        return 1.0
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, cb in enumerate(b, 1):
            prev, dp[j] = dp[j], min(dp[j] + 1, dp[j - 1] + 1, prev + (ca != cb))
    return dp[len(b)] / len(a)


def _asr_text(path: str, lang: str = "az") -> str | None:
    """Transcribe a generated clip with Gemini ASR (no torch needed). Used by the judge."""
    if not GOOGLE_KEY:
        return None
    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=GOOGLE_KEY)
        f = client.files.upload(file=str(path))
        lname = CLONE_LANG_NAMES.get(lang, "Azerbaijani")
        r = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[f"Transcribe this audio verbatim. Output ONLY the spoken {lname} text.", f],
        )
        return (r.text or "").strip()
    except Exception as e:
        log(f"   judge ASR failed: {e}")
        return None


def generate_best_of(capability: str, providers: list, job: dict, n: int) -> dict:
    """Generate n takes, auto-judge by ASR-CER vs the target text, return the best one."""
    cands: list[dict] = []
    for i in range(max(1, n)):
        r = run_cascade(capability, providers, job)
        if not r.get("path"):
            continue
        heard = _asr_text(r["path"], job.get("lang", "az"))
        r["heard"] = heard
        r["cer"] = round(_cer(job["prompt"], heard), 3) if heard else 1.0
        cands.append(r)
        log(f"   take {i + 1}/{n}: CER={r['cer']}  ::  {heard}")
    if not cands:
        return run_cascade(capability, providers, job)
    best = min(cands, key=lambda r: r.get("cer", 1.0))
    log(f"==> best-of-{n}: picked take with CER={best.get('cer')} (lower = clearer)")
    return best


# --------------------------------------------------------------------------- cascades / CLI

def cascade_for(capability: str, quality: bool, force: str | None) -> list:
    table = {
        "music": [("hf", music_hf), ("elevenlabs", music_elevenlabs), ("lyria", music_lyria)],
        "sfx":   [("elevenlabs", sfx_elevenlabs), ("hf", sfx_hf)],
        "tts":   [("edge", tts_edge), ("gemini", tts_gemini), ("elevenlabs", tts_elevenlabs)],
        "clone": [("omnivoice", voice_clone_omnivoice)],
    }[capability]
    if force:
        picked = [p for p in table if p[0] == force]
        if not picked:
            sys.exit(f"unknown provider '{force}' for {capability}; "
                     f"choose from {[p[0] for p in table]}")
        return picked
    if quality:
        # Best-first: float ElevenLabs (the studio engine) to the front.
        table = sorted(table, key=lambda p: 0 if p[0] == "elevenlabs" else 1)
    return table


def cmd_voices(args) -> None:
    print("Edge Neural TTS (free, unlimited):")
    for k, v in EDGE_VOICES.items():
        print(f"  {k:6} -> {v}")
    print(f"\nGemini native-audio TTS ({GEMINI_TTS_MODEL}, --provider gemini --voice <name>):")
    print("  " + ", ".join(GEMINI_VOICES) + "  (30+ exist; free output not for commercial use)")
    print("\nElevenLabs (needs ELEVENLABS_API_KEY):")
    if not ELEVEN_KEY:
        print("  [key not set - add ELEVENLABS_API_KEY to .env to list your voices]")
        return
    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
        client = ElevenLabs(api_key=ELEVEN_KEY)
        for v in client.voices.get_all().voices:
            print(f"  {v.voice_id}  {v.name}")
    except Exception as e:
        print(f"  [could not list ElevenLabs voices: {e}]")


def cmd_doctor(args) -> None:
    def mark(ok: bool) -> str:
        return "READY" if ok else "----"
    has_eleven_sdk = _importable("elevenlabs")
    print("Audio Studio - provider readiness")
    print(f"  ElevenLabs key      {mark(bool(ELEVEN_KEY))}   (music + sfx + tts + voice clone)")
    print(f"  ElevenLabs SDK      {mark(has_eleven_sdk)}   pip install elevenlabs")
    print(f"  Edge TTS (free)     {mark(_importable('edge_tts'))}   pip install edge-tts")
    print(f"  HF gradio_client    {mark(_importable('gradio_client'))}   pip install gradio_client")
    print(f"  HF_TOKEN            {mark(bool(HF_TOKEN))}   (better ZeroGPU quota)")
    print(f"  Gemini key          {mark(bool(GOOGLE_KEY))}   (Lyria + Gemini TTS)")
    print(f"  google-genai        {mark(_importable('google.genai'))}   pip install google-genai")
    print(f"  Lyria enabled       {mark(ENABLE_LYRIA)}   set AUDIO_ENABLE_LYRIA=1 (may bill)")
    print(f"  Voice clone (free)  {mark(_importable('gradio_client'))}   OmniVoice Space + a human ref clip")
    print(f"\n  HF music space: {HF_MUSIC_SPACE}")
    print(f"  HF sfx space:   {HF_SFX_SPACE}")
    print(f"  HF clone space: {HF_CLONE_SPACE}  (clone needs --ref <human voice clip>)")
    print(f"  output dir:     {DEFAULT_OUT}")


def _importable(mod: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="audio_studio", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    for cap in ("music", "sfx", "tts"):
        sp = sub.add_parser(cap, help=f"generate {cap}")
        sp.add_argument("prompt", help="text prompt / description")
        sp.add_argument("--duration", type=int, default=(30 if cap == "music" else 4))
        sp.add_argument("--out", default=str(DEFAULT_OUT))
        sp.add_argument("--provider", default=None)
        sp.add_argument("--quality", action="store_true", help="best-first instead of free-first")
        sp.add_argument("--lang", default="az")
        sp.add_argument("--voice", default=None)
        if cap == "tts":
            # Voice brief (Gemini): purpose-driven delivery. Same text, different intonation.
            sp.add_argument("--purpose", default=None,
                            help="delivery preset: reklam|izah|tebrik|xeberdarliq|destek|elan|xeber")
            sp.add_argument("--style", default=None,
                            help="explicit delivery instruction (overrides --purpose)")
            sp.add_argument("--brief", default=None,
                            help="freeform purpose; an LLM crafts the delivery instruction")
            sp.add_argument("--no-post", dest="no_post", action="store_true",
                            help="skip silence-trim + loudness post-processing")
            sp.add_argument("--best-of", dest="best_of", type=int, default=1,
                            help="generate N takes, auto-judge by ASR-CER, keep the clearest")
        sp.add_argument("--json", action="store_true")

    # clone: speak text in a *cloned* human voice (the path to natural Azerbaijani).
    cl = sub.add_parser("clone", help="clone a human voice from a reference clip and speak text")
    cl.add_argument("prompt", help="text to speak in the cloned voice")
    cl.add_argument("--ref", required=True, help="reference audio: a 20-30s clean human voice clip")
    cl.add_argument("--ref-text", dest="ref_text", default="",
                    help="transcript of the reference clip (improves fidelity)")
    cl.add_argument("--lang", default="az")
    cl.add_argument("--speed", type=float, default=1.0)
    cl.add_argument("--instruct", default="", help="style hint, e.g. 'calm natural conversational'")
    cl.add_argument("--ns", type=float, default=48, help="diffusion steps (more = refined, slower)")
    cl.add_argument("--gs", type=float, default=2.0, help="guidance scale (higher = stricter)")
    cl.add_argument("--du", type=float, default=None, help="target seconds (default: from text)")
    cl.add_argument("--by-sentence", dest="by_sentence", action="store_true",
                    help="synthesize each sentence separately then stitch (better pacing)")
    cl.add_argument("--no-post", dest="no_post", action="store_true",
                    help="skip silence-trim + loudness post-processing")
    cl.add_argument("--best-of", dest="best_of", type=int, default=1,
                    help="generate N takes, auto-judge by ASR-CER, keep the clearest")
    cl.add_argument("--out", default=str(DEFAULT_OUT))
    cl.add_argument("--provider", default=None)
    cl.add_argument("--json", action="store_true")

    sub.add_parser("voices", help="list usable voices")
    sub.add_parser("doctor", help="show which providers are configured")

    args = p.parse_args(argv)

    if args.cmd == "voices":
        return cmd_voices(args) or 0
    if args.cmd == "doctor":
        return cmd_doctor(args) or 0

    job = {
        "prompt": args.prompt,
        "out": Path(args.out),
        "lang": args.lang,
        "duration": getattr(args, "duration", None),
        "voice": getattr(args, "voice", None),
        "ref": getattr(args, "ref", None),
        "ref_text": getattr(args, "ref_text", ""),
        "speed": getattr(args, "speed", 1.0),
        "instruct": getattr(args, "instruct", ""),
        "ns": getattr(args, "ns", 48),
        "gs": getattr(args, "gs", 2.0),
        "du": getattr(args, "du", None),
        "by_sentence": getattr(args, "by_sentence", False),
        "no_post": getattr(args, "no_post", False),
        "purpose": getattr(args, "purpose", None),
        "style": getattr(args, "style", None),
        "brief": getattr(args, "brief", None),
    }
    # Voice-brief steering is a Gemini feature; if a style/purpose/brief is set on `tts`
    # without an explicit provider, route to gemini so the steering actually applies.
    provider = args.provider
    if args.cmd == "tts" and not provider and any(
        (job.get("purpose"), job.get("style"), job.get("brief"))
    ):
        provider = "gemini"
    providers = cascade_for(args.cmd, getattr(args, "quality", False), provider)
    n = getattr(args, "best_of", 1) or 1
    if n > 1 and args.cmd in ("tts", "clone"):
        result = generate_best_of(args.cmd, providers, job, n)
    else:
        result = run_cascade(args.cmd, providers, job)

    if args.json:
        print(json.dumps(result, default=str))
    elif result.get("path"):
        print(f"\nOK  [{result['provider']}]  {result['path']}")
    else:
        print("\nNo file produced - see the manual handoff above.")
    return 0 if result.get("path") else 2


if __name__ == "__main__":
    sys.exit(main())
