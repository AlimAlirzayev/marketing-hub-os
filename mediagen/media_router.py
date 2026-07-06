#!/usr/bin/env python3
"""
Media Router — unified multi-provider AI media generation.
ZERO BUDGET FIRST: free providers always tried before paid.

Priority stacks:
  IMAGE:  gemini(free) → together(free) → fireworks(free) → hf_api(free)
          → g4f/bing-dalle3(free) → siliconflow(free) → pollinations(zero-auth)
          → openai(paid) → fal(paid) → stability(paid)
  VIDEO:  hf_spaces(free) → kling_browser(OpenClaw) → fal(paid)
  VOICE:  edge_tts(free) → pollinations_tts(free) → openai(paid) → elevenlabs(paid)
  MUSIC:  suno_browser(OpenClaw) → udio_browser(OpenClaw) → fal(paid)

Usage:
  python3 media_router.py image "cinematic Baku skyline at sunset" --out out.jpg
  python3 media_router.py image "..." --provider gemini --out out.jpg
  python3 media_router.py image "..." --provider g4f --model bing --out out.jpg
  python3 media_router.py video "timelapse of Baku city" --out out.mp4
  python3 media_router.py voice "Salam, xoş gəldiniz" --voice az-AZ-BabekNeural --out out.mp3
  python3 media_router.py music "upbeat corporate background" --out out.mp3
  python3 media_router.py --list-providers
"""

import argparse
import asyncio
import base64
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

# ── API key helpers — always read from env at call time ───────────────────
def _google_key():   return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
def _openai_key():   return os.environ.get("OPENAI_API_KEY", "")
def _fal_key():      return os.environ.get("FAL_API_KEY", "")
def _stab_key():     return os.environ.get("STABILITY_API_KEY", "")
def _el_key():       return os.environ.get("ELEVENLABS_API_KEY", "")
def _suno_url():     return os.environ.get("SUNO_API_URL", "")
def _together_key(): return os.environ.get("TOGETHER_API_KEY", "")
def _fireworks_key():return os.environ.get("FIREWORKS_API_KEY", "")
def _hf_token():     return os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY", "")
def _sf_key():       return os.environ.get("SILICONFLOW_API_KEY", "")

# ── SSL context ────────────────────────────────────────────────────────────
_ssl = ssl.create_default_context()
try:
    import certifi
    _ssl = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _ssl.check_hostname = False
    _ssl.verify_mode = ssl.CERT_NONE

# ── HTTP helpers ───────────────────────────────────────────────────────────

def _retry(fn, retries=3):
    for attempt in range(retries):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 ** (attempt + 1))
            elif attempt == retries - 1:
                raise
            else:
                time.sleep(2 ** attempt)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def http_get(url, headers=None, timeout=90, retries=3):
    h = {**(headers or {}), "User-Agent": "MediaRouter/1.0"}
    def _do():
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl) as r:
            return r.read(), r.headers.get("Content-Type", "")
    return _retry(_do, retries)


def http_post(url, body, headers=None, timeout=120, retries=3):
    if isinstance(body, dict):
        data, ct = json.dumps(body).encode(), "application/json"
    else:
        data, ct = body, "application/octet-stream"
    h = {"Content-Type": ct, "User-Agent": "MediaRouter/1.0", **(headers or {})}
    def _do():
        req = urllib.request.Request(url, data=data, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl) as r:
            return r.read(), r.headers.get("Content-Type", "")
    return _retry(_do, retries)

# ══════════════════════════════════════════════════════════════════════════
# IMAGE PROVIDERS  (free first)
# ══════════════════════════════════════════════════════════════════════════

def image_gemini(prompt, width=1024, height=1024, model="gemini-3.1-flash-image-preview", **_):
    """Gemini image gen — free with API key.
    Models: gemini-3.1-flash-image-preview (Nano Banana 2, best free),
            gemini-2.5-flash-image, gemini-3-pro-image-preview"""
    key = _google_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    # try model, fallback to older
    for m in [model, "gemini-2.5-flash-image", "gemini-2.0-flash-preview-image-generation"]:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{m}:generateContent?key={key}")
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
        }
        try:
            data, _ = http_post(url, body, timeout=60, retries=1)
            resp = json.loads(data)
            for part in resp["candidates"][0]["content"]["parts"]:
                if "inlineData" in part:
                    return base64.b64decode(part["inlineData"]["data"]), part["inlineData"]["mimeType"]
        except Exception:
            continue
    raise RuntimeError("All Gemini image models failed")


def image_imagen(prompt, width=1024, height=1024, model="imagen-4.0-generate-001", **_):
    """Google Imagen 4 — state-of-the-art quality, free with Gemini API key.
    Models: imagen-4.0-generate-001 (best), imagen-4.0-fast-generate-001 (fast),
            imagen-4.0-ultra-generate-001 (ultra quality)"""
    key = _google_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:predict?key={key}")
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "1:1" if width == height else ("16:9" if width > height else "9:16"),
        }
    }
    data, _ = http_post(url, body, timeout=90)
    resp = json.loads(data)
    b64 = resp["predictions"][0]["bytesBase64Encoded"]
    mime = resp["predictions"][0].get("mimeType", "image/png")
    return base64.b64decode(b64), mime


def image_together(prompt, width=1024, height=1024, model="flux-schnell", **_):
    """Together.ai — free FLUX.1-schnell, fast."""
    key = _together_key()
    if not key:
        raise RuntimeError("TOGETHER_API_KEY not set")
    model_map = {
        "flux-schnell": "black-forest-labs/FLUX.1-schnell-Free",
        "flux-dev":     "black-forest-labs/FLUX.1-dev",
        "flux-pro":     "black-forest-labs/FLUX.1-pro",
        "sd35":         "stabilityai/stable-diffusion-3-5-large",
    }
    fqn = model_map.get(model, model)
    body = {
        "model": fqn,
        "prompt": prompt,
        "width": width,
        "height": height,
        "steps": 4,
        "n": 1,
        "response_format": "b64_json",
    }
    data, _ = http_post(
        "https://api.together.xyz/v1/images/generations", body,
        headers={"Authorization": f"Bearer {key}"}, timeout=90)
    b64 = json.loads(data)["data"][0]["b64_json"]
    return base64.b64decode(b64), "image/jpeg"


def image_fireworks(prompt, width=1024, height=1024, model="flux-schnell", **_):
    """Fireworks.ai — fast FLUX inference."""
    key = _fireworks_key()
    if not key:
        raise RuntimeError("FIREWORKS_API_KEY not set")
    model_map = {
        "flux-schnell": "accounts/fireworks/models/flux-1-schnell-fp8",
        "flux-dev":     "accounts/fireworks/models/flux-1-dev-fp8",
        "sd35":         "accounts/fireworks/models/stable-diffusion-3p5-large",
        "playground":   "accounts/fireworks/models/playground-v2-5-1024px-aesthetic",
    }
    body = {
        "model": model_map.get(model, f"accounts/fireworks/models/{model}"),
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": 4,
        "guidance_scale": 0,
        "output_image_format": "JPEG",
    }
    data, _ = http_post(
        "https://api.fireworks.ai/inference/v1/image_generation/accounts/fireworks/models/flux-1-schnell-fp8",
        body,
        headers={"Authorization": f"Bearer {key}"}, timeout=90)
    resp = json.loads(data)
    if "output" in resp:
        return base64.b64decode(resp["output"][0]["choices"][0]["image"]["url"].split(",", 1)[1]), "image/jpeg"
    b64 = resp.get("data", [{}])[0].get("b64_json", "")
    if b64:
        return base64.b64decode(b64), "image/jpeg"
    # Sometimes returns URL
    img_url = resp.get("data", [{}])[0].get("url", "")
    img_data, mime = http_get(img_url)
    return img_data, mime or "image/jpeg"


def image_hf_api(prompt, width=1024, height=1024, model="flux-schnell", **_):
    """HuggingFace Inference API — free FLUX.1-schnell (no CC needed)."""
    token = _hf_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    model_map = {
        "flux-schnell": "black-forest-labs/FLUX.1-schnell",
        "flux-dev":     "black-forest-labs/FLUX.1-dev",
        "sd35":         "stabilityai/stable-diffusion-3.5-large",
        "sdxl":         "stabilityai/stable-diffusion-xl-base-1.0",
    }
    hf_model = model_map.get(model, model)
    body = {"inputs": prompt, "parameters": {"width": width, "height": height}}
    data, mime = http_post(
        f"https://api-inference.huggingface.co/models/{hf_model}",
        body, headers=headers, timeout=120)
    return data, mime or "image/jpeg"


def image_siliconflow(prompt, width=1024, height=1024, model="flux-schnell", **_):
    """SiliconFlow — Chinese platform, 1000 RPM free, FLUX/SD3/Kolors."""
    key = _sf_key()
    if not key:
        raise RuntimeError("SILICONFLOW_API_KEY not set — free signup at siliconflow.cn")
    model_map = {
        "flux-schnell": "black-forest-labs/FLUX.1-schnell",
        "flux-dev":     "black-forest-labs/FLUX.1-dev",
        "sd35":         "stabilityai/stable-diffusion-3-5-large",
        "kolors":       "Kwai-Kolors/Kolors",
        "janus":        "deepseek-ai/Janus-Pro-7B",
        "flux-pro":     "Pro/black-forest-labs/FLUX.1-pro",
    }
    body = {
        "model": model_map.get(model, model),
        "prompt": prompt,
        "image_size": f"{width}x{height}",
        "num_inference_steps": 20,
        "guidance_scale": 7.5,
    }
    data, _ = http_post(
        "https://api.siliconflow.cn/v1/image/generations", body,
        headers={"Authorization": f"Bearer {key}"}, timeout=90)
    resp = json.loads(data)
    img_url = resp["images"][0]["url"]
    img_data, mime = http_get(img_url)
    return img_data, mime or "image/jpeg"


def image_g4f(prompt, width=1024, height=1024, model="flux-dev", **_):
    """g4f — reverse-engineered free: FLUX.1-dev, SD3.5, Azure Flux 1.1 Pro (no auth needed).
    Models: flux-dev, flux-schnell, flux-pro(Azure), sd35, janus"""
    import g4f
    from g4f.client import Client as G4FClient
    model_map = {
        "flux-dev":    ("BlackForestLabs_Flux1Dev", "flux"),
        "flux-schnell":("HuggingFaceInference",     "black-forest-labs/FLUX.1-schnell"),
        "flux-pro":    ("Azure",                     "flux-1.1-pro"),
        "sd35":        ("StabilityAI_SD35Large",     "sd-3.5-large"),
        "janus":       ("DeepseekAI_JanusPro7b",     "janus-pro-7b-image"),
    }
    prov_name, mdl = model_map.get(model, model_map["flux-dev"])
    prov = getattr(g4f.Provider, prov_name)
    resp = G4FClient().images.generate(model=mdl, prompt=prompt, provider=prov, response_format="url")
    img_url = resp.data[0].url
    if img_url.startswith("data:"):
        header, b64 = img_url.split(",", 1)
        return base64.b64decode(b64), header.split(";")[0].split(":")[1]
    img_data, mime = http_get(img_url, timeout=90)
    return img_data, mime or "image/jpeg"


def image_pollinations(prompt, width=1024, height=1024, model="flux", **_):
    """Pollinations — zero-auth FLUX, always available."""
    encoded = urllib.parse.quote(prompt, safe="")
    url = (f"https://image.pollinations.ai/prompt/{encoded}"
           f"?width={width}&height={height}&model={model}&nologo=true&enhance=true")
    data, mime = http_get(url, timeout=90)
    return data, mime or "image/jpeg"


def image_openai(prompt, width=1024, height=1024, quality="high", **_):
    """OpenAI gpt-image-1 — paid, highest quality."""
    key = _openai_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    size = "1536x1024" if width > height else ("1024x1536" if height > width else "1024x1024")
    body = {"model": "gpt-image-1", "prompt": prompt, "n": 1,
            "size": size, "quality": quality, "output_format": "jpeg"}
    data, _ = http_post(
        "https://api.openai.com/v1/images/generations", body,
        headers={"Authorization": f"Bearer {key}"}, timeout=120)
    return base64.b64decode(json.loads(data)["data"][0]["b64_json"]), "image/jpeg"


def image_fal(prompt, width=1024, height=1024, model="flux-pro", **_):
    """fal.ai — paid, premium models (Imagen4, Ideogram, Recraft)."""
    key = _fal_key()
    if not key:
        raise RuntimeError("FAL_API_KEY not set")
    model_map = {
        "flux-pro":     "fal-ai/flux-pro",
        "flux-dev":     "fal-ai/flux/dev",
        "flux-schnell": "fal-ai/flux/schnell",
        "sd35":         "fal-ai/stable-diffusion-v35-large",
        "ideogram":     "fal-ai/ideogram/v2",
        "imagen4":      "fal-ai/imagen4/preview",
        "sana":         "fal-ai/sana",
        "recraft":      "fal-ai/recraft-v3",
    }
    fal_model = model_map.get(model, f"fal-ai/{model}")
    data, _ = http_post(
        f"https://fal.run/{fal_model}",
        {"prompt": prompt, "image_size": {"width": width, "height": height}},
        headers={"Authorization": f"Key {key}"}, timeout=120)
    img_url = json.loads(data)["images"][0]["url"]
    img_data, mime = http_get(img_url)
    return img_data, mime or "image/jpeg"


def image_stability(prompt, width=1024, height=1024, model="ultra", **_):
    """Stability AI — paid, Ultra/Core/SD3.5."""
    key = _stab_key()
    if not key:
        raise RuntimeError("STABILITY_API_KEY not set")
    endpoint_map = {
        "ultra": "https://api.stability.ai/v2beta/stable-image/generate/ultra",
        "core":  "https://api.stability.ai/v2beta/stable-image/generate/core",
        "sd35":  "https://api.stability.ai/v2beta/stable-image/generate/sd3",
    }
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    raw = (f'--{boundary}\r\nContent-Disposition: form-data; name="prompt"\r\n\r\n{prompt}\r\n'
           f'--{boundary}\r\nContent-Disposition: form-data; name="output_format"\r\n\r\njpeg\r\n'
           f'--{boundary}--\r\n').encode()
    data, _ = http_post(endpoint_map.get(model, endpoint_map["ultra"]), raw, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "image/*",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }, timeout=90)
    return data, "image/jpeg"


IMAGE_PROVIDERS = [
    # FREE tier first
    ("gemini",       image_gemini,       _google_key),
    ("imagen",       image_imagen,       _google_key),   # Imagen 4 — best free quality
    ("together",     image_together,     _together_key),
    ("fireworks",    image_fireworks,    _fireworks_key),
    ("hf_api",       image_hf_api,       lambda: True),   # works without token too (rate limited)
    ("siliconflow",  image_siliconflow,  _sf_key),
    ("g4f",          image_g4f,          lambda: True),   # always available
    ("pollinations", image_pollinations, lambda: True),   # zero-auth fallback
    # PAID tier
    ("openai",       image_openai,       _openai_key),
    ("fal",          image_fal,          _fal_key),
    ("stability",    image_stability,    _stab_key),
]

# ══════════════════════════════════════════════════════════════════════════
# VIDEO PROVIDERS  (free first)
# ══════════════════════════════════════════════════════════════════════════

def video_hf(prompt, model="wan21", **_):
    """HuggingFace Spaces — free GPU, Wan2.1/LTX-Video/CogVideoX."""
    from gradio_client import Client
    space_map = {
        "wan21":    "Wan-AI/Wan2.1-T2V-A14B",
        "ltx":      "Lightricks/LTX-Video",
        "cogvideo": "THUDM/CogVideoX-5B-Space",
    }
    client = Client(space_map.get(model, space_map["wan21"]))
    result = client.predict(prompt=prompt, api_name="/generate")
    path = result if isinstance(result, str) else (result.get("video") or result[0])
    return Path(path).read_bytes(), "video/mp4"


def video_fal(prompt, model="kling", duration=5, image_url=None, **_):
    """fal.ai — paid: Kling 1.6, Veo2, Sora, Seedance, Minimax."""
    key = _fal_key()
    if not key:
        raise RuntimeError("FAL_API_KEY not set")
    model_map = {
        "kling":     "fal-ai/kling-video/v1.6/standard/text-to-video",
        "kling-pro": "fal-ai/kling-video/v1.6/pro/text-to-video",
        "veo2":      "fal-ai/veo2",
        "sora":      "fal-ai/sora",
        "wan21":     "fal-ai/wan-t2v",
        "ltx":       "fal-ai/ltx-video",
        "cogvideo":  "fal-ai/cogvideox-5b",
        "hunyuan":   "fal-ai/hunyuan-video",
        "seedance":  "fal-ai/seedance-v1",
        "minimax":   "fal-ai/minimax-video",
    }
    body = {"prompt": prompt, "duration": duration}
    if image_url:
        body["image_url"] = image_url
    data, _ = http_post(
        f"https://fal.run/{model_map.get(model, f'fal-ai/{model}')}", body,
        headers={"Authorization": f"Key {key}"}, timeout=300)
    resp = json.loads(data)
    vid_url = resp.get("video", {}).get("url") or resp.get("url") or resp["videos"][0]["url"]
    vid_data, _ = http_get(vid_url, timeout=120)
    return vid_data, "video/mp4"


VIDEO_PROVIDERS = [
    ("hf",  video_hf,  lambda: True),
    ("fal", video_fal, _fal_key),
]

# ══════════════════════════════════════════════════════════════════════════
# VOICE PROVIDERS  (free first)
# ══════════════════════════════════════════════════════════════════════════

def voice_edge_tts(text, voice="az-AZ-BabekNeural", **_):
    """Microsoft Edge TTS — completely free, 400+ voices, no API key."""
    # Azerbaijani voices: az-AZ-BabekNeural (male), az-AZ-BanuNeural (female)
    # Turkish: tr-TR-AhmetNeural, tr-TR-EmelNeural
    # English: en-US-JennyNeural, en-GB-SoniaNeural
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp = f.name
    try:
        asyncio.run(_edge_tts_generate(text, voice, tmp))
        return Path(tmp).read_bytes(), "audio/mpeg"
    finally:
        Path(tmp).unlink(missing_ok=True)


async def _edge_tts_generate(text, voice, path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


def voice_pollinations(text, voice="alloy", **_):
    """Pollinations TTS — free, zero-auth."""
    encoded = urllib.parse.quote(text, safe="")
    data, mime = http_get(
        f"https://text.pollinations.ai/{encoded}?model=openai-audio&voice={voice}",
        timeout=60)
    return data, mime or "audio/mpeg"


def voice_openai(text, voice="shimmer", model="tts-1-hd", **_):
    """OpenAI TTS — paid, best quality (tts-1-hd / gpt-4o-mini-tts)."""
    key = _openai_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    body = {"model": model, "input": text, "voice": voice, "response_format": "mp3"}
    data, _ = http_post(
        "https://api.openai.com/v1/audio/speech", body,
        headers={"Authorization": f"Bearer {key}"}, timeout=60)
    return data, "audio/mpeg"


def voice_elevenlabs(text, voice="JBFqnCBsd6RMkjVDRTgX", model="eleven_turbo_v2_5", **_):
    """ElevenLabs — paid, best voice quality & cloning."""
    key = _el_key()
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")
    model_map = {
        "turbo":        "eleven_turbo_v2_5",
        "flash":        "eleven_flash_v2_5",
        "multilingual": "eleven_multilingual_v2",
    }
    body = {"text": text, "model_id": model_map.get(model, model),
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}
    data, _ = http_post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}", body,
        headers={"xi-api-key": key, "Accept": "audio/mpeg"}, timeout=60)
    return data, "audio/mpeg"


VOICE_PROVIDERS = [
    # FREE tier first
    ("edge_tts",     voice_edge_tts,    lambda: True),   # always free
    ("pollinations", voice_pollinations, lambda: True),  # zero-auth
    # PAID tier
    ("openai",       voice_openai,      _openai_key),
    ("elevenlabs",   voice_elevenlabs,  _el_key),
]

# ══════════════════════════════════════════════════════════════════════════
# MUSIC PROVIDERS  (free first)
# ══════════════════════════════════════════════════════════════════════════

def music_suno(prompt, duration=30, **_):
    """Suno — via self-hosted suno-api Docker (SUNO_API_URL env var)."""
    url = _suno_url() or "http://localhost:8199"
    data, _ = http_post(f"{url}/api/generate",
                        {"prompt": prompt, "make_instrumental": False, "wait_audio": True},
                        timeout=300)
    resp = json.loads(data)
    items = resp if isinstance(resp, list) else resp.get("clips", [resp])
    audio_url = items[0].get("audio_url") or items[0].get("url")
    audio_data, _ = http_get(audio_url, timeout=120)
    return audio_data, "audio/mpeg"


def music_fal(prompt, **_):
    """fal.ai stable-audio — paid."""
    key = _fal_key()
    if not key:
        raise RuntimeError("FAL_API_KEY not set")
    data, _ = http_post(
        "https://fal.run/fal-ai/stable-audio",
        {"prompt": prompt, "seconds_total": 30},
        headers={"Authorization": f"Key {key}"}, timeout=120)
    resp = json.loads(data)
    audio_url = resp.get("audio_file", {}).get("url") or resp["url"]
    audio_data, _ = http_get(audio_url)
    return audio_data, "audio/mpeg"


MUSIC_PROVIDERS = [
    ("suno", music_suno, _suno_url),
    ("fal",  music_fal,  _fal_key),
]

# ══════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════

PROVIDER_TABLE = {
    "image": IMAGE_PROVIDERS,
    "video": VIDEO_PROVIDERS,
    "voice": VOICE_PROVIDERS,
    "music": MUSIC_PROVIDERS,
}

_MODEL_PROVIDER = {
    "gemini": "gemini", "gemini-3.1": "gemini", "gemini-2.5": "gemini",
    "imagen": "imagen", "imagen4": "imagen", "imagen-4": "imagen",
    "flux-schnell": "together", "flux-free": "together",
    "fireworks": "fireworks",
    "flux": "pollinations",
    "bing": "g4f", "dalle3": "g4f",
    "kolors": "siliconflow", "janus": "siliconflow",
    "gpt-image-1": "openai", "dalle": "openai",
    "flux-pro": "fal", "flux-dev": "fal", "sd35": "fal",
    "ideogram": "fal", "kling": "fal", "kling-pro": "fal",
    "veo2": "fal", "sora": "fal", "wan21": "fal",
    "ltx": "fal", "seedance": "fal", "hunyuan": "fal", "minimax": "fal",
    "ultra": "stability", "core": "stability",
    "edge": "edge_tts", "az": "edge_tts",
    "eleven_turbo_v2_5": "elevenlabs", "multilingual": "elevenlabs",
    "tts-1-hd": "openai", "tts-1": "openai",
}


def route(task, prompt, provider=None, model=None, out_path=None, **kwargs):
    """Route to best available provider. Returns (bytes, mime_type, provider_name)."""
    providers = PROVIDER_TABLE.get(task)
    if not providers:
        raise ValueError(f"Unknown task: {task}. Use: image|video|voice|music")

    target = provider or (model and _MODEL_PROVIDER.get(model))

    for name, fn, available in providers:
        if target and name != target:
            continue
        if not available():
            if target:
                raise RuntimeError(f"Provider '{name}' unavailable — check env vars")
            continue
        try:
            print(f"[media_router] {task} → {name}" + (f"/{model}" if model else ""), file=sys.stderr)
            kw = {**kwargs, **({"model": model} if model else {})}
            data, mime = fn(prompt, **kw)
            if out_path:
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_bytes(data)
                print(f"[media_router] saved → {out_path}", file=sys.stderr)
            return data, mime, name
        except Exception as e:
            print(f"[media_router] {name} failed: {e}", file=sys.stderr)
            if target:
                raise
            continue

    raise RuntimeError(f"All providers failed for task={task}")


def list_providers():
    for task, providers in PROVIDER_TABLE.items():
        print(f"\n  {task.upper()}")
        for name, _, available in providers:
            print(f"  {'✅ FREE' if name in ('gemini','together','fireworks','hf_api','siliconflow','g4f','pollinations','hf','edge_tts') else '💰 PAID' if name in ('openai','fal','stability','elevenlabs') else '⚙️ '} {'🟢' if available() else '⚫'}  {name}")

# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Media Router — zero-budget-first AI media generation")
    parser.add_argument("task",   nargs="?", choices=["image","video","voice","music"])
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--provider", "-p",
                        help="gemini|together|fireworks|hf_api|siliconflow|g4f|pollinations|openai|fal|stability|edge_tts|elevenlabs|hf|suno")
    parser.add_argument("--model",    "-m",
                        help="e.g. flux-schnell, kling, gpt-image-1, ultra, bing, az-AZ-BabekNeural")
    parser.add_argument("--out",      "-o", default="output")
    parser.add_argument("--width",    type=int, default=1024)
    parser.add_argument("--height",   type=int, default=1024)
    parser.add_argument("--voice",    default="az-AZ-BabekNeural")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--list-providers", action="store_true")
    args = parser.parse_args()

    if args.list_providers:
        list_providers()
        return

    if not args.task or not args.prompt:
        parser.print_help()
        sys.exit(1)

    ext = {"image": "jpg", "video": "mp4", "voice": "mp3", "music": "mp3"}[args.task]
    out = args.out if "." in args.out else f"{args.out}.{ext}"

    data, mime, used = route(
        args.task, args.prompt,
        provider=args.provider, model=args.model, out_path=out,
        width=args.width, height=args.height,
        voice=args.voice, duration=args.duration,
    )
    print(f"✅ {used} → {out} ({len(data)//1024}KB)")


if __name__ == "__main__":
    main()
