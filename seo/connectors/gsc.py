"""Google Search Console connector — the own-site ground truth.

Everything else in this engine infers; GSC *measures*. It returns the real
clicks, impressions, CTR and average position for your site's queries and pages,
straight from Google — the signal that closes the reinforcement loop (seo/
reinforce.py): after we publish, GSC tells us what actually ranked, and the
system learns from it.

Auth mirrors ga4-studio's live connector exactly: a service-account JSON minted
into an OAuth token (webmasters.readonly scope), then plain `requests` against
the Search Analytics API — no grpc/SDK, installs on the locked-down machine.

Demo mode (no creds) returns deterministic, realistic synthetic data so the
whole loop is testable and the UI works with zero setup. Live vs demo is always
labelled; nothing is silently faked.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import quote

import requests

from .. import config

_creds = None
_session = requests.Session()


class GSCNotConfigured(RuntimeError):
    pass


@dataclass
class GSCRow:
    key: str                 # the dimension value (query text, or page URL, or date)
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0         # 0..1
    position: float = 0.0    # average, 1 = top


@dataclass
class GSCReport:
    site: str
    start: str
    end: str
    dimension: str
    mode: str                # "live" | "demo"
    rows: list[GSCRow] = field(default_factory=list)
    error: str = ""

    @property
    def total_clicks(self) -> int:
        return sum(r.clicks for r in self.rows)

    @property
    def total_impressions(self) -> int:
        return sum(r.impressions for r in self.rows)


# --------------------------------------------------------------------------- #
# Auth (live)
# --------------------------------------------------------------------------- #

def _token() -> str:
    global _creds
    if not (config.GSC_SITE_URL and config.GSC_SERVICE_ACCOUNT_FILE):
        raise GSCNotConfigured("GSC_SITE_URL və service-account faylı lazımdır.")
    if _creds is None:
        try:
            from google.oauth2 import service_account
        except ImportError as exc:
            raise GSCNotConfigured(
                "Canlı rejim üçün 'google-auth' lazımdır: "
                ".venv\\Scripts\\python.exe -m pip install google-auth") from exc
        _creds = service_account.Credentials.from_service_account_file(
            config.GSC_SERVICE_ACCOUNT_FILE, scopes=[config.GSC_SCOPE])
    if not _creds.valid:
        from google.auth.transport.requests import Request
        _creds.refresh(Request())
    return _creds.token


# --------------------------------------------------------------------------- #
# Query
# --------------------------------------------------------------------------- #

def _default_range(days: int) -> tuple[str, str]:
    # GSC data lags ~2-3 days; end at day-3 for a stable window.
    end = date.today() - timedelta(days=3)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def query(site: str | None = None, *, days: int = 28, dimension: str = "query",
          row_limit: int = 25, page_filter: str | None = None,
          start: str | None = None, end: str | None = None) -> GSCReport:
    """Search Analytics query. Live when configured, else deterministic demo.
    Never raises for the caller — failures come back on report.error."""
    site = site or config.GSC_SITE_URL or "sc-domain:example.az"
    if not start or not end:
        start, end = _default_range(days)
    mode = config.gsc_mode()

    if mode == "demo":
        return _demo_report(site, start, end, dimension, row_limit, page_filter)

    body: dict = {
        "startDate": start, "endDate": end,
        "dimensions": [dimension], "rowLimit": row_limit,
    }
    if page_filter:
        body["dimensionFilterGroups"] = [{"filters": [
            {"dimension": "page", "operator": "equals", "expression": page_filter}]}]
    url = f"{config.GSC_API}/sites/{quote(site, safe='')}/searchAnalytics/query"
    try:
        r = _session.post(url, headers={"Authorization": f"Bearer {_token()}"},
                          json=body, timeout=30)
    except (requests.RequestException, GSCNotConfigured) as e:
        return GSCReport(site, start, end, dimension, "live", error=str(e)[:200])
    if not r.ok:
        msg = ""
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = (r.text or "")[:200]
        return GSCReport(site, start, end, dimension, "live", error=f"GSC {r.status_code}: {msg}")

    rows = [
        GSCRow(key=(row.get("keys") or ["?"])[0],
               clicks=int(row.get("clicks", 0)),
               impressions=int(row.get("impressions", 0)),
               ctr=round(row.get("ctr", 0.0), 4),
               position=round(row.get("position", 0.0), 1))
        for row in r.json().get("rows", [])
    ]
    return GSCReport(site, start, end, dimension, "live", rows=rows)


def top_queries(site: str | None = None, *, days: int = 28, limit: int = 25) -> GSCReport:
    return query(site, days=days, dimension="query", row_limit=limit)


def top_pages(site: str | None = None, *, days: int = 28, limit: int = 25) -> GSCReport:
    return query(site, days=days, dimension="page", row_limit=limit)


def page_performance(page_url: str, *, site: str | None = None, days: int = 28,
                     limit: int = 25) -> GSCReport:
    """The queries a specific published page ranks for — the D1 outcome signal."""
    return query(site, days=days, dimension="query", row_limit=limit, page_filter=page_url)


# --------------------------------------------------------------------------- #
# Demo (deterministic synthetic data — zero creds, realistic AZ insurance)
# --------------------------------------------------------------------------- #

_DEMO_QUERIES = [
    "kasko sığorta", "kasko sığorta qiyməti", "kasko sığorta nədir",
    "icbari sığorta", "avtomobil sığortası", "sığorta kalkulyatoru",
    "onlayn kasko", "səyahət sığortası", "əmlak sığortası", "tibbi sığorta",
    "kasko hesablama", "sığorta şirkətləri", "franşiza nədir", "sığorta haqqı",
    "kasko sığorta onlayn", "avtomobil kasko qiyməti", "icbari sığorta yoxla",
]


def _seeded(text: str, lo: int, hi: int) -> int:
    h = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
    return lo + (h % (hi - lo + 1))


def _demo_report(site, start, end, dimension, row_limit, page_filter) -> GSCReport:
    rows: list[GSCRow] = []
    src = _DEMO_QUERIES if dimension == "query" else [
        f"https://xalqsigorta.az/{q.replace(' ', '-')}" for q in _DEMO_QUERIES]
    for key in src[:row_limit]:
        impr = _seeded(key + start, 200, 9000)
        pos = round(1 + _seeded(key, 0, 240) / 10, 1)          # 1.0 .. 25.0
        ctr = max(0.005, round(0.35 / pos, 4))                 # better position -> higher CTR
        clicks = int(impr * ctr)
        rows.append(GSCRow(key=key, clicks=clicks, impressions=impr, ctr=ctr, position=pos))
    rows.sort(key=lambda r: r.clicks, reverse=True)
    return GSCReport(site, start, end, dimension, "demo", rows=rows)
