"""Creative Lab - the art-director prompt engine.

Takes a one-line brief and composes N distinct, copy-paste-ready image prompts,
each built on the 11-layer master_template, grounded in the active Style DNA +
brand identity + the AI-tells exclusion list + the model dialect + the user's
house rules. This is the hard, valuable part - and it runs on the free text LLM,
so the ChatGPT Bridge flow (user generates the actual image in their ChatGPT
Business UI) costs nothing extra.

Always returns N concepts: if Gemini is unavailable, a deterministic template
composer fills in from the Style DNA's verbatim reference phrases.
"""

from __future__ import annotations

import json
import re

from . import brand, config, llm

# Keep grounding context bounded so we stay well within free-tier limits.
_CAP_STYLE = 4000
_CAP_BRAND = 2500
_CAP_DIALECT = 1800
_CAP_TELLS = 1600


def _clip(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[:n].rsplit("\n", 1)[0] + "\n…"


def _system() -> str:
    return (
        "You are a senior art director and image-prompt engineer for Xalq "
        "Sigorta, a premium Azerbaijani financial-services brand. You write "
        "advertising-grade prompts that read like a real photo brief, never "
        "like generic AI stock. You strictly obey the brand's hard rules and "
        "the AI-tells exclusion list. You always answer with valid JSON only - "
        "no prose, no markdown fences."
    )


def _build_prompt(brief: str, style: dict, dialect_key: str, dialect_md: str,
                  fmt_spec: str, n: int, with_caption: bool, voice: dict | None,
                  house_rules: str, extra_exclusions: str) -> str:
    parts = [
        f"BRIEF: {brief.strip()}",
        f"OUTPUT FORMAT (Layer 1 constraint): {fmt_spec}.",
        f"TARGET IMAGE MODEL: {dialect_key} - phrase prompts the way this model "
        f"prefers (see dialect notes).",
        "",
        "=== 11-LAYER SKELETON (every prompt must cover these) ===\n"
        "1 Constraint  2 Camera&Lens  3 Lighting  4 Subject identity  "
        "5 Brand props (HEX-precise)  6 Scene background  7 Brand atmosphere  "
        "8 Negative space for overlay  9 Style anchor (real references)  "
        "10 Quality directives  11 Exclusion list (AI-tells first).",
        "",
        "=== ACTIVE STYLE DNA ===\n" + _clip(style.get("body", ""), _CAP_STYLE),
        "",
        "=== BRAND IDENTITY (hard rules override everything) ===\n"
        + _clip(brand.brand_identity(), _CAP_BRAND),
        "",
        "=== MODEL DIALECT NOTES ===\n" + _clip(dialect_md, _CAP_DIALECT),
        "",
        "=== AI-TELLS TO EXCLUDE (pick the 8-12 most likely, order by "
        "probability, put text/letters first) ===\n"
        + _clip(brand.ai_tells(), _CAP_TELLS),
    ]
    if house_rules.strip():
        parts += ["", "=== HOUSE RULES (must respect) ===\n" + house_rules.strip()]
    if extra_exclusions.strip():
        parts += ["", "=== EXTRA EXCLUSIONS ===\n" + extra_exclusions.strip()]
    if with_caption and voice:
        parts += ["", "=== CAPTION VOICE DNA (for the Azerbaijani caption) ===\n"
                  + _clip(voice.get("body", ""), 2200)]

    cap_field = (
        ', "caption": "an Azerbaijani Instagram caption in the voice above, '
        '2-4 short lines, calm authority, no clickbait, no emoji"'
        if with_caption else ""
    )
    parts += [
        "",
        f"TASK: Produce EXACTLY {n} DISTINCT creative concepts for this brief. "
        "Each concept must take a genuinely different visual angle (different "
        "subject/scene/composition) - not minor variations. Reserve the "
        "upper-left third clean for the headline and the bottom ~180px clean "
        "for the vector footer (these are added later, never rendered).",
        "",
        "Return a JSON array of objects with EXACTLY these keys:",
        '  "angle"     : 3-5 word title for the concept',
        '  "rationale" : one sentence on why this idea fits the brief + brand',
        '  "prompt"    : the FULL copy-paste-ready image prompt (covers all 11 '
        'layers, phrased for the target model, ends with the exclusion list)'
        + cap_field,
        "",
        "JSON only. No commentary.",
    ]
    return "\n".join(parts)


def _extract_json_array(text: str) -> list[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass
    return []


def _normalize(items: list[dict], n: int) -> list[dict]:
    out = []
    for i, it in enumerate(items[:n]):
        prompt = str(it.get("prompt", "")).strip()
        if not prompt:
            continue
        out.append({
            "idx": i,
            "angle": str(it.get("angle", f"Concept {i + 1}")).strip()[:80],
            "rationale": str(it.get("rationale", "")).strip(),
            "prompt": prompt,
            "caption": str(it.get("caption", "")).strip(),
        })
    return out


def _fallback(brief: str, style: dict, fmt_spec: str, n: int,
              extra_exclusions: str) -> list[dict]:
    """Deterministic composer when Gemini is unavailable - uses the Style DNA's
    verbatim Layer-9 reference phrases so output is still on-brand."""
    refs = re.findall(r'"([^"]+)"', style.get("body", ""))
    refs = [r for r in refs if len(r) > 25][:6] or [
        "Premium financial-services editorial photography."]
    angles = [
        "Single subject, considered", "Environmental wide", "Brand prop macro",
        "Partnership / two-subject", "Architectural frame", "Negative-space hero",
        "Material still life", "Documentary candid",
    ]
    base_excl = ("✗ Any visible text or readable signage\n✗ Watermarks\n"
                 "✗ Plastic AI skin, smooth airbrushed faces\n"
                 "✗ Extra/fused fingers\n✗ Floating shadow-less subject\n"
                 "✗ HDR-flattened lighting\n✗ Brand red as more than 5% of frame")
    if extra_exclusions.strip():
        base_excl += "\n" + extra_exclusions.strip()
    out = []
    for i in range(n):
        ref = refs[i % len(refs)]
        out.append({
            "idx": i,
            "angle": angles[i % len(angles)],
            "rationale": "Template-composed (AI offline) - on-brand from Style DNA.",
            "prompt": (
                f"=== FORMAT ===\n{fmt_spec}. Background plate only; headline and "
                f"footer added later.\n\n=== BRIEF ===\n{brief.strip()}\n\n"
                f"=== STYLE ANCHOR ===\n{ref}\n\n=== COMPOSITION ===\n"
                f"{angles[i % len(angles)]}. Reserve the upper-left third and the "
                f"bottom 180px clean for overlay.\n\n=== LIGHTING ===\nSingle soft "
                f"daylight key, crisp shadow modeling preserved, ~5000K.\n\n"
                f"=== BRAND ===\nXalq Sigorta brand red #E31E24 used surgically, "
                f"never above 5% of frame. Premium materials with patina.\n\n"
                f"=== QUALITY ===\nVisible skin texture, natural hand anatomy, "
                f"ISO 200 film grain.\n\n=== EXCLUDE (in order) ===\n{base_excl}"),
            "caption": "",
        })
    return out


def compose(brief: str, style_key: str, voice_key: str, dialect_key: str,
            fmt_label: str, n: int, with_caption: bool,
            house_rules: str = "", extra_exclusions: str = "") -> dict:
    """Returns {"concepts": [...], "source": "gemini"|"template", "meta": {...}}."""
    n = max(1, min(8, int(n)))
    style = next((s for s in brand.list_style_dna() if s["key"] == style_key), None) \
        or {"key": style_key, "body": ""}
    voice = next((v for v in brand.list_voice_dna() if v["key"] == voice_key), None)
    dialect_md = brand.dialect_body(dialect_key)
    fmt_spec = config.FORMATS.get(fmt_label, fmt_label)

    meta = {"style": style_key, "voice": voice_key, "dialect": dialect_key,
            "format": fmt_label}

    if llm.available():
        try:
            raw = llm.gemini_text(
                _build_prompt(brief, style, dialect_key, dialect_md, fmt_spec,
                              n, with_caption, voice, house_rules, extra_exclusions),
                system=_system(), temperature=0.85)
            concepts = _normalize(_extract_json_array(raw), n)
            if concepts:
                return {"concepts": concepts, "source": "gemini", "meta": meta}
        except Exception:  # noqa: BLE001 - any failure falls back, never errors out
            pass
    return {"concepts": _fallback(brief, style, fmt_spec, n, extra_exclusions),
            "source": "template", "meta": meta}
