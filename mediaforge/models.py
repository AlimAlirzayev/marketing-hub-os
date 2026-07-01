"""FLORA video-model catalog and an honest alias resolver.

Mirrors `video-studio/generative_ads/model_matrix.flora.md` (refreshed
2026-05-22). The catalog can drift — FLORA's real list is authoritative via the
MCP `flora models list --type video`. So this resolver never pretends: when a
user asks for a model that is not in the catalog (e.g. "seedance 2.5"), it maps
to the closest real model AND surfaces a note, instead of silently inventing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


CATALOG_REFRESHED = "2026-05-22"


@dataclass(frozen=True)
class VideoModel:
    id: str
    kind: str            # "i2v" | "t2v"
    tier: str            # "discovery" | "production" | "premium"
    label: str
    durations_s: tuple[int, ...]
    max_resolution: str
    strength: str
    limitation: str


CATALOG: dict[str, VideoModel] = {
    "i2v-seedance-1.5-pro": VideoModel(
        "i2v-seedance-1.5-pro", "i2v", "discovery", "Seedance 1.5 Pro",
        (4, 6, 8, 10, 12), "720p",
        "Fast, cheap, great first motion exploration",
        "720p max in current catalog; can mutate text/UI",
    ),
    "i2v-kling-2.6": VideoModel(
        "i2v-kling-2.6", "i2v", "discovery", "Kling 2.6",
        (5, 10), "1080p",
        "Good short motion and commercial polish",
        "Few controls in CLI schema",
    ),
    "i2v-seedance-2-0-reference-i2v-enhancor": VideoModel(
        "i2v-seedance-2-0-reference-i2v-enhancor", "i2v", "production",
        "Seedance 2.0 Reference (Enhancor)",
        (4, 6, 8, 10, 12, 15), "1080p",
        "Best fit for reference-led brand consistency",
        "Higher cost than discovery tier",
    ),
    "i2v-runway-gen-4.5": VideoModel(
        "i2v-runway-gen-4.5", "i2v", "production", "Runway Gen-4.5",
        (5, 8, 10), "1080p",
        "Strong high-end motion from reference stills",
        "No explicit resolution param in current CLI schema",
    ),
    "i2v-sora2-pro": VideoModel(
        "i2v-sora2-pro", "i2v", "production", "Sora 2 Pro",
        (4, 8, 12), "1080p",
        "Strong temporal storytelling and smooth motion",
        "Slow; 10s not available — pick 8s or 12s",
    ),
    "i2v-veo-3-1-lite-i2v": VideoModel(
        "i2v-veo-3-1-lite-i2v", "i2v", "production", "Veo 3.1 Lite",
        (4, 6, 8), "1080p",
        "High-quality short clips",
        "Max 8s in current catalog",
    ),
    "i2v-veo3": VideoModel(
        "i2v-veo3", "i2v", "premium", "Veo 3",
        (4, 6, 8), "1080p",
        "Premium cinematic motion",
        "Very high cost; sparse CLI params",
    ),
    "t2v-kling-v3-pro": VideoModel(
        "t2v-kling-v3-pro", "t2v", "premium", "Kling v3 Pro",
        (3, 5, 8, 10, 12, 15), "4k",
        "Strong 1080p/4k cinematic text-to-video",
        "No image reference; weaker brand consistency",
    ),
}


# User-friendly alias -> catalog id. Order matters: most specific first.
_ALIASES: list[tuple[str, str]] = [
    (r"seedance\s*2[._]?5", "i2v-seedance-2-0-reference-i2v-enhancor"),
    (r"seedance\s*2([._]0)?", "i2v-seedance-2-0-reference-i2v-enhancor"),
    (r"seedance\s*1[._]?5", "i2v-seedance-1.5-pro"),
    (r"seedance", "i2v-seedance-2-0-reference-i2v-enhancor"),
    (r"runway|gen[-\s]*4", "i2v-runway-gen-4.5"),
    (r"sora", "i2v-sora2-pro"),
    (r"kling\s*v?3", "t2v-kling-v3-pro"),
    (r"kling", "i2v-kling-2.6"),
    (r"veo\s*3[._]?1|veo.*lite", "i2v-veo-3-1-lite-i2v"),
    (r"veo", "i2v-veo3"),
]

# Recommended second-variant partner per resolved model (reference vs motion).
_PARTNER: dict[str, str] = {
    "i2v-seedance-2-0-reference-i2v-enhancor": "i2v-runway-gen-4.5",
    "i2v-runway-gen-4.5": "i2v-seedance-2-0-reference-i2v-enhancor",
    "i2v-sora2-pro": "i2v-seedance-2-0-reference-i2v-enhancor",
    "i2v-veo3": "i2v-seedance-2-0-reference-i2v-enhancor",
    "t2v-kling-v3-pro": "i2v-seedance-2-0-reference-i2v-enhancor",
    "i2v-kling-2.6": "i2v-seedance-2-0-reference-i2v-enhancor",
    "i2v-seedance-1.5-pro": "i2v-runway-gen-4.5",
    "i2v-veo-3-1-lite-i2v": "i2v-seedance-2-0-reference-i2v-enhancor",
}

# Relative cost band per tier (FLORA prices are credits — confirm run_cost via
# MCP before firing; we never invent a USD number).
_TIER_COST = {
    "discovery": "aşağı (kəşfiyyat)",
    "production": "orta (client-facing)",
    "premium": "yüksək (hero/kino)",
}


def resolve(alias: str | None, *, want_duration: int = 10) -> dict[str, Any]:
    """Resolve a user model phrase to a real catalog model, honestly.

    Returns a dict with the resolved model, any substitution note, a duration
    that the model actually supports, and a recommended second variant.
    """
    notes: list[str] = []
    raw = (alias or "").strip()
    resolved_id: str | None = None
    exact = raw.casefold().replace(" ", "")

    # 1. exact catalog id?
    for cid in CATALOG:
        if exact == cid.casefold().replace(" ", ""):
            resolved_id = cid
            break

    # 2. alias regex
    if resolved_id is None and raw:
        low = raw.casefold()
        for pattern, cid in _ALIASES:
            if re.search(pattern, low):
                resolved_id = cid
                if not re.search(r"seedance\s*2[._]?5", low):
                    break
                # explicit "2.5" — flag the substitution
                notes.append(
                    "Kataloqda dəqiq 'Seedance 2.5' yoxdur; ən yaxın uyğun model "
                    "Seedance 2.0 Reference (Enhancor) seçildi. FLORA kataloqu "
                    "dəyişə bilər — MCP `flora models list --type video` ilə təsdiqlə."
                )
                break

    # 3. nothing matched -> default production reference model
    if resolved_id is None:
        resolved_id = "i2v-seedance-2-0-reference-i2v-enhancor"
        if raw:
            notes.append(
                f"'{raw}' kataloqda tapılmadı; standart production modeli "
                "Seedance 2.0 Reference seçildi."
            )

    model = CATALOG[resolved_id]
    duration = _nearest_duration(model, want_duration, notes)
    partner_id = _PARTNER.get(resolved_id, "i2v-runway-gen-4.5")

    return {
        "requested": raw or None,
        "model": model,
        "model_id": model.id,
        "label": model.label,
        "tier": model.tier,
        "cost_band": _TIER_COST[model.tier],
        "duration_s": duration,
        "requested_duration_s": want_duration,
        "partner_id": partner_id,
        "partner_label": CATALOG[partner_id].label,
        "fallbacks": ["i2v-kling-2.6", "i2v-seedance-1.5-pro", "deterministic-remotion"],
        "notes": notes,
        "catalog_refreshed": CATALOG_REFRESHED,
    }


def _nearest_duration(model: VideoModel, want: int, notes: list[str]) -> int:
    if want in model.durations_s:
        return want
    nearest = min(model.durations_s, key=lambda d: abs(d - want))
    notes.append(
        f"{model.label} {want}s dəstəkləmir; ən yaxın dəstəklənən {nearest}s seçildi "
        f"(dəstəklənən: {', '.join(str(d) + 's' for d in model.durations_s)})."
    )
    return nearest


def as_dict(resolution: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe view (drops the dataclass) for API responses."""
    out = dict(resolution)
    m: VideoModel = out.pop("model")
    out["model_kind"] = m.kind
    out["model_strength"] = m.strength
    out["model_limitation"] = m.limitation
    out["model_max_resolution"] = m.max_resolution
    out["model_durations"] = list(m.durations_s)
    return out
