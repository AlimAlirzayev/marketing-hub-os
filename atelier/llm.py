"""Thin Gemini wrapper (text + vision), reusing the free Xalq Insurance Digital OS key.

Mirrors ads-studio/analytics/ai.py: bounded retries on transient errors, and
callers are expected to catch RuntimeError / Exception and fall back to a
deterministic path so the UI never shows a raw error. Kept dependency-light so
it imports cleanly even when google-genai isn't installed yet.
"""

from __future__ import annotations

import re
import time

import os

from .config import GEMINI_API_KEY, GEMINI_MODEL

_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE",
              "500", "INTERNAL", "overloaded")

# Text generation prefers the unified router (free-first cascade + one spend log);
# vision stays on the direct Gemini path (image input). Disable with
# ATELIER_DISABLE_LLM_ROUTER=1. Falls back to direct Gemini if the router is absent.
_USE_ROUTER = os.getenv("ATELIER_DISABLE_LLM_ROUTER", "0").lower() not in {"1", "true", "yes", "on"}
_ROUTER_TIER = os.getenv("ATELIER_LLM_TIER", "smart")


def available() -> bool:
    return bool(GEMINI_API_KEY)


def _via_router(prompt: str, system: str, temperature: float) -> str | None:
    if not _USE_ROUTER:
        return None
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        import llm_router
    except Exception:  # noqa: BLE001
        return None
    try:
        text, _model = llm_router.complete(prompt, system=system or None,
                                           tier=_ROUTER_TIER, temperature=temperature)
        return text or None
    except Exception:  # noqa: BLE001
        return None


def _sleep_for(exc: Exception, attempt: int) -> None:
    m = re.search(r"retryDelay'?\s*[:=]\s*'?(\d+)", str(exc))
    time.sleep(min(float(m.group(1)) if m else 4 * (attempt + 1), 30))


def gemini_text(prompt: str, system: str = "", temperature: float = 0.7,
                max_retries: int = 3) -> str:
    routed = _via_router(prompt, system, temperature)
    if routed is not None:
        return routed
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    cfg = types.GenerateContentConfig(
        system_instruction=system or None, temperature=temperature)
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt, config=cfg)
            return (resp.text or "").strip()
        except Exception as exc:  # noqa: BLE001 - classified below
            if not any(tok in str(exc) for tok in _RETRYABLE):
                raise
            last = exc
            _sleep_for(exc, attempt)
    raise last  # type: ignore[misc]


def gemini_vision(prompt: str, image_bytes: bytes, mime_type: str,
                  system: str = "", temperature: float = 0.4,
                  max_retries: int = 3) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    cfg = types.GenerateContentConfig(
        system_instruction=system or None, temperature=temperature)
    img = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL, contents=[prompt, img], config=cfg)
            return (resp.text or "").strip()
        except Exception as exc:  # noqa: BLE001
            if not any(tok in str(exc) for tok in _RETRYABLE):
                raise
            last = exc
            _sleep_for(exc, attempt)
    raise last  # type: ignore[misc]
