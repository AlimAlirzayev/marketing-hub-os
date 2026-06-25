"""Creative critique - a vision art-director pass over an uploaded image.

After the user generates a concept in ChatGPT and uploads it back, this scores
the actual pixels against the brand rules + AI-tells, and checks the overlay
zones (upper-left for the headline, bottom strip for the footer) are clean.
Runs on free Gemini vision. If unavailable, returns a manual-review checklist
so the user still has a structured way to judge the image themselves.
"""

from __future__ import annotations

import json
import re

from . import brand, llm

_SYSTEM = (
    "You are a senior art director for Xalq Sigorta, a premium Azerbaijani "
    "financial-services brand. You review advertising images critically and "
    "honestly - you are hard to impress. You answer with valid JSON only."
)

_MANUAL = {
    "score": None,
    "verdict": "AI offline - manual review.",
    "brand_fit": "Gemini vision unavailable. Judge against the checklist below.",
    "strengths": [],
    "fixes": [
        "Brand red surgical (<5% of frame), never a wash?",
        "Premium materials with patina, realistic skin texture?",
        "Upper-left third clean for the headline?",
        "Bottom ~180px clean for the footer?",
        "No AI tells: plastic skin, extra fingers, fake text, floating shadows?",
        "Lighting has real shadow modeling (not HDR-flat)?",
    ],
    "ai_tells": [],
    "overlay": {"top_left_clear": None, "bottom_clear": None, "note": "manual"},
    "source": "manual",
}


def _build_prompt(angle: str, prompt_excerpt: str, style_key: str) -> str:
    return "\n".join([
        f"Review this advertising image. Intended concept: \"{angle}\" "
        f"(style: {style_key}).",
        "",
        "Brand hard rules:\n" + brand.brand_identity()[:1800],
        "",
        "AI-tells to catch:\n" + brand.ai_tells()[:1200],
        "",
        "Judge: brand fit, photographic realism, whether the upper-left third "
        "is clean for an Azerbaijani headline and the bottom ~180px is clean "
        "for the footer, and any AI tells actually visible in THIS image.",
        "",
        "Return JSON with EXACTLY these keys:",
        '  "score": integer 0-100 (overall brand-ready quality)',
        '  "verdict": one short sentence',
        '  "brand_fit": 1-2 sentences on how well it matches the brand',
        '  "strengths": array of short strings',
        '  "fixes": array of short, specific, actionable strings',
        '  "ai_tells": array of AI tells visible in this image (empty if none)',
        '  "overlay": {"top_left_clear": bool, "bottom_clear": bool, '
        '"note": short string}',
        "",
        "Be specific to what you actually see. JSON only.",
    ])


def _parse(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?", "", text.strip()).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _coerce(data: dict) -> dict:
    def _as_list(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return [str(v).strip()] if v else []

    score = data.get("score")
    try:
        score = max(0, min(100, int(score))) if score is not None else None
    except (TypeError, ValueError):
        score = None
    overlay = data.get("overlay") or {}
    if not isinstance(overlay, dict):
        overlay = {}
    return {
        "score": score,
        "verdict": str(data.get("verdict", "")).strip(),
        "brand_fit": str(data.get("brand_fit", "")).strip(),
        "strengths": _as_list(data.get("strengths")),
        "fixes": _as_list(data.get("fixes")),
        "ai_tells": _as_list(data.get("ai_tells")),
        "overlay": {
            "top_left_clear": overlay.get("top_left_clear"),
            "bottom_clear": overlay.get("bottom_clear"),
            "note": str(overlay.get("note", "")).strip(),
        },
        "source": "gemini",
    }


def review(image_bytes: bytes, mime_type: str, angle: str = "",
           prompt_excerpt: str = "", style_key: str = "") -> dict:
    if not llm.available():
        return dict(_MANUAL)
    try:
        raw = llm.gemini_vision(
            _build_prompt(angle, prompt_excerpt, style_key),
            image_bytes, mime_type, system=_SYSTEM, temperature=0.3)
        parsed = _parse(raw)
        if parsed:
            return _coerce(parsed)
    except Exception:  # noqa: BLE001 - never surface a raw error to the board
        pass
    return dict(_MANUAL)
