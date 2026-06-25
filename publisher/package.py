"""Xalq Insurance Digital OS Publisher - publish-package assembly.

Turns "publish this asset to these platforms" into a concrete, per-platform
plan: the right caption (trimmed to each platform's limit), hashtags, the media
file, and a scheduled time. The plan is provider-agnostic - the router hands it
to Postiz when it's up, or writes it as a manual handoff when it isn't.

Caption sources, in order: an explicit --caption override, the campaign's
copy-studio output (caption-*.md), a clip's title from clips.json, then a
slug-derived placeholder. Nothing is invented silently - the report says which.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOCIAL_OUT = REPO / "social-studio" / "output"
COPY_OUT = REPO / "copy-studio" / "output"

# provider = Postiz integration identifier; limit = caption char cap;
# media = what the platform expects.
PLATFORMS: dict[str, dict] = {
    "x":         {"provider": "x",         "limit": 280,  "media": "video"},
    "twitter":   {"provider": "x",         "limit": 280,  "media": "video"},
    "tiktok":    {"provider": "tiktok",    "limit": 2200, "media": "video"},
    "reels":     {"provider": "instagram", "limit": 2200, "media": "video"},
    "instagram": {"provider": "instagram", "limit": 2200, "media": "any"},
    "linkedin":  {"provider": "linkedin",  "limit": 3000, "media": "any"},
    "facebook":  {"provider": "facebook",  "limit": 5000, "media": "any"},
    "youtube":   {"provider": "youtube",   "limit": 5000, "media": "video"},
    "threads":   {"provider": "threads",   "limit": 500,  "media": "any"},
    "bluesky":   {"provider": "bluesky",   "limit": 300,  "media": "any"},
}

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


class PackageError(RuntimeError):
    """A recoverable packaging failure with a human-actionable message."""


def _strip_md(text: str) -> str:
    """Flatten a caption-*.md into plain post text."""
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("---") or s.startswith(">"):
            continue
        s = re.sub(r"[*_`]", "", s)            # drop md emphasis
        lines.append(s)
    return "\n".join(lines).strip()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "post"


def _trim(text: str, limit: int) -> str:
    """Trim to limit on a word boundary, keeping it clean."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "…"


# --------------------------------------------------------------------------- #
# Asset + caption resolution
# --------------------------------------------------------------------------- #

def resolve_asset(asset: str) -> dict:
    """Resolve a file path or a campaign slug into media + caption context."""
    p = Path(asset)
    if p.is_file():
        kind = "video" if p.suffix.lower() in VIDEO_EXT else "image"
        title = _title_from_manifest(p)
        return {"media": p, "kind": kind, "slug": _slugify(p.parent.name + "-" + p.stem),
                "title": title, "copy_dir": _maybe_copy_dir(p.parent.name)}

    # treat as a campaign slug
    slug = _slugify(asset)
    media, kind = _first_visual(SOCIAL_OUT / slug)
    copy_dir = COPY_OUT / slug
    if media is None and not copy_dir.is_dir():
        raise PackageError(
            f"'{asset}' is neither a file nor a known campaign slug "
            f"(looked in {SOCIAL_OUT/slug} and {copy_dir})."
        )
    return {"media": media, "kind": kind, "slug": slug, "title": None,
            "copy_dir": copy_dir if copy_dir.is_dir() else None}


def _title_from_manifest(clip: Path) -> str | None:
    manifest = clip.parent / "clips.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    for c in data.get("clips", []):
        if c.get("file") and Path(c["file"]).name == clip.name:
            return c.get("title")
    return None


def _maybe_copy_dir(name: str) -> Path | None:
    d = COPY_OUT / _slugify(name)
    return d if d.is_dir() else None


def _first_visual(folder: Path) -> tuple[Path | None, str]:
    if not folder.is_dir():
        return None, "image"
    for ext in (".mp4", ".png", ".jpg", ".jpeg", ".webp"):
        hit = next(iter(sorted(folder.glob(f"*{ext}"))), None)
        if hit:
            return hit, ("video" if ext == ".mp4" else "image")
    return None, "image"


def _caption_pool(copy_dir: Path | None) -> dict[str, str]:
    if not copy_dir:
        return {}
    pool = {}
    for f in copy_dir.glob("caption-*.md"):
        body = _strip_md(f.read_text(encoding="utf-8", errors="replace"))
        if body:
            pool[f.stem] = body
    return pool


def _pick_caption(platform: str, pool: dict[str, str], title: str | None, slug: str) -> tuple[str, str]:
    """Return (caption, source-label). Prefer copy-studio, then title, then slug."""
    prefs = {
        "instagram": ["caption-az-instagram", "caption-az-linkedin", "caption-en-international"],
        "reels":     ["caption-az-instagram", "caption-en-international"],
        "tiktok":    ["caption-az-instagram", "caption-en-international"],
        "youtube":   ["caption-az-instagram", "caption-en-international"],
        "linkedin":  ["caption-az-linkedin", "caption-az-instagram", "caption-en-international"],
        "facebook":  ["caption-az-instagram", "caption-az-linkedin"],
        "x":         ["caption-en-international", "caption-az-instagram"],
        "twitter":   ["caption-en-international", "caption-az-instagram"],
        "threads":   ["caption-en-international", "caption-az-instagram"],
        "bluesky":   ["caption-en-international", "caption-az-instagram"],
    }.get(platform, [])
    for key in prefs:
        if key in pool:
            return pool[key], key + ".md"
    if pool:                                   # any caption beats none
        k = next(iter(pool))
        return pool[k], k + ".md"
    if title:
        return title, "clip title"
    return slug.replace("-", " ").title(), "slug placeholder"


def _hashtags(copy_dir: Path | None) -> str:
    if copy_dir and (copy_dir / "hashtags.md").is_file():
        tags = re.findall(r"#\w+", (copy_dir / "hashtags.md").read_text(encoding="utf-8", errors="replace"))
        if tags:
            return " ".join(dict.fromkeys(tags))   # de-dup, keep order
    return ""


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #

def build_plan(
    asset: str,
    platforms: list[str],
    *,
    when: str = "now",
    caption_override: str | None = None,
    stagger_min: int = 0,
) -> dict:
    """Assemble the per-platform publish plan."""
    unknown = [p for p in platforms if p not in PLATFORMS]
    if unknown:
        raise PackageError(f"unknown platform(s): {unknown}. Known: {sorted(PLATFORMS)}")

    ctx = resolve_asset(asset)
    pool = _caption_pool(ctx["copy_dir"])
    tags = _hashtags(ctx["copy_dir"])

    if when == "now":
        base = datetime.now(timezone.utc)
        post_type = "now"
    else:
        base = datetime.fromisoformat(when)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        post_type = "schedule"

    entries = []
    for i, platform in enumerate(platforms):
        spec = PLATFORMS[platform]
        if caption_override:
            caption, source = caption_override, "override"
        else:
            caption, source = _pick_caption(platform, pool, ctx["title"], ctx["slug"])
        full = (caption + ("\n\n" + tags if tags else "")).strip()
        scheduled = base + timedelta(minutes=stagger_min * i)
        entries.append({
            "platform": platform,
            "provider": spec["provider"],
            "caption": _trim(full, spec["limit"]),
            "caption_source": source,
            "limit": spec["limit"],
            "media": str(ctx["media"]) if ctx["media"] else None,
            "scheduled_at": scheduled.isoformat(),
        })

    return {
        "asset": asset,
        "slug": ctx["slug"],
        "media": str(ctx["media"]) if ctx["media"] else None,
        "kind": ctx["kind"],
        "type": post_type,
        "when": base.isoformat(),
        "hashtags": tags,
        "entries": entries,
    }
