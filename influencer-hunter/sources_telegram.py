"""Telegram public-channel connector — free, anonymous, no ban risk.

Reads public channel previews at ``t.me/s/<channel>`` (title, subscriber count,
description, recent posts + view counts). No login, no MTProto session, no phone
number — the public web preview is anonymous and rate-friendly, unlike Telethon
selfbots which are against ToS and get accounts flagged.

Discovery: keyless web search for Azerbaijani channel lists, plus seed handles.
Limitation: only channels that expose a public web preview are readable, and the
preview has no per-comment data (posts + views only).
"""

from __future__ import annotations

import re

import httpx

import config
import sources_web
from models import CampaignBrief, EvidenceItem, InfluencerCandidate, SourceStatus

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_RESERVED = {
    "s", "share", "joinchat", "addstickers", "proxy", "setlanguage", "iv", "c", "bot",
    "login", "username", "usernames", "previews", "blog", "contact", "faq", "apps", "tour",
}


def available() -> bool:
    return not config.DISABLE_TELEGRAM


def _as_int(text: str) -> int | None:
    t = str(text or "").strip().lower().replace(" ", "").replace(",", "").replace(" ", "").replace("\xa0", "")
    mult = 1
    if t.endswith("k"):
        mult, t = 1_000, t[:-1]
    elif t.endswith("m"):
        mult, t = 1_000_000, t[:-1]
    try:
        return int(float(re.sub(r"[^0-9.]", "", t)) * mult)
    except ValueError:
        return None


def _strip(html: str) -> str:
    html = re.sub(r"(?is)<br\s*/?>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


def _extract_usernames(text: str) -> list[str]:
    out: list[str] = []
    for u in re.findall(r"t\.me/(?:s/)?@?([A-Za-z0-9_]{4,32})", text):
        ul = u.lower()
        if ul in _RESERVED or ul in out:
            continue
        out.append(u)
    return out


def _scrape_channel(username: str) -> InfluencerCandidate | None:
    try:
        r = httpx.get(f"https://t.me/s/{username}", headers=_UA, timeout=20, follow_redirects=True)
    except Exception:  # noqa: BLE001
        return None
    if r.status_code != 200 or "tgme_channel_info" not in r.text:
        return None
    return _parse_channel(username, r.text)


def _parse_channel(username: str, h: str) -> InfluencerCandidate | None:
    if "tgme_channel_info" not in h:
        return None
    title_m = re.search(r"tgme_channel_info_header_title.*?>(.*?)</div>", h, re.S)
    title = _strip(title_m.group(1)) if title_m else username
    desc_m = re.search(r'tgme_channel_info_description[^>]*>(.*?)</div>', h, re.S)
    bio = _strip(desc_m.group(1)) if desc_m else ""

    followers = None
    for value, ctype in re.findall(r'tgme_channel_info_counter.*?counter_value">([^<]+)</span>.*?counter_type">([^<]+)</span>', h, re.S):
        if "subscriber" in ctype.lower():
            followers = _as_int(value)
            break

    c = InfluencerCandidate(
        handle=username.lower(), name=title, platform="telegram",
        url=f"https://t.me/{username}", bio=bio[:1500], followers=followers,
    )
    texts = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>\s*<div class="tgme_widget_message_footer', h, re.S)
    if not texts:
        texts = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', h, re.S)
    views = re.findall(r'tgme_widget_message_views">([^<]+)<', h)
    for i, raw in enumerate(texts[: config.TG_MAX_POSTS]):
        text = _strip(raw)
        if not text:
            continue
        v = _as_int(views[i]) if i < len(views) else 0
        c.evidence.append(EvidenceItem(
            kind="post", source="telegram", text=text[:2000], author=username.lower(),
            metrics={"likes": 0, "comments": 0, "video_views": v or 0},
            reason="Telegram public post",
        ))
    return c


def _merge_metrics(c: InfluencerCandidate) -> None:
    posts = [e for e in c.evidence if e.kind == "post"]
    if not posts:
        return
    c.avg_views = sum(e.metrics.get("video_views", 0) for e in posts) / len(posts)
    if c.followers:
        c.engagement_rate = c.avg_views / c.followers  # reach ratio (views/subscribers)


def _queries(brief: CampaignBrief) -> list[str]:
    arch = (brief.creator_archetypes or ["blogger"])[0].strip()
    topic = (brief.must_have_topics or [""])[0].strip()
    return list(dict.fromkeys([
        f"azərbaycan {topic or arch} telegram kanal",
        f"azerbaijan {topic or 'travel'} telegram channel",
        f"azərbaycanlı {arch} telegram",
    ]))[:3]


def collect(
    brief: CampaignBrief,
    *,
    seed_handles: list[str] | None = None,
    deep_comments: bool = True,
) -> tuple[list[InfluencerCandidate], list[SourceStatus], int]:
    statuses: list[SourceStatus] = []
    if not available():
        statuses.append(SourceStatus("telegram", "skipped", "Telegram connector söndürülüb"))
        return [], statuses, 0

    usernames: list[str] = [u.lstrip("@") for u in (seed_handles or []) if u.strip()]

    for q in _queries(brief):
        try:
            links = sources_web._search(q, limit=6)
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus("telegram/search", f"error:{type(exc).__name__}", str(exc)[:120]))
            continue
        direct = _extract_usernames(" ".join(links))
        from_pages: list[str] = []
        for link in links[:2]:
            if "t.me/" in link:
                continue
            try:
                from_pages.extend(_extract_usernames(httpx.get(link, headers=_UA, timeout=15, follow_redirects=True).text))
            except Exception:  # noqa: BLE001
                pass
        found = list(dict.fromkeys([*direct, *from_pages]))
        usernames.extend(found)
        statuses.append(SourceStatus("telegram/search", "ok" if found else "empty", f"{len(found)} kanal: {q}"))

    usernames = list(dict.fromkeys(usernames))[: config.TG_MAX_CHANNELS]
    if not usernames:
        statuses.append(SourceStatus("telegram", "empty", "Uyğun public kanal tapılmadı"))
        return [], statuses, 0

    candidates: list[InfluencerCandidate] = []
    seen = 0
    for u in usernames:
        c = _scrape_channel(u)
        if c:
            _merge_metrics(c)
            candidates.append(c)
            seen += 1 + len([e for e in c.evidence if e.kind == "post"])
    statuses.append(SourceStatus("telegram/channels", "ok" if candidates else "empty", f"{len(candidates)} public kanal oxundu"))
    return candidates, statuses, seen
