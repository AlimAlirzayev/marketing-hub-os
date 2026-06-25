"""Public web discovery connector — free, no credentials, no ban risk.

Attacks the discovery ceiling that blind platform search leaves thin. It mines
public "best Azerbaijani creators" listicles/articles via a keyless search
(DuckDuckGo Lite) and an LLM extractor, turning the brief into real, named
creator leads. These leads are not enriched (no follower/engagement metrics), so
they surface as research leads whose handles can be fed to the enrichment
connectors (YouTube / Instagram) for verification.

Only creators explicitly named on a real page are returned — nothing invented.
"""

from __future__ import annotations

import re

import httpx

import config
import llm
from models import CampaignBrief, EvidenceItem, InfluencerCandidate, SourceStatus

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_SKIP_DOMAINS = (
    "duckduckgo", "google.", "bing.com", "pinterest", "twitter", "x.com",
    "tiktok.com", "facebook.com/sharer",
)

_SYSTEM = """You extract Azerbaijani influencer/creator leads from a web page's text.
Return strict JSON: {"creators":[{"name":"...","handle":"...","platform":"instagram|youtube|tiktok|web","note":"..."}]}.
Rules:
- Only creators explicitly named on the page. Never invent creators or handles.
- handle: the @username without '@' if the page states it, else "".
- note: one short Azerbaijani phrase describing who they are.
- Skip the publication/site itself; return only the individual creators it lists."""


def available() -> bool:
    # Extraction needs an LLM; without one we degrade honestly rather than guess.
    return (not config.DISABLE_WEB) and llm.available()


def _search(query: str, limit: int = 5) -> list[str]:
    r = httpx.post("https://lite.duckduckgo.com/lite/", data={"q": query},
                   headers=_UA, timeout=20, follow_redirects=True)
    r.raise_for_status()
    out: list[str] = []
    for link in re.findall(r'href="(https?://[^"]+)"', r.text):
        if any(d in link for d in _SKIP_DOMAINS):
            continue
        if link not in out:
            out.append(link)
        if len(out) >= limit:
            break
    return out


def _fetch_text(url: str) -> str:
    r = httpx.get(url, headers=_UA, timeout=20, follow_redirects=True)
    r.raise_for_status()
    html = r.text
    html = re.sub(r"(?is)<(script|style|nav|footer|header|svg).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text)[:6000]


def _queries(brief: CampaignBrief) -> list[str]:
    arch = (brief.creator_archetypes or ["blogger"])[0].strip()
    topic = (brief.must_have_topics or [""])[0].strip()
    return list(dict.fromkeys([
        f"azərbaycanlı {arch} siyahısı",
        f"best azerbaijani {topic or 'travel'} bloggers",
        f"azərbaycan {topic} bloger izlə",
    ]))[:3]


def _handle(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._]", "", str(value or "").lstrip("@")).lower()


def collect(
    brief: CampaignBrief,
    *,
    seed_handles: list[str] | None = None,
    deep_comments: bool = True,
) -> tuple[list[InfluencerCandidate], list[SourceStatus], int]:
    statuses: list[SourceStatus] = []
    if not available():
        statuses.append(SourceStatus("web", "skipped", "LLM açarı yoxdur və ya web söndürülüb; extraction üçün lazımdır"))
        return [], statuses, 0

    urls: list[str] = []
    for q in _queries(brief):
        try:
            found = _search(q)
            urls.extend(found)
            statuses.append(SourceStatus("web/search", "ok" if found else "empty", f"{len(found)} nəticə: {q}"))
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus("web/search", f"error:{type(exc).__name__}", str(exc)[:120]))
    urls = list(dict.fromkeys(urls))[: config.WEB_MAX_PAGES]

    candidates: dict[str, InfluencerCandidate] = {}
    seen = 0
    for url in urls:
        try:
            text = _fetch_text(url)
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus("web/fetch", f"error:{type(exc).__name__}", url[:80]))
            continue
        data = llm.complete_json(f"URL: {url}\n\nPAGE TEXT:\n{text}", system=_SYSTEM, default=None)
        creators = data.get("creators") if isinstance(data, dict) else None
        if not isinstance(creators, list) or not creators:
            statuses.append(SourceStatus("web/extract", "empty", url[:60]))
            continue
        n = 0
        for cr in creators:
            if not isinstance(cr, dict):
                continue
            name = str(cr.get("name") or "").strip()
            handle = _handle(cr.get("handle"))
            key = handle or name.lower()
            if not key:
                continue
            platform = str(cr.get("platform") or "web").strip().lower()
            note = str(cr.get("note") or "").strip()
            c = candidates.get(key) or InfluencerCandidate(handle=handle or key, platform="web", name=name)
            c.bio = c.bio or note
            if platform and platform not in c.categories:
                c.categories.append(platform)
            c.evidence.append(EvidenceItem(
                kind="mention", url=url, source="web",
                text=(f"{note} — mənbə platforması: {platform}" if note else f"platform: {platform}"),
                reason="Public web siyahısında qeyd olunub",
            ))
            candidates[key] = c
            n += 1
        seen += n
        statuses.append(SourceStatus("web/extract", "ok" if n else "empty", f"{n} creator: {url.split('//')[-1][:34]}"))

    return list(candidates.values()), statuses, seen
