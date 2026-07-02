"""Deterministic tests for the self-reflection loop (LLM faked, no network)."""

from __future__ import annotations

import seo.content.refine as rmod
from seo.content.brief import Brief
from seo.content.writer import Article, _build_jsonld


def _article(markdown: str | None = None) -> Article:
    brief = Brief(keyword="kasko sığorta", intent="informational",
                  secondary_keywords=["kasko qiyməti"])
    art = Article(
        keyword="kasko sığorta",
        h1="Kasko Sığorta — Tam Bələdçi",
        meta_title="Kasko Sığorta Nədir? Tam Bələdçi və Faydaları",
        meta_description="Kasko sığorta nədir, hansı riskləri əhatə edir və qiyməti necə hesablanır — ətraflı bələdçi.",
        markdown=markdown or ("## Kasko nədir\n\nİzah. " + "söz " * 320),
        faq=[{"q": "Kasko məcburidir?", "a": "Xeyr, könüllüdür."}],
        brief=brief,
    )
    art.jsonld = _build_jsonld(art)
    return art


def _run_with_fake_llm(responses: list[dict | None], article: Article):
    """Swap refine's llm.ask_json for a scripted sequence, run, restore."""
    calls = iter(responses)
    orig = rmod.llm.ask_json
    rmod.llm.ask_json = lambda *a, **k: next(calls, None)
    try:
        return rmod.refine_article(article.brief, article=article)
    finally:
        rmod.llm.ask_json = orig


def test_publish_verdict_stops_loop():
    res = _run_with_fake_llm(
        [{"verdict": "publish", "issues": [], "coverage_missing": []}], _article())
    assert not res.improved
    assert res.iterations[0].verdict == "publish"
    # no revision call was consumed — only the critique response was used
    assert len(res.iterations) == 1


def test_revise_path_improves_article():
    better_md = "## Kasko nədir\n\nDaha dolğun izah. " + "söz " * 350 + "\n\n## Françiza\n\nİzah."
    res = _run_with_fake_llm([
        {"verdict": "revise", "issues": ["françiza örtülməyib"], "coverage_missing": ["françiza"]},
        {"markdown": better_md, "faq": [{"q": "Françiza nədir?", "a": "İzah."}]},
        {"verdict": "publish", "issues": [], "coverage_missing": []},
    ], _article())
    assert res.improved
    assert "Françiza" in res.article.markdown
    assert res.article.faq[0]["q"] == "Françiza nədir?"
    verdicts = [i.verdict for i in res.iterations]
    assert "revise" in verdicts and "publish" in verdicts


def test_regression_is_rejected():
    """A revision that scores worse on our own checklist must not replace the draft."""
    original = _article()
    res = _run_with_fake_llm([
        {"verdict": "revise", "issues": ["x"], "coverage_missing": []},
        {"markdown": "qısa", "faq": []},   # tiny draft -> fails content-depth check
    ], original)
    assert not res.improved
    assert res.article.markdown == original.markdown   # kept the better version


def test_fallback_article_is_not_refined():
    art = _article()
    art.source = "fallback"
    res = _run_with_fake_llm([], art)
    assert res.iterations[0].verdict == "error"
    assert not res.improved
