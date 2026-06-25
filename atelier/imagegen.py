"""Multi-engine image generation — the unified image layer for the OS.

A small provider registry so "add every Google image model" stays orderly: the
Creative Studio just picks an engine id; this module knows how to call each one
and always returns PNG bytes (or a clean error — never raises into the UI).

Engines (all via the same GEMINI_API_KEY that already unlocks the full stack):
  • gemini-2.5-flash-image  — "Nano Banana", fast, supports edit  (cheap)
  • gemini-3-pro-image      — "Nano Banana Pro", top quality      (paid)
  • imagen-4.0 / -fast / -ultra                                    (paid / cheap-ish)
  • imagen-3.0              — legacy, kept for continuity
  • chatgpt-bridge         — manual: generate in ChatGPT UI, upload back

Cost honesty: visibility ≠ free. flash-image / imagen-4-fast are cheap; pro /
ultra are paid per image. Each call is best-effort; quota/billing errors are
returned as {"ok": False, "error": ...} so the caller can fall back to the
ChatGPT Bridge with no silent drop.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from .config import GEMINI_API_KEY

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Imagen only accepts these aspect ratios — map our format labels to the nearest.
_IMAGEN_ASPECT = {
    "4:5 Feed": "3:4", "1:1 Square": "1:1", "9:16 Story": "9:16",
    "1.91:1 Link": "16:9", "16:9 Wide": "16:9",
}


@dataclass(frozen=True)
class Engine:
    id: str
    label: str
    kind: str   # "imagen" | "gemini" | "bridge"
    model: str
    tier: str   # "cheap" | "paid" | "manual"


ENGINES: list[Engine] = [
    Engine("gemini-2.5-flash-image", "Gemini 2.5 Flash Image (Nano Banana)", "gemini", "gemini-2.5-flash-image", "cheap"),
    Engine("gemini-3-pro-image", "Gemini 3 Pro Image (Nano Banana Pro)", "gemini", "gemini-3-pro-image", "paid"),
    Engine("imagen-4", "Imagen 4", "imagen", "imagen-4.0-generate-001", "paid"),
    Engine("imagen-4-fast", "Imagen 4 Fast", "imagen", "imagen-4.0-fast-generate-001", "cheap"),
    Engine("imagen-4-ultra", "Imagen 4 Ultra", "imagen", "imagen-4.0-ultra-generate-001", "paid"),
    Engine("gemini-web", "Gemini (abunəlik · brauzer)", "web", "gemini", "sub"),
    Engine("chatgpt-web", "ChatGPT (abunəlik · brauzer)", "web", "chatgpt", "sub"),
    Engine("chatgpt-bridge", "ChatGPT Bridge (manual)", "bridge", "", "manual"),
]

_TIER_LABEL = {"cheap": "ucuz", "paid": "paid", "manual": "əl ilə", "sub": "abunəlik"}


def list_engines(include_bridge: bool = False) -> list[Engine]:
    return [e for e in ENGINES if include_bridge or e.kind != "bridge"]


def engine_label(e: Engine) -> str:
    return f"{e.label} · {_TIER_LABEL.get(e.tier, e.tier)}"


def get(engine_id: str) -> Engine | None:
    return next((e for e in ENGINES if e.id == engine_id), None)


def _client():
    from google import genai
    return genai.Client(api_key=GEMINI_API_KEY)


def _as_bytes(data) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return base64.b64decode(data)
    raise RuntimeError("unexpected image data type")


def _gen_imagen(model: str, prompt: str, fmt_label: str) -> bytes:
    from google.genai import types
    client = _client()
    aspect = _IMAGEN_ASPECT.get(fmt_label, "3:4")
    try:
        cfg = types.GenerateImagesConfig(
            number_of_images=1, aspect_ratio=aspect, output_mime_type="image/png")
    except TypeError:  # older SDK without aspect_ratio
        cfg = types.GenerateImagesConfig(number_of_images=1, output_mime_type="image/png")
    res = client.models.generate_images(model=model, prompt=prompt, config=cfg)
    imgs = getattr(res, "generated_images", None) or []
    if not imgs:
        raise RuntimeError("model returned no image (possibly blocked/safety)")
    return _as_bytes(imgs[0].image.image_bytes)


def _gen_gemini(model: str, prompt: str, fmt_label: str) -> bytes:
    client = _client()
    contents = f"{prompt}\n\n[Render as a single image. Target aspect ratio: {fmt_label}.]"
    res = client.models.generate_content(model=model, contents=contents)
    for cand in (getattr(res, "candidates", None) or []):
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                return _as_bytes(data)
    raise RuntimeError("model returned no image part (possibly text-only/safety)")


def _gen_web(site: str, prompt: str, timeout_s: int = 260) -> bytes:
    """Drive the logged-in Gemini/ChatGPT web UI via the subscription bridge,
    in a separate process so Playwright never collides with Streamlit."""
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "atelier.web_bridge", "--generate",
             "--site", site, "--prompt", prompt, "--out", tmp.name],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=timeout_s)
        if proc.returncode == 0 and os.path.getsize(tmp.name) > 0:
            with open(tmp.name, "rb") as f:
                return f.read()
        msg = ((proc.stdout or "") + (proc.stderr or "")).strip()
        raise RuntimeError(msg[-300:] or f"web bridge exit {proc.returncode}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def generate(engine_id: str, prompt: str, fmt_label: str = "4:5 Feed") -> dict:
    """Returns {"ok": True, "bytes":..., "mime":"image/png", "model":...}
    or {"ok": False, "error": str, "model": str}. Never raises."""
    e = get(engine_id)
    if not e or e.kind == "bridge":
        return {"ok": False, "error": "manual", "model": engine_id}
    try:
        if e.kind == "web":
            data = _gen_web(e.model, prompt)
        else:
            if not GEMINI_API_KEY:
                return {"ok": False, "error": "GEMINI_API_KEY yoxdur", "model": e.model}
            data = (_gen_imagen if e.kind == "imagen" else _gen_gemini)(
                e.model, prompt, fmt_label)
        return {"ok": True, "bytes": data, "mime": "image/png",
                "model": e.model, "label": e.label}
    except Exception as exc:  # noqa: BLE001 — surfaced to caller, never silent
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "model": e.model}
