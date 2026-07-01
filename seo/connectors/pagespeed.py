"""Core Web Vitals via Google PageSpeed Insights API — free, keyless-capable.

Returns real lab + field metrics (LCP, INP, CLS, and the performance score).
Works with NO key (rate-limited); a key just raises quota. If the call fails or
is rate-limited we return available=False so the auditor labels it ƏLÇATMAZ
rather than inventing numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from .. import config


@dataclass
class Vitals:
    available: bool = False
    strategy: str = "mobile"
    performance: float | None = None    # 0-100
    lcp_ms: float | None = None         # Largest Contentful Paint
    inp_ms: float | None = None         # Interaction to Next Paint (replaced FID)
    cls: float | None = None            # Cumulative Layout Shift
    field_data: bool = False            # True if real-user (CrUX) data present
    error: str = ""

    def verdict(self) -> str:
        """Google's own 'good' thresholds (2026)."""
        if not self.available:
            return "unknown"
        bad = []
        if self.lcp_ms is not None and self.lcp_ms > 2500:
            bad.append("LCP")
        if self.inp_ms is not None and self.inp_ms > 200:
            bad.append("INP")
        if self.cls is not None and self.cls > 0.1:
            bad.append("CLS")
        return "good" if not bad else "poor:" + ",".join(bad)


def _num(d, *path, default=None):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def core_web_vitals(url: str, strategy: str = "mobile") -> Vitals:
    v = Vitals(strategy=strategy)
    params = {"url": url, "strategy": strategy, "category": "performance"}
    if config.PSI_API_KEY:
        params["key"] = config.PSI_API_KEY
    try:
        resp = requests.get(config.PSI_ENDPOINT, params=params, timeout=60)
        if resp.status_code != 200:
            v.error = f"PSI HTTP {resp.status_code}"
            return v
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        v.error = str(e)[:160]
        return v

    lh = data.get("lighthouseResult", {})
    score = _num(lh, "categories", "performance", "score")
    if score is not None:
        v.performance = round(score * 100)
    audits = lh.get("audits", {})
    lcp = _num(audits, "largest-contentful-paint", "numericValue")
    cls = _num(audits, "cumulative-layout-shift", "numericValue")
    if lcp is not None:
        v.lcp_ms = round(lcp)
    if cls is not None:
        v.cls = round(cls, 3)

    # Field (real-user) data — INP lives here; prefer it when present.
    loading = data.get("loadingExperience", {}).get("metrics", {})
    inp = _num(loading, "INTERACTION_TO_NEXT_PAINT", "percentile")
    if inp is not None:
        v.inp_ms = inp
        v.field_data = True
    f_lcp = _num(loading, "LARGEST_CONTENTFUL_PAINT_MS", "percentile")
    if f_lcp is not None:
        v.lcp_ms = f_lcp
        v.field_data = True
    f_cls = _num(loading, "CUMULATIVE_LAYOUT_SHIFT_SCORE", "percentile")
    if f_cls is not None:
        v.cls = round(f_cls / 100, 3)

    v.available = v.performance is not None or v.lcp_ms is not None
    return v
