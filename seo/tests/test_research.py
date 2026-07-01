"""Network/LLM-free tests for the research layer: SERP parsing, gap reporting,
and the brief's SERP-gap fallback wiring."""

from __future__ import annotations

from seo.connectors.serp import parse_serp
from seo.content.brief import build_brief
from seo.report import gap_report
from seo.research.gap import Competitor, GapResult

# a compact DuckDuckGo-HTML fixture (redirect-wrapped + direct hrefs, a dupe domain)
SERP_FIXTURE = """
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fkasko.az%2Fnedir">Kasko nədir</a>
<a class="result__snippet">Kasko haqqında məlumat.</a>
<a class="result__a" href="https://insure.az/kasko">Insure Kasko</a>
<a class="result__snippet">Insure snippet.</a>
<a class="result__a" href="https://kasko.az/qiymet">Kasko qiymət (eyni domen)</a>
<a class="result__snippet">dupe domain.</a>
<a class="result__a" href="https://pasha-insurance.az/kasko">Paşa Kasko</a>
<a class="result__snippet">Paşa snippet.</a>
"""


def test_parse_serp_dedupes_by_domain_and_cleans_redirect():
    res = parse_serp(SERP_FIXTURE, n=10)
    domains = [r.domain for r in res]
    assert domains == ["kasko.az", "insure.az", "pasha-insurance.az"]  # dupe kasko.az dropped
    assert res[0].url == "https://kasko.az/nedir"                       # uddg redirect unwrapped
    assert res[0].title == "Kasko nədir"
    assert res[0].snippet == "Kasko haqqında məlumat."
    assert res[0].rank == 1


def test_gap_report_renders_sections():
    g = GapResult(
        keyword="kasko sığorta", source="llm",
        competitors=[Competitor(1, "Kasko.az", "https://kasko.az", "kasko.az", ["H2 a", "H3 b"])],
        common_subtopics=["nədir", "əhatə"],
        content_gaps=["françiza"],
        faq_questions=["Kasko nədir?"],
    )
    txt = gap_report(g)
    assert "CONTENT-GAP" in txt
    assert "françiza" in txt
    assert "kasko.az" in txt
    assert "Kasko nədir?" in txt


def test_brief_fallback_uses_gap_when_llm_down():
    """With no LLM, the brief must still borrow the live-SERP gap's outline/FAQ."""
    import seo.content.brief as bmod
    from seo.research.keywords import ResearchResult
    orig_ask, orig_research = bmod.llm.ask_json, bmod.research_keywords
    bmod.llm.ask_json = lambda *a, **k: None
    bmod.research_keywords = lambda *a, **k: ResearchResult(seed="k", keywords=["k a", "k b"])
    try:
        gap = GapResult(keyword="k", source="llm",
                        recommended_outline=[{"h2": "Bölmə 1", "h3": ["x"]}],
                        faq_questions=["Sual 1?"])
        brief = build_brief("k", gap=gap)
    finally:
        bmod.llm.ask_json, bmod.research_keywords = orig_ask, orig_research
    assert brief.source == "fallback"
    assert brief.outline == [{"h2": "Bölmə 1", "h3": ["x"]}]
    assert brief.faqs == ["Sual 1?"]
