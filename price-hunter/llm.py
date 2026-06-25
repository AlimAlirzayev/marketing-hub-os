"""LLM layer for Price Hunter.

Primary: Gemini (free, big context) for page->offers extraction and the final
verdict. Fallback: Groq (free, fast). Both are optional - callers must handle
RuntimeError and degrade to the regex extractor so the agent never hard-crashes
because a key is missing or a quota is hit.

Mirrors atelier/llm.py: bounded retries on transient errors, dependency-light
imports (google-genai / groq are imported lazily).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

from config import (
    GEMINI_API_KEY,
    GEMINI_MODELS,
    GROQ_API_KEY,
    GROQ_MODEL,
)

_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE",
              "500", "INTERNAL", "overloaded", "rate limit", "rate_limit")
_QUOTA = ("429", "RESOURCE_EXHAUSTED", "quota")

# google-genai prints "Both GOOGLE_API_KEY and GEMINI_API_KEY are set..." on every
# call when both env vars exist. We pass the key explicitly, so drop the duplicate
# env var (config already captured its value) to keep output clean.
os.environ.pop("GOOGLE_API_KEY", None)

# Free Gemini/Groq tiers rate-limit bursts. A global minimum interval between
# *any* two LLM calls (even across threads) keeps us under the per-minute cap so
# extraction never silently degrades to the regex fallback. Tune via PH_LLM_MIN_INTERVAL.
_MIN_INTERVAL = float(os.getenv("PH_LLM_MIN_INTERVAL", "4.0"))
_throttle_lock = threading.Lock()
_last_call_at = 0.0

# Prefer the repo-wide unified router (free-first cascade + one spend log). Falls
# back transparently to the local Gemini/Groq path if the router or litellm is
# unavailable, so behavior is identical. Disable with PH_DISABLE_LLM_ROUTER=1.
_USE_ROUTER = os.getenv("PH_DISABLE_LLM_ROUTER", "0").lower() not in {"1", "true", "yes", "on"}
_ROUTER_TIER = os.getenv("PH_LLM_TIER", "cheap")


def _throttle() -> None:
    global _last_call_at
    with _throttle_lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()


def available() -> bool:
    return bool(GEMINI_API_KEY or GROQ_API_KEY)


def _sleep_for(exc: Exception, attempt: int) -> None:
    m = re.search(r"retryDelay'?\s*[:=]\s*'?(\d+)", str(exc))
    time.sleep(min(float(m.group(1)) if m else 3 * (attempt + 1), 25))


# --------------------------------------------------------------------------
# Provider calls
# --------------------------------------------------------------------------
def _gemini(prompt: str, system: str, temperature: float, json_mode: bool,
            max_retries: int = 2) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    cfg = types.GenerateContentConfig(
        system_instruction=system or None,
        temperature=temperature,
        response_mime_type="application/json" if json_mode else None,
    )
    last: Exception | None = None
    # Try each model; rotate to the next on quota exhaustion (per-model quota).
    for model in GEMINI_MODELS:
        for attempt in range(max_retries):
            try:
                _throttle()
                resp = client.models.generate_content(
                    model=model, contents=prompt, config=cfg)
                return (resp.text or "").strip()
            except Exception as exc:  # noqa: BLE001 - classified below
                last = exc
                s = str(exc)
                if any(tok in s for tok in _QUOTA):
                    break  # this model is exhausted -> try the next model
                if not any(tok in s for tok in _RETRYABLE):
                    raise
                _sleep_for(exc, attempt)
    raise last  # type: ignore[misc]


def _groq(prompt: str, system: str, temperature: float, json_mode: bool,
          max_retries: int = 3) -> str:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    kwargs = {"model": GROQ_MODEL, "messages": messages,
              "temperature": temperature}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            _throttle()
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            if not any(tok in str(exc).lower() for tok in _RETRYABLE):
                raise
            last = exc
            _sleep_for(exc, attempt)
    raise last  # type: ignore[misc]


def _via_router(prompt: str, system: str, temperature: float, json_mode: bool) -> str | None:
    """Try the unified llm_router; None if it can't serve (caller falls back)."""
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
    except Exception:  # noqa: BLE001
        return None


def complete(prompt: str, system: str = "", temperature: float = 0.2,
             json_mode: bool = False) -> str:
    """Text completion with provider failover (router -> Gemini -> Groq).

    Raises RuntimeError if no provider is configured or all providers fail.
    """
    routed = _via_router(prompt, system, temperature, json_mode)
    if routed is not None:
        return routed

    errors = []
    if GEMINI_API_KEY:
        try:
            return _gemini(prompt, system, temperature, json_mode)
        except Exception as exc:  # noqa: BLE001 - try the next provider
            errors.append(f"gemini: {exc}")
    if GROQ_API_KEY:
        try:
            return _groq(prompt, system, temperature, json_mode)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"groq: {exc}")
    raise RuntimeError(
        "no LLM provider available; " + " | ".join(errors)
        if errors else "no LLM provider configured (set GEMINI_API_KEY/GROQ_API_KEY)")


# --------------------------------------------------------------------------
# JSON helpers - LLMs sometimes wrap JSON in prose / code fences.
# --------------------------------------------------------------------------
def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def complete_json(prompt: str, system: str = "", temperature: float = 0.1,
                  default=None):
    """Completion that returns parsed JSON. Returns `default` on any failure."""
    try:
        raw = complete(prompt, system=system, temperature=temperature,
                       json_mode=True)
    except Exception:
        return default
    raw = _strip_fences(raw)
    try:
        return json.loads(raw)
    except Exception:
        # Last resort: grab the outermost JSON object/array in the blob.
        m = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return default
    return default
