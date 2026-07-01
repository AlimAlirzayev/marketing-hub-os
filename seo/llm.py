"""Thin, graceful wrapper over the ecosystem's llm_router for SEO tasks.

Centralizes the SEO 'voice' (an expert AZ SEO strategist) and makes every LLM
call degrade gracefully: if no provider is configured or the call fails, callers
get None and fall back to a keyless path instead of crashing. Follows the 20/80
rule — clustering/first-drafts on `cheap`, final synthesis on `smart`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# make the repo-root importable (llm_router lives there), like other studios do
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

SEO_SYSTEM = (
    "Sən dünya səviyyəli, 2026 standartlarına hakim SEO strateqisən. Azərbaycan "
    "bazarını, axtarış niyyətini (search intent) və E-E-A-T / GEO (AI Overviews) "
    "prinsiplərini bilirsən. Cavabların dəqiq, praktik və uydurmasızdır."
)


def _tiers(smart: bool) -> list[str]:
    # smart first for quality, but always fall back to cheap — the premium free
    # tier (gemini-pro) rate-limits fast, and a 429 must never break the engine.
    return ["smart", "cheap"] if smart else ["cheap"]


def ask(prompt: str, *, smart: bool = False, temperature: float = 0.4) -> str | None:
    from llm_router import complete
    for tier in _tiers(smart):
        try:
            text, _ = complete(prompt, system=SEO_SYSTEM, tier=tier, temperature=temperature)
            if text:
                return text
        except Exception:  # noqa: BLE001 — try next tier, then give up gracefully
            continue
    return None


def ask_json(prompt: str, *, smart: bool = False, temperature: float = 0.3) -> dict | None:
    from llm_router import complete_json
    for tier in _tiers(smart):
        try:
            data, _ = complete_json(prompt, system=SEO_SYSTEM, tier=tier, temperature=temperature)
            if data:
                return data
        except Exception:  # noqa: BLE001
            continue
    return None


def available() -> bool:
    """True if at least one LLM provider is configured."""
    try:
        from llm_router import _cascade, _configured
        return any(_configured(req) for _, req in _cascade("cheap"))
    except Exception:  # noqa: BLE001
        return False
