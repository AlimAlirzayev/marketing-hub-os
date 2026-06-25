"""Small LLM facade for brief parsing and final recommendations."""

from __future__ import annotations

import json
import os
import re
import threading
import time

from config import GEMINI_API_KEY, GEMINI_MODELS, GROQ_API_KEY, GROQ_MODEL

os.environ.pop("GOOGLE_API_KEY", None)

_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL", "rate")
_QUOTA = ("429", "RESOURCE_EXHAUSTED", "quota")
_MIN_INTERVAL = float(os.getenv("IH_LLM_MIN_INTERVAL", "2.5"))
_lock = threading.Lock()
_last = 0.0

# Prefer the repo-wide unified router (free-first cascade + one spend log). If it
# or litellm is unavailable in this venv, we transparently fall back to the local
# Gemini/Groq path below — so behavior is identical, just better-instrumented when
# the router is present. Disable with IH_DISABLE_LLM_ROUTER=1.
_USE_ROUTER = os.getenv("IH_DISABLE_LLM_ROUTER", "0").lower() not in {"1", "true", "yes", "on"}
_ROUTER_TIER = os.getenv("IH_LLM_TIER", "cheap")


def available() -> bool:
    return bool(GEMINI_API_KEY or GROQ_API_KEY)


def _throttle() -> None:
    global _last
    with _lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()


def _sleep_for(exc: Exception, attempt: int) -> None:
    m = re.search(r"retryDelay'?\s*[:=]\s*'?(\d+)", str(exc))
    time.sleep(min(float(m.group(1)) if m else 2 * (attempt + 1), 20))


def _gemini(prompt: str, system: str, temperature: float, json_mode: bool) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    cfg = types.GenerateContentConfig(
        system_instruction=system or None,
        temperature=temperature,
        response_mime_type="application/json" if json_mode else None,
    )
    last: Exception | None = None
    for model in GEMINI_MODELS:
        for attempt in range(2):
            try:
                _throttle()
                resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
                return (resp.text or "").strip()
            except Exception as exc:  # noqa: BLE001
                last = exc
                msg = str(exc)
                if any(tok in msg for tok in _QUOTA):
                    break
                if not any(tok.lower() in msg.lower() for tok in _RETRYABLE):
                    raise
                _sleep_for(exc, attempt)
    raise last  # type: ignore[misc]


def _groq(prompt: str, system: str, temperature: float, json_mode: bool) -> str:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    kwargs = {"model": GROQ_MODEL, "messages": messages, "temperature": temperature}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    last: Exception | None = None
    for attempt in range(3):
        try:
            _throttle()
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if not any(tok in str(exc).lower() for tok in _RETRYABLE):
                raise
            _sleep_for(exc, attempt)
    raise last  # type: ignore[misc]


def _via_router(prompt: str, system: str, temperature: float, json_mode: bool) -> str | None:
    """Try the unified llm_router. Returns text, or None if it can't serve (then
    the caller falls back to the local Gemini/Groq path — never a hard failure)."""
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
        text, _model = llm_router.complete(
            prompt, system=system or None, tier=_ROUTER_TIER,
            want_json=json_mode, temperature=temperature,
        )
        return text or None
    except Exception:  # noqa: BLE001 — router exhausted/unavailable → local fallback
        return None


def complete(prompt: str, system: str = "", temperature: float = 0.2, json_mode: bool = False) -> str:
    routed = _via_router(prompt, system, temperature, json_mode)
    if routed is not None:
        return routed

    errors: list[str] = []
    if GEMINI_API_KEY:
        try:
            return _gemini(prompt, system, temperature, json_mode)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"gemini: {exc}")
    if GROQ_API_KEY:
        try:
            return _groq(prompt, system, temperature, json_mode)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"groq: {exc}")
    raise RuntimeError("no LLM provider available; " + " | ".join(errors) if errors else "no LLM provider configured")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def complete_json(prompt: str, system: str = "", temperature: float = 0.1, default=None):
    try:
        raw = complete(prompt, system=system, temperature=temperature, json_mode=True)
    except Exception:
        return default
    raw = _strip_fences(raw)
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return default
    return default
