"""AZDub TTS proxy.

Default mode uses edge-tts for free Azerbaijani voices. For a free-tier
alternative, set TTS_PROVIDER=gemini plus GEMINI_API_KEY/GOOGLE_API_KEY.
For higher quality paid voice cloning, use ElevenLabs.
"""

import io
import os
import re
import wave

import edge_tts
import httpx
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AZDub TTS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


AZURE_VOICE_RE = re.compile(r"^az-AZ-[A-Za-z]+Neural$")


def env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def rate_to_speed(rate: str) -> float:
    """Map Edge-style '+10%' rates to ElevenLabs' conservative speed range."""
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)%", rate.strip())
    if not match:
        return 1.0
    speed = 1.0 + (float(match.group(1)) / 100.0)
    return min(1.2, max(0.7, speed))


async def edge_tts_audio(text: str, voice: str, rate: str, pitch: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def wav_from_pcm(
    pcm: bytes,
    channels: int = 1,
    sample_rate: int = 24000,
    sample_width: int = 2,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


async def gemini_tts_audio(text: str, rate: str) -> bytes:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY or GOOGLE_API_KEY is not configured on the TTS proxy.",
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="google-genai is not installed. Run pip install -r requirements.txt.",
        ) from exc

    model_id = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    voice_name = os.getenv("GEMINI_TTS_VOICE", "Kore")
    language_code = os.getenv("GEMINI_TTS_LANGUAGE", "az-AZ")
    style_prompt = os.getenv(
        "GEMINI_TTS_PROMPT",
        "Read naturally in Azerbaijani. Avoid a robotic tone. Keep the pacing suitable for video dubbing.",
    )
    speed_hint = ""
    if rate.strip() != "+0%":
        speed_hint = f" Speaking rate hint: {rate}."

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=f"{style_prompt} Language: {language_code}.{speed_hint}\n\n{text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name,
                        )
                    )
                ),
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini TTS request failed: {exc}",
        ) from exc

    try:
        pcm = response.candidates[0].content.parts[0].inline_data.data
    except (AttributeError, IndexError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Gemini TTS returned no audio data.",
        ) from exc
    return wav_from_pcm(pcm)


async def elevenlabs_tts_audio(text: str, voice: str, rate: str) -> bytes:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ELEVENLABS_API_KEY is not configured on the TTS proxy.",
        )

    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not voice_id and not AZURE_VOICE_RE.fullmatch(voice):
        voice_id = voice
    if not voice_id:
        raise HTTPException(
            status_code=503,
            detail=(
                "ELEVENLABS_VOICE_ID is required when using provider=elevenlabs. "
                "Use an ElevenLabs voice ID or a cloned Azerbaijani voice."
            ),
        )

    model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")
    output_format = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    timeout_s = env_float("ELEVENLABS_TIMEOUT", 60.0)

    payload = {
        "text": text,
        "model_id": model_id,
        "language_code": os.getenv("ELEVENLABS_LANGUAGE_CODE", "az"),
        "voice_settings": {
            "stability": env_float("ELEVENLABS_STABILITY", 0.45),
            "similarity_boost": env_float("ELEVENLABS_SIMILARITY", 0.85),
            "style": env_float("ELEVENLABS_STYLE", 0.35),
            "use_speaker_boost": env_bool("ELEVENLABS_SPEAKER_BOOST", True),
            "speed": rate_to_speed(rate),
        },
    }

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    params = {"output_format": output_format}

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            res = await client.post(url, headers=headers, params=params, json=payload)
            res.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            raise HTTPException(
                status_code=502,
                detail=f"ElevenLabs TTS failed: HTTP {exc.response.status_code}: {body}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"ElevenLabs TTS request failed: {exc}",
            ) from exc

    return res.content


@app.get("/")
def root():
    provider = os.getenv("TTS_PROVIDER", "edge").strip().lower() or "edge"
    return {
        "ok": True,
        "service": "azdub-tts",
        "provider": provider,
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "elevenlabs_configured": bool(os.getenv("ELEVENLABS_API_KEY")),
    }


@app.get("/tts")
async def tts(
    text: str = Query(..., min_length=1, max_length=2000),
    voice: str = Query("az-AZ-BabekNeural"),
    rate: str = Query("+0%"),
    pitch: str = Query("+0Hz"),
    provider: str | None = Query(None),
):
    selected = (provider or os.getenv("TTS_PROVIDER", "edge")).strip().lower() or "edge"
    media_type = "audio/mpeg"

    if selected in {"gemini", "google", "google-ai", "aistudio"}:
        data = await gemini_tts_audio(text, rate)
        selected = "gemini"
        media_type = "audio/wav"
    elif selected in {"elevenlabs", "11labs", "eleven"}:
        data = await elevenlabs_tts_audio(text, voice, rate)
        selected = "elevenlabs"
    elif selected in {"edge", "edge-tts", "microsoft"}:
        data = await edge_tts_audio(text, voice, rate, pitch)
        selected = "edge"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown TTS provider: {selected}")

    if not data:
        raise HTTPException(status_code=502, detail=f"{selected} returned empty audio.")

    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-AZDUB-TTS-Provider": selected,
            "X-AZDUB-TTS-Mime": media_type,
        },
    )
