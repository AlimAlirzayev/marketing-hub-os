"""Deterministic, network-free tests for the SEO audit engine.

They exercise the parser, every check's pass/warn/fail branch via synthetic
contexts, and the scoring — so CI stays green without touching the internet.
"""

from __future__ import annotations

from seo.audit import checklist
from seo.audit.checklist import AuditContext
from seo.connectors.pagespeed import Vitals
from seo.connectors.robots import RobotsInfo
from seo.htmlparse import parse


# ---- parser ---------------------------------------------------------------- #

GOOD_HTML = """
<html lang="az"><head>
<title>Yaxşı Başlıq — Test Sayt SEO</title>
<meta name="description" content="Bu təsvir təxminən altmış simvoldan çoxdur və ideal uzunluq diapazonundadır deyə bilərik.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="https://x.az/">
<link rel="icon" href="/favicon.ico">
<meta property="og:title" content="T"><meta property="og:image" content="https://x.az/i.png">
<script type="application/ld+json">{"@type":"Organization","name":"X"}</script>
</head><body>
<h1>Bir</h1><h2>İki</h2><h3>Üç</h3>
<img src="a" alt="var"><img src="b" alt="var2">
<p>%s</p></body></html>
""" % ("söz " * 320)


def _ctx(html=GOOD_HTML, *, url="https://x.az/", robots=None, sitemap_ok=True,
         vitals=None, status=200, ssl_verified=True, apex_unreachable=False,
         www_fallback_url="") -> AuditContext:
    class F:  # minimal Fetched stand-in
        pass
    f = F()
    f.url = url
    f.status = status
    f.elapsed_ms = 120
    f.ssl_verified = ssl_verified
    f.apex_unreachable = apex_unreachable
    f.www_fallback_url = www_fallback_url
    return AuditContext(
        url=url, fetched=f, page=parse(html),
        robots=robots or RobotsInfo(exists=True, sitemaps=["s.xml"]),
        sitemap_ok=sitemap_ok, sitemap_url="https://x.az/sitemap.xml",
        vitals=vitals or Vitals(),
    )


def test_parser_extracts_core_signals():
    p = parse(GOOD_HTML)
    assert p.title.startswith("Yaxşı")
    assert len(p.h1) == 1
    assert p.html_lang == "az"
    assert p.img_total == 2 and p.img_missing_alt == 0
    assert p.jsonld_types == ["Organization"]
    assert p.canonical and p.viewport and p.favicon
    assert p.text_words >= 300


def test_good_page_scores_high():
    findings = checklist.run_all(_ctx())
    pct, grade = checklist.score(findings)
    assert pct >= 85, [f"{f.title}:{f.status}" for f in findings if f.status in ("warn", "fail")]
    assert grade in ("A", "B")


def test_missing_https_fails():
    c = _ctx(url="http://x.az/")
    f = next(x for x in checklist.run_all(c) if x.id == "https")
    assert f.status == "fail" and f.weight == 3


def test_missing_title_fails():
    html = GOOD_HTML.replace("<title>Yaxşı Başlıq — Test Sayt SEO</title>", "")
    f = next(x for x in checklist.run_all(_ctx(html)) if x.id == "title")
    assert f.status == "fail"


def test_multiple_h1_warns():
    html = GOOD_HTML.replace("<h1>Bir</h1>", "<h1>Bir</h1><h1>İki</h1>")
    f = next(x for x in checklist.run_all(_ctx(html)) if x.id == "h1")
    assert f.status == "warn"


def test_missing_schema_fails():
    html = GOOD_HTML.replace('<script type="application/ld+json">{"@type":"Organization","name":"X"}</script>', "")
    f = next(x for x in checklist.run_all(_ctx(html)) if x.id == "schema")
    assert f.status == "fail"


def test_noindex_fails_indexable():
    html = GOOD_HTML.replace('<meta name="viewport"', '<meta name="robots" content="noindex"><meta name="viewport"')
    f = next(x for x in checklist.run_all(_ctx(html)) if x.id == "indexable")
    assert f.status == "fail"


def test_sitemap_missing_fails():
    f = next(x for x in checklist.run_all(_ctx(sitemap_ok=False)) if x.id == "sitemap")
    assert f.status == "fail"


def test_vitals_good_passes():
    v = Vitals(available=True, performance=95, lcp_ms=1800, inp_ms=120, cls=0.05, field_data=True)
    f = next(x for x in checklist.run_all(_ctx(vitals=v)) if x.id == "cwv")
    assert f.status == "pass"


def test_vitals_poor_fails():
    v = Vitals(available=True, performance=40, lcp_ms=4200, inp_ms=350, cls=0.3)
    f = next(x for x in checklist.run_all(_ctx(vitals=v)) if x.id == "cwv")
    assert f.status == "fail" and "LCP" in f.detail


def test_vitals_unavailable_is_na():
    f = next(x for x in checklist.run_all(_ctx(vitals=Vitals(available=False))) if x.id == "cwv")
    assert f.status == "na"


def test_ai_governance_detected():
    r = RobotsInfo(exists=True, ai_bots_mentioned=["GPTBot", "ClaudeBot"])
    f = next(x for x in checklist.run_all(_ctx(robots=r)) if x.id == "ai_bots")
    assert f.status == "info" and "GPTBot" in f.detail


def test_ssl_chain_pass_when_verified():
    f = next(x for x in checklist.run_all(_ctx()) if x.id == "ssl_chain")
    assert f.status == "pass"


def test_ssl_chain_fails_when_unverified():
    c = _ctx(ssl_verified=False)
    f = next(x for x in checklist.run_all(c) if x.id == "ssl_chain")
    assert f.status == "fail" and f.weight == 2


def test_apex_pass_when_reachable():
    f = next(x for x in checklist.run_all(_ctx()) if x.id == "apex")
    assert f.status == "pass"


def test_apex_fails_when_only_www_answers():
    c = _ctx(apex_unreachable=True, www_fallback_url="https://www.x.az/")
    f = next(x for x in checklist.run_all(c) if x.id == "apex")
    assert f.status == "fail" and "www.x.az" in f.detail
