"""The brain: one sentence -> a directed, validated creative brief.

`parse_request` does deterministic intent extraction (model, duration, product,
platform). `direct` then authors the creative brief. It prefers the free-first
LLM router for genuine creativity, but always has a strong deterministic
fallback built from the category playbook, so the system NEVER fails silently —
it always returns a professional, schema-valid brief.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from . import knowledge, models


# --------------------------------------------------------------------------- #
# Intent parsing
# --------------------------------------------------------------------------- #
_AZ_LETTERS = set("əığşçöüĞŞÇÖÜİ")
_MODEL_HINT = re.compile(r"(seedance[\s._0-9]*\d?|kling[\s._v0-9]*\d?|runway[\s\w.-]*|sora[\s._0-9]*\d?|veo[\s._0-9]*\d?)", re.I)
_DURATION = re.compile(r"(\d{1,2})\s*(?:saniy[əe]lik|saniy[əe]|second[s]?|sec|s\b)", re.I)

_PLATFORMS = [
    (("tiktok",), "tiktok", "tiktok-feed", "9:16"),
    (("youtube shorts", "shorts"), "youtube", "youtube-shorts", "9:16"),
    (("youtube",), "youtube", "youtube-instream", "16:9"),
    (("linkedin",), "linkedin", "linkedin-feed", "1:1"),
    (("reels", "instagram", "insta", "meta", "facebook"), "meta", "instagram-facebook-reels", "9:16"),
]


def detect_language(text: str) -> str:
    return "az" if any(ch in _AZ_LETTERS for ch in text) else "en"


def parse_request(sentence: str) -> dict[str, Any]:
    """Deterministically extract structured intent from a free-text sentence."""
    text = (sentence or "").strip()
    low = text.casefold()

    m = _MODEL_HINT.search(text)
    model_phrase = m.group(1).strip() if m else None

    d = _DURATION.search(text)
    duration = int(d.group(1)) if d else 10
    duration = max(3, min(60, duration))

    category = knowledge.category_for(text)

    platform_name, placement, aspect = "meta", "instagram-facebook-reels", "9:16"
    for keys, pname, place, asp in _PLATFORMS:
        if any(k in low for k in keys):
            platform_name, placement, aspect = pname, place, asp
            break

    return {
        "raw": text,
        "language": detect_language(text),
        "model_phrase": model_phrase,
        "duration_s": duration,
        "category": category,
        "platform": platform_name,
        "placement": placement,
        "aspect": aspect,
    }


# --------------------------------------------------------------------------- #
# Brief authoring
# --------------------------------------------------------------------------- #
_ASPECT_RES = {"9:16": [1080, 1920], "16:9": [1920, 1080], "1:1": [1080, 1080], "4:5": [1080, 1350]}


def _slug(category: str, platform: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{category}-{platform}-{stamp}"


def _user_prompt(request: dict[str, Any], resolution: dict[str, Any]) -> str:
    pb = knowledge.playbook(request["category"])
    return f"""Brief request (one sentence from the marketer):
"{request['raw']}"

Target: {resolution['duration_s']}-second {request['aspect']} {request['platform']} promo video.
Product: {pb['product']}. Model that will render it: {resolution['label']} ({resolution['tier']} tier).

Author the creative. Return ONLY JSON with this exact shape:
{{
  "concept": {{
    "name": "short evocative concept name",
    "big_idea": "one sentence — the single creative idea",
    "emotional_arc": "the feeling curve across the {resolution['duration_s']}s",
    "framework": "which story framework and why, in one line",
    "why_it_works": "one line on why a scrolling human stops and feels this"
  }},
  "objective": {{
    "primary": "the marketing objective",
    "audience": "who this speaks to (Azerbaijani market)",
    "single_minded_message": "the ONE message, refined from the product truth",
    "conversion_action": "what we want them to do"
  }},
  "offer": {{
    "headline": "emotional Azerbaijani headline (brand-level, NO invented price/date)",
    "subheadline": "supporting Azerbaijani line",
    "cta": "short Azerbaijani CTA"
  }},
  "storyboard": [
    {{"time":"0.0-1.5s","beat":"hook","visual":"...","motion":"name a concrete camera move + shot type","overlay":"AZ overlay text for this beat"}},
    {{"time":"1.5-4.0s","beat":"story","visual":"...","motion":"...","overlay":"..."}},
    {{"time":"4.0-7.5s","beat":"turn","visual":"...","motion":"...","overlay":"..."}},
    {{"time":"7.5-{resolution['duration_s']}.0s","beat":"land","visual":"...","motion":"stable end frame","overlay":"CTA + brand"}}
  ],
  "overlay_text": ["every exact AZ line that must be a deterministic overlay"],
  "selection_criteria": ["what a good render must satisfy"],
  "qa_reject": ["reject the render if ..."],
  "qa_approve": ["approve the render if ..."]
}}

Rules: cinematic, premium, human. Direct MOTION not typography. Never render
readable AZ text in pixels. Do not invent prices, dates, or phone numbers."""


def _brief_from_creative(
    request: dict[str, Any],
    resolution: dict[str, Any],
    creative: dict[str, Any],
) -> dict[str, Any]:
    """Assemble a schema-valid brief from creative fields + compliance defaults."""
    pb = knowledge.playbook(request["category"])
    aspect = request["aspect"]
    res = _ASPECT_RES.get(aspect, [1080, 1920])
    slug = _slug(request["category"], request["platform"])

    storyboard = creative.get("storyboard") or _fallback_storyboard(pb, resolution["duration_s"])
    storyboard = [
        {
            "time": str(b.get("time", "")),
            "beat": str(b.get("beat", "")),
            "visual": str(b.get("visual", "")),
            "motion": str(b.get("motion", "")),
            "overlay": str(b.get("overlay", "")),
        }
        for b in storyboard[:6]
    ]

    obj = creative.get("objective") or {}
    off = creative.get("offer") or {}
    overlay_text = [str(x) for x in (creative.get("overlay_text") or []) if str(x).strip()]
    if not overlay_text:
        overlay_text = [off.get("headline", pb["single_minded"]), off.get("cta", "Ətraflı bax")]

    recommended = [resolution["model_id"], resolution["partner_id"]]
    variant_count = min(8, max(1, len(recommended) + 1))

    return {
        "version": "1",
        "campaign": {
            "slug": slug,
            "name": creative.get("concept", {}).get("name") or f"{pb['product']} promo",
            "language": request["language"] if request["language"] in {"az", "en"} else "az",
            "owner": "Xalq Sigorta Marketing",
            "source_brief": request["raw"],
        },
        "platform": {
            "name": request["platform"],
            "placement": request["placement"],
            "paid_media_notes": (
                f"{resolution['duration_s']}s paid {request['platform']}. The hook must "
                "read in the first second; CTA must settle and hold for the last ~0.8s."
            ),
        },
        "format": {
            "aspect": aspect,
            "duration_s": resolution["duration_s"],
            "resolution": res,
            "fps": 30,
            "safe_area": "Keep primary copy in the central 900x1500 px; avoid bottom app UI zone.",
        },
        "objective": {
            "primary": obj.get("primary") or f"Drive consideration for {pb['product']}.",
            "audience": obj.get("audience") or "Azerbaijani audience relevant to this insurance line.",
            "single_minded_message": obj.get("single_minded_message") or pb["single_minded"],
            "conversion_action": obj.get("conversion_action") or "Learn more / contact Xalq Sigorta",
        },
        "brand": {
            "name": knowledge.BRAND_DNA["name"],
            "identity_source": knowledge.BRAND_DNA["identity_source"],
            "tone": list(knowledge.BRAND_DNA["tone"]),
            "palette": list(knowledge.BRAND_DNA["palette"]),
            "typography": list(knowledge.BRAND_DNA["typography"]),
            "rules": list(knowledge.BRAND_DNA["rules"]),
        },
        "offer": {
            "headline": off.get("headline") or pb["single_minded"],
            "subheadline": off.get("subheadline") or "",
            "dates": "[təsdiq gözlənir]",
            "cta": off.get("cta") or "Ətraflı bax",
            "terms": [],
        },
        "assets": [
            {
                "role": "brand_logo",
                "path_or_url": "social-studio/brand_kit/xalqsigorta-logo-official.svg",
                "usage": "Final deterministic overlay logo.",
                "must_preserve": ["exact logo geometry", "official color"],
            },
            {
                "role": "style_reference",
                "path_or_url": "social-studio/brand_kit/brand.md",
                "usage": "Brand color, tone and typography reference for the motion plate.",
                "must_preserve": list(pb.get("signature_scenes", []))[:2],
            },
        ],
        "storyboard": storyboard,
        "model_strategy": {
            "recommended": recommended,
            "fallbacks": resolution["fallbacks"],
            "variant_count": variant_count,
            "selection_criteria": [str(x) for x in (creative.get("selection_criteria") or [
                "hook is premium and readable in the first second",
                "motion supports the story without random cinematic drift",
                "no AI-generated readable Azerbaijani text in the foreground",
                "clean negative space held for the deterministic overlay",
                "stable final frame for CTA and thumbnail",
            ])],
        },
        "text_policy": {
            "ai_text_rule": (
                "Generate a textless / low-text motion plate. All exact Azerbaijani "
                "copy, logo, price, date and CTA are deterministic overlays added after."
            ),
            "overlay_text": overlay_text,
            "forbidden": [
                "mutated Azerbaijani text",
                "invented prices or dates",
                "fake Xalq Sigorta logo",
                "new sponsor brands",
                "warped UI controls",
                *[f"avoid: {a}" for a in pb.get("avoid", [])],
            ],
        },
        "qa": {
            "reject_if": [str(x) for x in (creative.get("qa_reject") or [
                "Azerbaijani text is generated or malformed in the foreground",
                "Xalq Sigorta identity is altered",
                "the offer is not understandable without audio",
                "the final CTA is not readable for the last 0.8 seconds",
            ])],
            "approve_if": [str(x) for x in (creative.get("qa_approve") or [
                "the first second reads as a premium, thumb-stopping frame",
                "the motion plate supports the concept and emotional arc",
                "all exact copy is locked as overlay text",
                "the video works without audio and is ready for upload",
            ])],
        },
    }


def _fallback_storyboard(pb: dict[str, Any], duration: int) -> list[dict[str, str]]:
    scenes = pb["signature_scenes"]
    end = f"7.5-{duration}.0s"
    return [
        {
            "time": "0.0-1.5s", "beat": "Hook — freedom",
            "visual": scenes[0],
            "motion": "slow push-in, hero wide → detail; motion already alive",
            "overlay": "",
        },
        {
            "time": "1.5-4.0s", "beat": "Story — a small 'what if'",
            "visual": scenes[1] if len(scenes) > 1 else scenes[0],
            "motion": "handheld intimacy, gentle parallax; soft desaturation on the risk beat",
            "overlay": "",
        },
        {
            "time": "4.0-7.5s", "beat": "Turn — the invisible safety net",
            "visual": scenes[2] if len(scenes) > 2 else scenes[0],
            "motion": "match cut on motion into a calm, high-key resolve",
            "overlay": pb["single_minded"],
        },
        {
            "time": end, "beat": "Land — brand + CTA",
            "visual": scenes[3] if len(scenes) > 3 else scenes[-1],
            "motion": "locked-off stable end frame; hold the last beat",
            "overlay": "Xalq Sığorta · Ətraflı bax",
        },
    ]


def _deterministic_creative(request: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any]:
    pb = knowledge.playbook(request["category"])
    fw = knowledge.FRAMEWORKS[pb["recommended_framework"]]
    arc = knowledge.EMOTION_ARCS[pb["recommended_arc"]]
    return {
        "concept": {
            "name": f"{pb['product']} — {pb.get('single_minded', '')[:32]}",
            "big_idea": pb.get("core_truth_az", pb["core_truth"]),
            "emotional_arc": " → ".join(arc.get("curve_az", arc["curve"])),
            "framework": fw["name"],
            "why_it_works": pb.get("core_truth_az", pb["core_truth"]),
        },
        "objective": {
            "primary": f"Drive consideration for {pb['product']}.",
            "audience": "Azerbaijani audience relevant to this insurance line.",
            "single_minded_message": pb["single_minded"],
            "conversion_action": "Learn more / contact Xalq Sigorta",
        },
        "offer": {
            "headline": pb["single_minded"],
            "subheadline": "",
            "cta": "Ətraflı bax",
        },
        "storyboard": _fallback_storyboard(pb, resolution["duration_s"]),
        "overlay_text": [pb["single_minded"], "Xalq Sığorta", "Ətraflı bax"],
        "_engine": "deterministic",
    }


def direct(sentence: str, *, use_llm: bool = True) -> dict[str, Any]:
    """Full brain pass: sentence -> {request, resolution, concept, brief, meta}."""
    request = parse_request(sentence)
    resolution = models.resolve(request["model_phrase"], want_duration=request["duration_s"])

    creative: dict[str, Any] | None = None
    engine = "deterministic"
    llm_model = None
    llm_error = None

    if use_llm:
        try:
            creative, llm_model = _author_with_llm(request, resolution)
            engine = "llm"
        except Exception as exc:  # noqa: BLE001 — fall back, never fail the job
            llm_error = str(exc)[:200]

    if creative is None:
        creative = _deterministic_creative(request, resolution)

    concept = creative.get("concept") or {}
    brief = _brief_from_creative(request, resolution, creative)
    errors = validate_brief(brief)
    if errors:
        # If the LLM produced something malformed, fall back deterministically.
        creative = _deterministic_creative(request, resolution)
        concept = creative["concept"]
        brief = _brief_from_creative(request, resolution, creative)
        errors = validate_brief(brief)
        engine = "deterministic"

    return {
        "request": request,
        "resolution": models.as_dict(resolution),
        "concept": concept,
        "brief": brief,
        "meta": {
            "engine": engine,
            "llm_model": llm_model,
            "llm_error": llm_error,
            "valid": not errors,
            "validation_errors": errors,
        },
    }


def _author_with_llm(request: dict[str, Any], resolution: dict[str, Any]) -> tuple[dict[str, Any], str]:
    import llm_router  # local root module

    system = knowledge.director_system_prompt(request["category"])
    prompt = _user_prompt(request, resolution)
    data, model_used = llm_router.complete_json(
        prompt, system=system, tier="cheap", temperature=0.75, max_tokens=1600
    )
    if not isinstance(data, dict) or "storyboard" not in data:
        raise ValueError("LLM did not return a usable creative object")
    return data, model_used


# --------------------------------------------------------------------------- #
# Validation (lightweight, no external jsonschema dependency)
# --------------------------------------------------------------------------- #
_TOP = ["version", "campaign", "platform", "format", "objective", "brand",
        "offer", "assets", "storyboard", "model_strategy", "text_policy", "qa"]
_ASPECTS = {"9:16", "4:5", "1:1", "16:9"}
_FPS = {24, 25, 30, 60}
_PLATFORM_NAMES = {"meta", "instagram", "tiktok", "linkedin", "youtube", "generic"}
_ASSET_ROLES = {"brand_logo", "partner_logo", "product_reference", "campaign_key_visual",
                "motion_reference", "style_reference", "overlay_lockup", "music_reference", "legal_source"}


def validate_brief(brief: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in _TOP:
        if key not in brief:
            errors.append(f"missing top-level key: {key}")
    if errors:
        return errors
    if brief.get("version") != "1":
        errors.append("version must be '1'")
    fmt = brief["format"]
    if fmt.get("aspect") not in _ASPECTS:
        errors.append(f"format.aspect invalid: {fmt.get('aspect')}")
    if fmt.get("fps") not in _FPS:
        errors.append(f"format.fps invalid: {fmt.get('fps')}")
    if not (1 <= float(fmt.get("duration_s", 0)) <= 60):
        errors.append("format.duration_s out of range")
    if not (isinstance(fmt.get("resolution"), list) and len(fmt["resolution"]) == 2):
        errors.append("format.resolution must be [w, h]")
    if brief["platform"].get("name") not in _PLATFORM_NAMES:
        errors.append(f"platform.name invalid: {brief['platform'].get('name')}")
    for i, beat in enumerate(brief["storyboard"]):
        for k in ("time", "beat", "visual", "motion", "overlay"):
            if k not in beat:
                errors.append(f"storyboard[{i}] missing {k}")
    for i, asset in enumerate(brief["assets"]):
        if asset.get("role") not in _ASSET_ROLES:
            errors.append(f"assets[{i}].role invalid: {asset.get('role')}")
    ms = brief["model_strategy"]
    if not (1 <= int(ms.get("variant_count", 0)) <= 8):
        errors.append("model_strategy.variant_count out of range")
    for req_key in ("primary", "audience", "single_minded_message"):
        if not brief["objective"].get(req_key):
            errors.append(f"objective.{req_key} empty")
    return errors
