"""Official source verifier for the Certification Coach catalog.

The catalog is useful only if its references stay honest. This verifier checks
each certification URL against provider-specific official-domain allowlists,
fetches a small public page sample, records evidence terms, and stores the result
in local runtime cache. It never logs in, submits forms, pays, or opens exam
sessions.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from . import coach


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / "data" / "certification_coach"
SOURCE_CACHE_PATH = RUNTIME_DIR / "source_checks.json"

OFFICIAL_DOMAINS: dict[str, tuple[str, ...]] = {
    "Google Skillshop": ("skillshop.withgoogle.com", "skillshop.docebosaas.com", "support.google.com"),
    "Meta Blueprint": ("facebook.com", "business.facebook.com", "fbp.exceedlms.com", "certifications.facebookblueprint.com"),
    "HubSpot Academy": ("academy.hubspot.com", "hubspot.com"),
    "Semrush Academy": ("semrush.com", "www.semrush.com"),
    "LinkedIn Marketing Academy": ("training.marketing.linkedin.com", "business.linkedin.com", "linkedin.com"),
    "TikTok Academy": ("ads.tiktok.com", "tiktok.com"),
    "CXL Institute": ("cxl.com", "www.cxl.com"),
}

COMMON_TERMS = {
    "certification", "certified", "professional", "academy", "exam", "marketing",
    "google", "meta", "linkedin", "tiktok", "hubspot", "semrush", "cxl",
    "the", "and", "for", "with", "online",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").strip(".").casefold()


def _host_allowed(provider: str, url: str) -> bool:
    host = _host(url)
    for domain in OFFICIAL_DOMAINS.get(provider, ()):
        domain = domain.casefold()
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _title(html_text: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_text or "")
    if not match:
        return ""
    return _strip_html(match.group(1))[:180]


def _terms(cert: dict[str, Any]) -> list[str]:
    raw = f"{cert.get('title', '')} {cert.get('track', '')} {' '.join(cert.get('prep_topics', []))}"
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z0-9]+", raw.casefold()):
        if len(token) < 4 or token in COMMON_TERMS:
            continue
        if token not in terms:
            terms.append(token)
    return terms[:10]


def _fetch_url(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    req = Request(
        url,
        headers={
            "User-Agent": "Ramin-OS-Certification-Coach/0.1 source verifier",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.2",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - public catalog URLs only.
        raw = resp.read(250_000)
        charset = resp.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
        return {
            "ok": 200 <= int(resp.status) < 400,
            "status_code": int(resp.status),
            "final_url": resp.url,
            "title": _title(text),
            "plain_text": _strip_html(text)[:6000],
        }


def verify_certification(
    cert: dict[str, Any],
    *,
    fetcher: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Verify one catalog source and return a compact, cache-safe record."""
    fetcher = fetcher or (lambda url: _fetch_url(url))
    url = str(cert.get("source_url") or "")
    provider = str(cert.get("provider") or "")
    allowed = _host_allowed(provider, url)
    result: dict[str, Any] = {
        "cert_id": cert.get("id"),
        "title": cert.get("title"),
        "provider": provider,
        "url": url,
        "host": _host(url),
        "official_domain": allowed,
        "checked_at": _now(),
        "status_code": None,
        "page_title": "",
        "final_url": "",
        "matched_terms": [],
        "missing_terms": [],
        "verdict": "needs_review",
        "note": "",
    }

    if not allowed:
        result["verdict"] = "needs_review"
        result["note"] = "URL host is outside the provider allowlist."
        return result

    try:
        fetched = fetcher(url)
    except Exception as exc:  # noqa: BLE001
        result["verdict"] = "failed"
        result["note"] = f"Fetch failed: {exc}"
        return result

    text = f"{fetched.get('title', '')} {fetched.get('plain_text', '')}".casefold()
    terms = _terms(cert)
    matched = [term for term in terms if term in text]
    missing = [term for term in terms if term not in text]

    result.update(
        {
            "status_code": fetched.get("status_code"),
            "page_title": fetched.get("title", ""),
            "final_url": fetched.get("final_url", url),
            "matched_terms": matched,
            "missing_terms": missing[:8],
        }
    )

    if fetched.get("ok") and matched:
        result["verdict"] = "verified"
        result["note"] = "Official host is reachable and page content matches catalog terms."
    elif fetched.get("ok"):
        result["verdict"] = "reachable_official"
        result["note"] = "Official host is reachable, but the public HTML sample did not expose strong catalog terms."
    else:
        result["verdict"] = "failed"
        result["note"] = f"HTTP status {fetched.get('status_code')}."
    return result


def verify_catalog(*, fetcher: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    data = coach.catalog()
    checks = [
        verify_certification(cert, fetcher=fetcher)
        for cert in data.get("certifications", [])
    ]
    summary = {
        "checked_at": _now(),
        "total": len(checks),
        "verified": sum(1 for item in checks if item["verdict"] == "verified"),
        "reachable_official": sum(1 for item in checks if item["verdict"] == "reachable_official"),
        "needs_review": sum(1 for item in checks if item["verdict"] == "needs_review"),
        "failed": sum(1 for item in checks if item["verdict"] == "failed"),
    }
    payload = {"summary": summary, "checks": checks}
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_cached() -> dict[str, Any]:
    if not SOURCE_CACHE_PATH.exists():
        return {
            "summary": {
                "checked_at": "",
                "total": len(coach.catalog().get("certifications", [])),
                "verified": 0,
                "reachable_official": 0,
                "needs_review": 0,
                "failed": 0,
            },
            "checks": [],
            "cache_path": str(SOURCE_CACHE_PATH),
            "stale": True,
        }
    try:
        payload = json.loads(SOURCE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {"summary": {}, "checks": []}
    payload["cache_path"] = str(SOURCE_CACHE_PATH)
    payload["stale"] = _is_stale(payload.get("summary", {}).get("checked_at", ""))
    return payload


def _is_stale(checked_at: str, *, max_days: int = 14) -> bool:
    if not checked_at:
        return True
    try:
        checked = dt.datetime.strptime(checked_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return True
    return dt.datetime.now(dt.timezone.utc) - checked > dt.timedelta(days=max_days)
