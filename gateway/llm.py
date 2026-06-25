"""Lightweight LLM calls for the gateway.

Deliberately does NOT use langchain/crewai: those pull heavy, sometimes
native dependencies that are unreliable on the locked-down corporate machine.
We call providers with their thin SDKs instead.

Takes the routing decision from ``orchestrator.router`` (a ModelChoice) and
turns it into a real completion. Today only Gemini is wired (its key is live
and free). Other providers raise a clear, recoverable error so the executor
can fall back to Gemini instead of crashing the whole job.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

from ._bootstrap import load_env
from orchestrator.router import ModelChoice

load_env()

_MAX_RETRIES = 4
_MAX_BACKOFF = 65  # seconds; free-tier RPM windows reset each minute

# Transient failures worth retrying: rate limits AND server-side overloads.
_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL", "overloaded")


def _is_retryable(exc: Exception) -> bool:
    s = str(exc)
    return any(tok in s for tok in _RETRYABLE)


def _retry_delay(exc: Exception, fallback: float) -> float:
    """Honor the API's suggested retryDelay if present, else use fallback."""
    m = re.search(r"retryDelay'?\s*[:=]\s*'?(\d+)", str(exc))
    return float(m.group(1)) if m else fallback


class ProviderNotConfigured(RuntimeError):
    """Raised when a provider has no usable credentials. Recoverable."""


def _gemini(model: str, prompt: str, system: str | None, use_search: bool = False) -> str:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ProviderNotConfigured("GEMINI_API_KEY / GOOGLE_API_KEY not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    # google_search grounding = live web access with zero extra keys/deps.
    tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else None
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.7,
        tools=tools,
    )
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            return (resp.text or "").strip()
        except Exception as exc:  # retry transient rate limits / overloads
            if not _is_retryable(exc):
                raise
            last_exc = exc
            time.sleep(min(_retry_delay(exc, 5 * (attempt + 1)), _MAX_BACKOFF))
    raise last_exc  # exhausted retries


def _not_wired(name: str):
    def _call(model: str, prompt: str, system: str | None, use_search: bool = False) -> str:
        raise ProviderNotConfigured(f"{name} provider not wired/credentialed yet")

    return _call


_PROVIDERS = {
    "gemini": _gemini,
    "anthropic": _not_wired("anthropic"),  # key still placeholder in .env
    "groq": _not_wired("groq"),
    "ollama": _not_wired("ollama"),
}

# Where to fall back when the routed provider has no credentials.
# NOTE: gemini-2.0-flash has a 0 free-tier quota on this key (regional); the
# 2.5+ models work, so default to one of those.
_FALLBACK = ModelChoice(
    provider="gemini",
    model=os.getenv("MODEL_FREE_BULK", "gemini-3.5-flash"),
    reason="fallback: routed provider not configured",
)


def _tier_for(choice: ModelChoice) -> str:
    """Map a routing decision to the unified router's tier. The 20% (planning /
    final synthesis / pro / paid providers) is 'smart'; everything else 'cheap'."""
    if choice.provider in ("anthropic", "openai") or "pro" in (choice.model or ""):
        return "smart"
    return "cheap"


def complete(
    choice: ModelChoice,
    prompt: str,
    system: str | None = None,
    use_search: bool = False,
) -> tuple[str, ModelChoice]:
    """Run a completion for ``choice``; fall back to Gemini if unconfigured.

    Routing has ONE brain: ``orchestrator.router`` *classifies* (task → tier), and
    ``llm_router`` (LiteLLM) *executes* that tier's free-first cascade. This
    function is the thin adapter between them. ``use_search`` enables live Google
    Search grounding (Gemini-only, so it keeps the direct path). Returns
    ``(text, used_choice)`` so callers can see if a fallback happened.
    """
    if not use_search:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from llm_router import complete as _route
            text, model = _route(prompt, system=system, tier=_tier_for(choice))
            return text, ModelChoice(provider="router", model=model, reason="llm_router")
        except Exception:
            pass  # router/litellm unavailable → fall back to direct providers

    fn = _PROVIDERS.get(choice.provider)
    if fn is not None:
        try:
            return fn(choice.model, prompt, system, use_search), choice
        except ProviderNotConfigured:
            pass  # fall through to the free tier
    text = _PROVIDERS["gemini"](_FALLBACK.model, prompt, system, use_search)
    return text, _FALLBACK
