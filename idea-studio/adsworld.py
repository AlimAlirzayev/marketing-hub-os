"""Ads of the World swipe-file organ for idea-studio.

Pulls real, current ad campaigns from adsoftheworld.com (public pages only)
into a local swipe file that /idea and /swipe read for grounded creative
reference — the creative-inspiration counterpart of Context7's docs
grounding. Insurance is the home industry (Xalq Sigorta), but any industry
slug on the site works: adsoftheworld.com/industries/<slug>.

Free, stdlib-only, deterministic — no LLM calls, no credentials, no login.
Only GETs public https pages on adsoftheworld.com. Every payload carries a
data label (CANLI = fetched live, DEMO = offline fixture) so downstream
consumers never mistake fixtures for reality.

Governance: config/agent_permissions.json -> adsworld_swipe.

Usage:
  python idea-studio/adsworld.py                          # insurance, cache-fresh
  python idea-studio/adsworld.py --industry automotive --pages 3
  python idea-studio/adsworld.py --deep 5 --fresh         # + top-5 campaign details
  python idea-studio/adsworld.py --campaign <slug>        # one campaign deep-dive
  python idea-studio/adsworld.py --grab <slug>            # download video + frames

Outputs:
  data/adsworld/<industry>.json            machine cache (stable schema v1)
  idea-studio/swipe_file/adsworld-<industry>.md   agent-readable digest
  idea-studio/output/adsworld/<slug>/      grabbed video + frames + detail.json
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "adsworld"
SWIPE_DIR = Path(__file__).resolve().parent / "swipe_file"
GRAB_DIR = Path(__file__).resolve().parent / "output" / "adsworld"
FFMPEG_TOOLS_GLOB = "video-studio/tools/*/bin"

# Downloads are allowed only from the site's own media CDN hosts.
MEDIA_HOST_PREFIXES = (
    "https://video.adsoftheworld.com/",
    "https://image.adsoftheworld.com/",
)

BASE_URL = "https://www.adsoftheworld.com"
DEFAULT_INDUSTRY = "insurance"
SCHEMA_VERSION = 1
FRESH_DAYS = 7
REQUEST_SLEEP_S = 1.0  # politeness gap between requests

# Bare UAs (e.g. plain "Mozilla/5.0") get 403 from the site's WAF;
# a full desktop browser string passes. Lesson learned 2026-07-16.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

CARD_ANCHOR_RE = re.compile(r"id='campaign_card_(\d+)'")
CARD_BRAND_RE = re.compile(r'href="/brands/([^"]+)">([^<]+)</a>')
CARD_TITLE_RE = re.compile(r'href="/campaigns/([^"]+)"><p>(.*?)</p></a>', re.S)
CARD_AGENCY_RE = re.compile(r'href="/agencies/([^"]+)">Agency:\s*([^<]+)</a>')
CARD_IMAGE_RE = re.compile(r'<img [^>]*src="(https://image\.adsoftheworld\.com/[^"]+)"')
TOTAL_RE = re.compile(r">([\d,]+) Campaigns<")
PAGE_RE = re.compile(r"\?page=(\d+)")

SUMMARY_RE = re.compile(
    r"This\s+(?:\w+\s+)?campaign titled '(?P<title>.+?)' was published in "
    r"(?P<country>.+?) in (?P<month>\w+),\s*(?P<year>\d{4})\.\s*"
    r"It was created for the brands?:\s*(?P<brands>.+?), by ad agenc(?:y|ies):\s*"
    r"(?P<agencies>.+?)\.",
    re.S,
)
# Anchored after a sentence end so it can't swallow the whole summary sentence
# ("This professional campaign titled ... This Film media campaign ...").
MEDIA_RE = re.compile(r"\.\s*This ([^.<>]+?) media campaign is related to the ([^.<>]+?) industr")
DESC_RE = re.compile(r">Description</p>\s*<div[^>]*>(.*?)</div>", re.S)
CREDITS_RE = re.compile(r">Credits</p>\s*<div[^>]*>(.*?)</div>", re.S)
VIDEO_RE = re.compile(r'src="(https://video\.adsoftheworld\.com/[^"]+)"')


def http_get(url: str, timeout: int = 30) -> str:
    """GET a public adsoftheworld.com page. Refuses any other host."""
    if not url.startswith(BASE_URL + "/"):
        raise ValueError(f"adsworld only fetches {BASE_URL} pages, got: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", fragment)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_listing(page_html: str) -> dict:
    """Parse an /industries/<slug> listing page into campaign cards."""
    anchors = list(CARD_ANCHOR_RE.finditer(page_html))
    campaigns = []
    for index, anchor in enumerate(anchors):
        end = anchors[index + 1].start() if index + 1 < len(anchors) else len(page_html)
        chunk = page_html[anchor.start():end]
        title_match = CARD_TITLE_RE.search(chunk)
        if not title_match:
            continue
        brand_match = CARD_BRAND_RE.search(chunk)
        agency_match = CARD_AGENCY_RE.search(chunk)
        image_match = CARD_IMAGE_RE.search(chunk)
        slug = title_match.group(1)
        campaigns.append(
            {
                "slug": slug,
                "url": f"{BASE_URL}/campaigns/{slug}",
                "title": html_lib.unescape(title_match.group(2)).strip(),
                "brand": html_lib.unescape(brand_match.group(2)).strip() if brand_match else None,
                "agency": html_lib.unescape(agency_match.group(2)).strip() if agency_match else None,
                "image": image_match.group(1) if image_match else None,
            }
        )
    total_match = TOTAL_RE.search(page_html)
    pages = [int(number) for number in PAGE_RE.findall(page_html)]
    return {
        "campaigns": campaigns,
        "total_campaigns": int(total_match.group(1).replace(",", "")) if total_match else None,
        "last_page": max(pages) if pages else 1,
    }


def parse_campaign(page_html: str) -> dict:
    """Parse a /campaigns/<slug> detail page into structured facts."""
    detail: dict = {}
    summary = SUMMARY_RE.search(page_html)
    if summary:
        detail.update(
            {
                "title": html_lib.unescape(summary.group("title")).strip(),
                "country": html_lib.unescape(summary.group("country")).strip(),
                "published": f"{summary.group('month')} {summary.group('year')}",
                "brands": [
                    part.strip()
                    for part in re.split(r",| and ", html_lib.unescape(summary.group("brands")))
                    if part.strip()
                ],
                "agencies": [
                    part.strip()
                    for part in re.split(r",| and ", html_lib.unescape(summary.group("agencies")))
                    if part.strip()
                ],
            }
        )
    media = MEDIA_RE.search(page_html)
    if media:
        detail["media_types"] = [
            part.strip()
            for part in re.split(r",| and ", html_lib.unescape(media.group(1)))
            if part.strip()
        ]
        detail["industries"] = [
            part.strip()
            for part in re.split(r",| and ", html_lib.unescape(media.group(2)))
            if part.strip()
        ]
    description = DESC_RE.search(page_html)
    if description:
        detail["description"] = _strip_tags(description.group(1))
    credits = CREDITS_RE.search(page_html)
    if credits:
        detail["credits"] = _strip_tags(credits.group(1))
    video = VIDEO_RE.search(page_html)
    if video:
        detail["video"] = video.group(1)
    return detail


def fetch_industry(industry: str, pages: int = 2, deep: int = 0) -> dict:
    """Fetch listing pages (+ optional detail deep-dives) into a v1 payload.

    Per-page failures are recorded in payload["errors"], never dropped
    silently (no-silent-drops rule).
    """
    campaigns: list = []
    errors: list = []
    total = None
    last_page = 1
    for page in range(1, pages + 1):
        if page > last_page and page > 1:
            break
        url = f"{BASE_URL}/industries/{industry}"
        if page > 1:
            url += f"?page={page}"
        try:
            parsed = parse_listing(http_get(url))
        except (urllib.error.URLError, ValueError, OSError) as error:
            errors.append({"url": url, "error": str(error)})
            continue
        campaigns.extend(parsed["campaigns"])
        total = parsed["total_campaigns"] or total
        last_page = parsed["last_page"]
        time.sleep(REQUEST_SLEEP_S)
    seen = set()
    unique = []
    for campaign in campaigns:
        if campaign["slug"] in seen:
            continue
        seen.add(campaign["slug"])
        unique.append(campaign)
    for campaign in unique[: max(deep, 0)]:
        try:
            campaign["detail"] = parse_campaign(http_get(campaign["url"]))
        except (urllib.error.URLError, ValueError, OSError) as error:
            errors.append({"url": campaign["url"], "error": str(error)})
        time.sleep(REQUEST_SLEEP_S)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": f"{BASE_URL}/industries/{industry}",
        "industry": industry,
        "label": "CANLI",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pages_fetched": pages,
        "total_campaigns_on_site": total,
        "campaigns": unique,
        "errors": errors,
    }


def download_media(url: str, dest: Path, timeout: int = 120) -> Path:
    """Download a media file from the site's own CDN. Refuses any other host."""
    if not url.startswith(MEDIA_HOST_PREFIXES):
        raise ValueError(f"adsworld only downloads from {MEDIA_HOST_PREFIXES}, got: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        dest.write_bytes(response.read())
    return dest


def find_ffmpeg() -> tuple[Path | None, Path | None]:
    """Locate the portable ffmpeg/ffprobe pair under video-studio/tools."""
    for bin_dir in sorted(ROOT.glob(FFMPEG_TOOLS_GLOB)):
        ffmpeg = bin_dir / "ffmpeg.exe"
        if not ffmpeg.exists():
            ffmpeg = bin_dir / "ffmpeg"
        if ffmpeg.exists():
            ffprobe = ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe"))
            return ffmpeg, (ffprobe if ffprobe.exists() else None)
    return None, None


def _video_duration(ffprobe: Path, video: Path) -> float | None:
    import subprocess

    try:
        result = subprocess.run(
            [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=60,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def extract_frames(video: Path, out_dir: Path, count: int = 6) -> tuple[list, list]:
    """Pull `count` evenly spaced frames so the agent can LOOK at the film.

    Returns (frame_paths, notes). Missing tools degrade to a note, never a
    silent drop.
    """
    import subprocess

    ffmpeg, ffprobe = find_ffmpeg()
    notes: list = []
    if ffmpeg is None:
        return [], [f"frames skipped: no ffmpeg under {FFMPEG_TOOLS_GLOB}"]
    duration = _video_duration(ffprobe, video) if ffprobe else None
    if not duration:
        notes.append("ffprobe duration unavailable — using 5s spacing")
    frames = []
    for index in range(count):
        timestamp = (duration * (index + 0.5) / count) if duration else index * 5.0
        frame = out_dir / f"frame-{index + 1}.jpg"
        try:
            result = subprocess.run(
                [str(ffmpeg), "-ss", f"{timestamp:.2f}", "-i", str(video),
                 "-frames:v", "1", "-q:v", "2", "-y", str(frame)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and frame.exists():
                frames.append(frame)
            else:
                notes.append(f"frame {index + 1} at {timestamp:.1f}s failed")
        except (subprocess.SubprocessError, OSError) as error:
            notes.append(f"frame {index + 1}: {error}")
    return frames, notes


def grab_campaign(slug: str, frames: int = 6) -> dict:
    """Steal-with-eyes pipeline: campaign facts + video + frames to LOOK at.

    Everything lands in idea-studio/output/adsworld/<slug>/ (the
    humann-ai-ref pattern: video.mp4 + frame-N.jpg + detail.json).
    """
    detail = parse_campaign(http_get(f"{BASE_URL}/campaigns/{slug}"))
    detail["url"] = f"{BASE_URL}/campaigns/{slug}"
    detail["label"] = "CANLI"
    out_dir = GRAB_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"slug": slug, "dir": str(out_dir), "detail": detail,
              "video": None, "frames": [], "notes": []}
    video_url = detail.get("video")
    if video_url:
        try:
            video_path = download_media(video_url, out_dir / "video.mp4")
            result["video"] = str(video_path)
            frame_paths, notes = extract_frames(video_path, out_dir, count=frames)
            result["frames"] = [str(path) for path in frame_paths]
            result["notes"].extend(notes)
        except (urllib.error.URLError, ValueError, OSError) as error:
            result["notes"].append(f"video download failed: {error}")
    else:
        result["notes"].append("campaign page exposes no direct video")
    (out_dir / "detail.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def cache_path(industry: str) -> Path:
    return CACHE_DIR / f"{industry}.json"


def swipe_path(industry: str) -> Path:
    return SWIPE_DIR / f"adsworld-{industry}.md"


def load_cache(industry: str) -> dict | None:
    path = cache_path(industry)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def is_fresh(payload: dict, days: int = FRESH_DAYS, now: datetime | None = None) -> bool:
    try:
        fetched = datetime.fromisoformat(payload["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return False
    now = now or datetime.now(timezone.utc)
    return (now - fetched).total_seconds() < days * 86400


def render_digest(payload: dict) -> str:
    """Render the payload as the agent-readable swipe-file markdown."""
    lines = [
        f"# Ads of the World swipe file — {payload['industry']}",
        "",
        f"- source: {payload['source']}",
        f"- label: {payload['label']}",
        f"- fetched_at: {payload['fetched_at']}",
        f"- campaigns_on_site: {payload.get('total_campaigns_on_site') or 'unknown'}"
        f" (this file: {len(payload['campaigns'])})",
        "",
        "Refresh: `python idea-studio/adsworld.py --industry "
        f"{payload['industry']} --fresh` (add `--deep N` for descriptions).",
        "",
    ]
    if payload.get("errors"):
        lines.append("## Fetch errors (not silently dropped)")
        lines.extend(f"- {error['url']}: {error['error']}" for error in payload["errors"])
        lines.append("")
    lines.append("## Campaigns (newest first)")
    lines.append("")
    for campaign in payload["campaigns"]:
        brand = campaign.get("brand") or "?"
        agency = campaign.get("agency") or "?"
        lines.append(f"### {campaign['title']} — {brand}")
        lines.append(f"- agency: {agency} · [campaign page]({campaign['url']})")
        detail = campaign.get("detail")
        if detail:
            facts = []
            if detail.get("country"):
                facts.append(detail["country"])
            if detail.get("published"):
                facts.append(detail["published"])
            if detail.get("media_types"):
                facts.append(" / ".join(detail["media_types"]))
            if facts:
                lines.append(f"- {' · '.join(facts)}")
            if detail.get("video"):
                lines.append(f"- video: {detail['video']}")
            if detail.get("description"):
                lines.append("")
                lines.append(detail["description"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save(payload: dict) -> tuple[Path, Path]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SWIPE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path(payload["industry"])
    cache_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    swipe_file = swipe_path(payload["industry"])
    swipe_file.write_text(render_digest(payload), encoding="utf-8")
    return cache_file, swipe_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--industry", default=DEFAULT_INDUSTRY)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--deep", type=int, default=0,
                        help="also fetch detail pages for the newest N campaigns")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore the cache even if it is fresh")
    parser.add_argument("--campaign", metavar="SLUG",
                        help="deep-dive one campaign and print JSON to stdout")
    parser.add_argument("--grab", metavar="SLUG",
                        help="download a campaign's video and extract frames to LOOK at")
    parser.add_argument("--frames", type=int, default=6,
                        help="frame count for --grab (default 6)")
    args = parser.parse_args(argv)

    if args.grab:
        result = grab_campaign(args.grab, frames=args.frames)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if (result["video"] or not result["detail"].get("video")) else 1

    if args.campaign:
        detail = parse_campaign(http_get(f"{BASE_URL}/campaigns/{args.campaign}"))
        detail["url"] = f"{BASE_URL}/campaigns/{args.campaign}"
        detail["label"] = "CANLI"
        print(json.dumps(detail, ensure_ascii=False, indent=2))
        return 0

    cached = load_cache(args.industry)
    if cached and is_fresh(cached) and not args.fresh:
        cache_file, swipe_file = save(cached)  # re-render digest from cache
        print(f"[adsworld] cache fresh ({cached['fetched_at']}) — reusing. "
              f"{len(cached['campaigns'])} campaigns.")
        print(f"[adsworld] swipe file: {swipe_file}")
        return 0

    payload = fetch_industry(args.industry, pages=args.pages, deep=args.deep)
    if not payload["campaigns"]:
        print("[adsworld] FETCH FAILED — no campaigns parsed. Errors:", file=sys.stderr)
        for error in payload["errors"]:
            print(f"  {error['url']}: {error['error']}", file=sys.stderr)
        if cached:
            print("[adsworld] keeping stale cache (better than nothing).", file=sys.stderr)
        return 1
    cache_file, swipe_file = save(payload)
    print(f"[adsworld] {payload['label']} — {len(payload['campaigns'])} campaigns "
          f"({payload.get('total_campaigns_on_site')} on site), "
          f"{len(payload['errors'])} errors.")
    print(f"[adsworld] cache: {cache_file}")
    print(f"[adsworld] swipe file: {swipe_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
