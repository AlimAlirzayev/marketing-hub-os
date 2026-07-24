"""gateway/social.py — the system's social-content reading hand.

WHY THIS EXISTS (2026-07-22 audit). When the operator drops a social link
(Instagram reel/post/profile, TikTok, YouTube, Facebook, X) — almost always to
say "make one like THIS for <brand>" — the old path routed the bare URL into the
headless-browser lane, whose Claude planner prompt ("you are Xalq Insurance
Digital OS, you have NO tools, output only JSON") collides head-on with real
Claude Code's own identity. Claude read it as a persona/injection override and
REFUSED, and the English refusal lecture was delivered to the operator verbatim
(jobs 165/167/168, all Instagram links the operator sent 2026-07-22).

This lane replaces the browser for social URLs. It READS what is reliably
readable WITHOUT login — Open Graph metadata (author, caption, likes/comments,
date, thumbnail) for Instagram/TikTok/Facebook/X, plus the transcript for
YouTube — and hands that REAL reference to the quality brain (gateway.brain) to
produce the operator's deliverable in Azerbaijani, grounded strictly in what was
extracted. No persona override, no JSON-planner role, no headless browser, and
never a claim to have watched raw video frames it did not see.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from . import brain

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# host substring -> human platform label
_PLATFORMS = {
    "instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "facebook.com": "Facebook",
    "fb.watch": "Facebook",
    "x.com": "X",
    "twitter.com": "X",
}

_URL_RE = re.compile(r"https?://[^\s<>()\]]+", re.IGNORECASE)
_MAX_URLS = 3
_FETCH_TIMEOUT = 15


# --- detection ---------------------------------------------------------------
def find_urls(text: str) -> list[str]:
    """Every http(s) URL in the text, trailing punctuation trimmed."""
    return [u.rstrip(".,;)") for u in _URL_RE.findall(text or "")]


def platform_of(url: str) -> str | None:
    low = (url or "").lower()
    for host, label in _PLATFORMS.items():
        if host in low:
            return label
    return None


def social_urls(text: str) -> list[str]:
    return [u for u in find_urls(text) if platform_of(u)]


def is_social_url(text: str) -> bool:
    """True when the text carries at least one recognised social-media link."""
    return bool(social_urls(text))


# --- low-level fetch (patched out in tests) ----------------------------------
def _fetch(url: str, timeout: int = _FETCH_TIMEOUT) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept-Language": "en,az;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def _meta(page: str, prop: str) -> str:
    """Value of an <meta property=|name= "prop"> tag, attribute order tolerant."""
    esc = re.escape(prop)
    for pat in (
        r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)["\']' % esc,
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']' % esc,
    ):
        m = re.search(pat, page, re.IGNORECASE)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


# --- per-platform extraction -------------------------------------------------
def _youtube_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def _add_youtube_transcript(ref: dict, url: str) -> None:
    """Attach the YouTube transcript (the real content) to ref, best-effort."""
    vid = _youtube_id(url)
    if not vid:
        return
    try:  # version-tolerant call across youtube_transcript_api releases
        from youtube_transcript_api import YouTubeTranscriptApi as _YT
        if hasattr(_YT, "get_transcript"):
            segs = _YT.get_transcript(vid, languages=["az", "en", "ru", "tr"])
        else:  # newer API: instance .fetch()
            segs = [{"text": s.text} for s in _YT().fetch(vid)]
        joined = " ".join(s.get("text", "") for s in segs).strip()
        if joined:
            ref["transcript"] = joined[:4000]
    except Exception:  # noqa: BLE001 — caption/title still useful without it
        pass


def _extract_youtube(url: str) -> dict:
    ref: dict = {"platform": "YouTube", "url": url}
    try:  # oEmbed gives title + channel with no key
        o = json.loads(_fetch("https://www.youtube.com/oembed?format=json&url="
                              + urllib.parse.quote(url, safe="")))
        ref["title"] = o.get("title", "")
        ref["author"] = o.get("author_name", "")
    except Exception as exc:  # noqa: BLE001
        ref["error"] = f"{type(exc).__name__}: {exc}"
    _add_youtube_transcript(ref, url)
    return ref


_IG_CODE_RE = re.compile(r"/(?:reel|reels|p|tv)/([^/?#]+)")


def _extract_og(url: str, platform: str) -> dict:
    page = _fetch(url)
    ref = {
        "platform": platform,
        "url": url,
        "title": _meta(page, "og:title"),
        "caption": _meta(page, "og:description") or _meta(page, "description"),
        "thumbnail": _meta(page, "og:image"),
        "kind": _meta(page, "og:type"),
    }
    # Instagram frequently login-walls the main page from a datacenter IP. The
    # public /embed/captioned/ view often still exposes the caption — try it as a
    # cheap second chance. (Best-effort: IG can hard-block the IP entirely, in
    # which case caption stays empty and the brain is told it could not be read.)
    if platform == "Instagram" and not ref["caption"]:
        m = _IG_CODE_RE.search(url)
        if m:
            try:
                emb = _fetch(f"https://www.instagram.com/reel/{m.group(1)}/embed/captioned/")
                cap = _meta(emb, "og:description")
                if not cap:
                    cm = re.search(r'class="Caption"[^>]*>(.*?)</div>', emb, re.DOTALL)
                    if cm:
                        cap = html.unescape(re.sub(r"<[^>]+>", " ", cm.group(1))).strip()
                if cap:
                    ref["caption"] = cap
            except Exception:  # noqa: BLE001 — honest empty caption is fine
                pass
    return ref


# Instagram/TikTok serve a login wall to datacenter IPs, so the only reliable
# read is an authenticated cookie jar (a BURNER account, exported Netscape
# cookies.txt). The operator places it locally at
# data/private_context/ig_cookies.txt, or points IG_COOKIES_FILE at it. Telegram
# secret/file couriers are permanently blocked. First present wins; yt-dlp then
# reads reels properly.
# Without any, the lane degrades honestly (says it could not open the link).
_ROOT = Path(__file__).resolve().parent.parent


def _ig_cookie_candidates() -> list[str]:
    cands = []
    env = os.getenv("IG_COOKIES_FILE")
    if env:
        cands.append(env)
    cands.append(str(_ROOT / "data" / "private_context" / "ig_cookies.txt"))
    return cands


def _ig_cookies_path() -> str | None:
    """First present cookie jar, or None."""
    for c in _ig_cookie_candidates():
        if os.path.exists(c):
            return c
    return None


def ig_status() -> str:
    """One-line readiness report the operator can check after dropping cookies."""
    p = _ig_cookies_path()
    if p:
        return f"✅ IG cookies aktiv: {p} — reel-lər oxunacaq."
    return ("⚠️ IG cookies yoxdur. Instagram reel-lərini oxumaq üçün BURNER hesabın "
            "cookies.txt faylını bu maşında lokal olaraq "
            "data/private_context/ig_cookies.txt yoluna qoy.")


class _SilentLogger:
    """Swallow yt-dlp's own logging (it prints ERROR lines to stderr even with
    quiet=True) so a blocked Instagram fetch does not spam the journal."""
    def debug(self, m): pass
    def info(self, m): pass
    def warning(self, m): pass
    def error(self, m): pass


def _ytdlp_opts(url: str) -> dict:
    opts = {"quiet": True, "skip_download": True, "no_warnings": True,
            "socket_timeout": _FETCH_TIMEOUT, "extractor_retries": 1,
            "logger": _SilentLogger()}
    low = url.lower()
    ck = _ig_cookies_path()
    if ck and ("instagram.com" in low or "tiktok.com" in low):
        opts["cookiefile"] = ck
    return opts


def _extract_ytdlp(url: str, platform: str) -> dict | None:
    """Rich, uniform read via yt-dlp — author, title, caption, engagement across
    every platform, and the reliable path for Instagram/TikTok WHEN a cookie jar
    is present. Returns None (so the caller falls back to OG/oEmbed) when yt-dlp
    can't read it — e.g. Instagram from a datacenter IP with no cookies."""
    try:
        import yt_dlp
    except Exception:  # noqa: BLE001 — library absent -> fall back
        return None
    try:
        with yt_dlp.YoutubeDL(_ytdlp_opts(url)) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:  # noqa: BLE001 — blocked/needs-cookies -> fall back honestly
        return None
    if not info:
        return None
    ref = {
        "platform": platform,
        "url": url,
        "author": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "",
        "title": (info.get("title") or "").strip(),
        "caption": (info.get("description") or "").strip(),
        "thumbnail": info.get("thumbnail") or "",
    }
    bits = []
    for key, label in (("view_count", "views"), ("like_count", "likes"),
                       ("comment_count", "comments"), ("duration", "sec")):
        if info.get(key):
            bits.append(f"{info[key]:,} {label}")
    if bits:
        ref["engagement"] = ", ".join(bits)
    # Only trust it if it actually carries readable content.
    return ref if (ref["caption"] or ref["title"]) else None


def extract(url: str) -> dict:
    """Best-effort structured reference for one social URL. Never raises.

    Order: yt-dlp first (richest + uniform + cookie-aware for IG/TikTok), then the
    platform-specific OG/oEmbed/transcript fallback so nothing regresses."""
    platform = platform_of(url) or "Web"
    try:
        rich = _extract_ytdlp(url, platform)
        if rich:
            if platform == "YouTube" and not rich.get("transcript"):
                _add_youtube_transcript(rich, url)  # transcript is the real content
            return rich
        if platform == "YouTube":
            return _extract_youtube(url)
        return _extract_og(url, platform)
    except Exception as exc:  # noqa: BLE001
        return {"platform": platform, "url": url,
                "error": f"{type(exc).__name__}: {exc}"}


def _render_reference(refs: list[dict]) -> str:
    """Compact, honest reference block for the brain prompt."""
    out: list[str] = []
    for i, r in enumerate(refs, 1):
        lines = [f"[{i}] {r.get('platform', 'Web')} — {r.get('url', '')}"]
        if r.get("title"):
            lines.append(f"    title/author: {r['title']}")
        if r.get("author"):
            lines.append(f"    author: {r['author']}")
        if r.get("caption"):
            lines.append(f"    caption/description: {r['caption']}")
        if r.get("engagement"):
            lines.append(f"    engagement: {r['engagement']}")
        if r.get("transcript"):
            lines.append(f"    transcript (excerpt): {r['transcript']}")
        if r.get("thumbnail"):
            lines.append(f"    thumbnail image: {r['thumbnail']}")
        if not _has_content(r):
            reason = r.get("error") or "blocked / not public"
            lines.append(f"    (could NOT be read: {reason} — its contents are "
                         "unknown to you; do not invent them)")
        out.append("\n".join(lines))
    return "\n\n".join(out)


def _has_content(ref: dict) -> bool:
    """True when the reference carries something the brain can actually ground on."""
    return bool(ref.get("caption") or ref.get("title") or ref.get("transcript"))


# --- the deliverable ---------------------------------------------------------
_SYSTEM = (
    "You are Ramin-OS, the operator's marketing co-pilot, replying on Telegram. "
    "The operator has shared one or more social-media links. A separate reader has "
    "already fetched what is publicly readable for each — author, caption, "
    "engagement, thumbnail, and (for YouTube) the transcript — and it is given to "
    "you below as REFERENCE. Ground everything you say strictly in that reference: "
    "do NOT claim to have watched the video frame by frame, and do NOT invent "
    "details that are not in the reference. If a link could not be read, say so "
    "plainly in one line and work from whatever IS available.\n\n"
    "Then do exactly what the operator asked. If the operator gave an instruction "
    "(e.g. 'make one like this for <brand>'), deliver the concrete adapted "
    "result — read the reference's format/hook/structure and produce the brand's "
    "version: a short concept with hook, scene beats, on-screen text and a "
    "caption. If the operator sent only the link with no instruction, give a "
    "short, useful read of what it is (format, hook, why it might matter for our "
    "marketing) and offer one concrete next step. Reply in Azerbaijani, like a "
    "sharp senior teammate: concrete and warm, no corporate filler, no lecturing, "
    "and NEVER a refusal about 'personas' or 'surveillance'. Keep it tight — this "
    "is a chat message, not an essay. Output clean Markdown."
)

_BARE_HINT = (
    "\n\n(The operator sent only the link, no other words. Give the short read + "
    "one concrete next step described above.)"
)


def _instruction(task: str) -> str:
    """The operator's words with the URLs stripped out; '' if it was a bare link."""
    stripped = _URL_RE.sub(" ", task or "")
    return stripped if len(re.sub(r"[^0-9A-Za-zƏəÜüÖöĞğİıŞşÇç]", "", stripped)) >= 3 else ""


def handle(task: str, *, prefer: str = "claude") -> tuple[str, str]:
    """Turn a message carrying social link(s) into a grounded AZ deliverable.

    Returns (text, label). Never raises — a fetch/brain failure still yields an
    honest Azerbaijani message rather than an English refusal or a stack trace.
    """
    urls = social_urls(task)[:_MAX_URLS]
    refs = [extract(u) for u in urls]
    reference = _render_reference(refs) or "(no readable reference)"
    instruction = _instruction(task)

    prompt = f"REFERENCE (already fetched for you):\n{reference}\n\n"
    if instruction.strip():
        prompt += f"OPERATOR INSTRUCTION:\n{instruction.strip()}"
    else:
        prompt += "OPERATOR INSTRUCTION: (none — just the link)"
    if not any(_has_content(r) for r in refs):
        # Blocked / private: the model saw nothing. Force it to say so instead of
        # quietly producing a generic result as if it had watched the reference.
        prompt += ("\n\nNOTE: none of the links could be read (blocked or not "
                   "public) — you did NOT see their contents. OPEN by telling the "
                   "operator plainly that you couldn't open the link, then either "
                   "ask them to paste the caption/text or offer a clearly-labelled "
                   "GENERIC idea. Never imply you saw the reference.")
    system = _SYSTEM + ("" if instruction.strip() else _BARE_HINT)

    text, model = brain.answer(prompt, system=system, prefer=prefer, timeout=120)
    if not text or not text.strip() or text.startswith("[brain error]"):
        # Honest fallback: hand back the raw reference rather than nothing.
        note = "\n".join(
            f"- {r.get('platform')}: {r.get('caption') or r.get('title') or r.get('error') or r.get('url')}"
            for r in refs)
        text = ("Linki oxudum, amma beyin cavabı alınmadı. Oxuya bildiyim:\n"
                + note + "\n\nNə edim bununla — buna bənzər konsept hazırlayım?")
        model = "none"
    return text.strip(), f"social:{model}"
