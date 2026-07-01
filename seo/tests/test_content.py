"""Network/LLM-free tests for the content engine's deterministic parts:
markdown->HTML, JSON-LD assembly, and the on-page self-check dogfood loop.
"""

from __future__ import annotations

from seo.content.brief import Brief
from seo.content.writer import Article, _build_jsonld, onpage_selfcheck
from seo.render import _md_to_html, article_html


def _sample_article() -> Article:
    brief = Brief(keyword="kasko sığorta", intent="informational",
                  secondary_keywords=["kasko qiyməti", "kasko nədir"])
    art = Article(
        keyword="kasko sığorta",
        h1="Kasko Sığorta Nədir? Tam Bələdçi",
        meta_title="Kasko Sığorta Nədir? Tam Bələdçi və Faydaları",
        meta_description="Kasko sığorta nədir, hansı riskləri əhatə edir və qiyməti necə hesablanır — ətraflı bələdçi.",
        markdown="## Kasko nədir\n\nKasko könüllü sığorta növüdür.\n\n"
                 "- Qəza\n- Oğurluq\n\n### Faydalar\n\nMaliyyə təhlükəsizliyi təmin edir. " + ("söz " * 300),
        faq=[{"q": "Kasko məcburidir?", "a": "Xeyr, kasko könüllüdür."}],
        brief=brief,
    )
    art.jsonld = _build_jsonld(art)
    return art


def test_md_to_html_headings_and_lists():
    html = _md_to_html("## Başlıq\n\nAbzas mətni.\n\n- bir\n- iki\n\n### Alt\n\n1. birinci")
    assert "<h2>Başlıq</h2>" in html
    assert "<h3>Alt</h3>" in html
    assert "<ul>" in html and "<li>bir</li>" in html
    assert "<ol>" in html and "<li>birinci</li>" in html
    assert "<p>Abzas mətni.</p>" in html


def test_md_bold_inline():
    assert "<strong>vacib</strong>" in _md_to_html("Bu **vacib** sözdür.")


def test_jsonld_has_article_and_faqpage():
    art = _sample_article()
    types = [o.get("@type") for o in art.jsonld]
    assert "Article" in types and "FAQPage" in types
    faq = next(o for o in art.jsonld if o.get("@type") == "FAQPage")
    assert faq["mainEntity"][0]["@type"] == "Question"
    assert faq["mainEntity"][0]["acceptedAnswer"]["text"] == "Xeyr, kasko könüllüdür."


def test_article_html_has_onpage_essentials():
    html = article_html(_sample_article())
    assert "<h1>" in html
    assert 'name="description"' in html
    assert 'name="viewport"' in html
    assert 'lang="az"' in html
    assert "application/ld+json" in html


def test_self_check_passes_core_onpage():
    """The generated article must be built to pass our own on-page checklist."""
    check = onpage_selfcheck(article_html(_sample_article()))
    ids = {i: s for i, s, _ in check["findings"]}
    assert ids["title"] == "pass"
    assert ids["h1"] == "pass"
    assert ids["schema"] == "pass"
    assert ids["description"] == "pass"
    assert check["passed"] >= 5
