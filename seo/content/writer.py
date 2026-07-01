"""Article writer — brief -> on-page-perfect Azerbaijani draft + structured data.

One smart LLM call turns the brief into a real article (markdown body + a
structured FAQ). We then engineer the on-page layer around it: a single H1, meta
title/description, and JSON-LD (Article + FAQPage) — the exact things our own
auditor checks. The result is content built to pass our own 2026 checklist, which
`onpage_selfcheck()` verifies (the dogfooding / self-reflection loop).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .. import llm
from .brief import Brief


@dataclass
class Article:
    keyword: str
    h1: str
    meta_title: str
    meta_description: str
    markdown: str = ""
    faq: list[dict] = field(default_factory=list)     # [{"q":..,"a":..}]
    jsonld: list = field(default_factory=list)
    brief: Brief | None = None
    source: str = "llm"                                # "llm" | "fallback"
    lang: str = "az"


_WRITE_PROMPT = """Sən Azərbaycan dilində yazan peşəkar SEO kontent yazıçısısan.
Hədəf açar söz: "{kw}" · axtarış niyyəti: {intent}.

Bu strukturlu brief əsasında dolğun, orijinal, dəyərli məqalə yaz:
Başlıq (H1): {title}
Bölmələr (H2/H3): {outline}
İşlədiləcək ikincili açar sözlər (təbii şəkildə): {secondary}
Örtüləcək anlayışlar: {entities}
Hədəf həcm: ~{words} söz.

Qaydalar: E-E-A-T (dəqiq, etibarlı, faydalı) · açar sözü doldurma (keyword stuffing) YOX ·
qısa abzaslar · lazım olduqda siyahılar · Azərbaycan dilinin təbii, canlı üslubu ·
uydurma statistika/rəqəm YOX.

Yalnız bu JSON formatında cavab ver:
{{
 "markdown": "H1-siz, ## və ### başlıqlarla tam məqalə (giriş abzası ilə başla, sonda qısa nəticə)",
 "faq": [{{"q":"sual","a":"2-4 cümləlik dəqiq cavab"}}]
}}
FAQ bu suallara cavab versin: {faqs}"""


def write_article(brief: Brief) -> Article:
    title = brief.title_options[0] if brief.title_options else brief.keyword.capitalize()
    art = Article(
        keyword=brief.keyword, h1=title,
        meta_title=brief.meta_title or title,
        meta_description=brief.meta_description,
        brief=brief,
    )
    outline_txt = "; ".join(
        f"{s['h2']} ({', '.join(s.get('h3', []))})" if s.get("h3") else s["h2"]
        for s in brief.outline
    ) or "giriş, əsas hissə, nəticə"

    data = llm.ask_json(_WRITE_PROMPT.format(
        kw=brief.keyword, intent=brief.intent, title=title, outline=outline_txt,
        secondary=", ".join(brief.secondary_keywords[:10]),
        entities=", ".join(brief.entities[:10]),
        words=brief.word_target, faqs=" | ".join(brief.faqs[:6]),
    ), smart=True, temperature=0.6)

    if not data or not data.get("markdown"):
        art.source = "fallback"
        art.markdown = f"## {brief.keyword}\n\n_(LLM əlçatmaz — brief-dən skelet yaradıldı.)_\n\n" + \
                       "\n".join(f"## {s['h2']}" for s in brief.outline)
        return art

    art.markdown = str(data["markdown"]).strip()
    art.faq = [{"q": str(x.get("q", "")).strip(), "a": str(x.get("a", "")).strip()}
               for x in data.get("faq", []) if isinstance(x, dict) and x.get("q")]
    if not art.meta_description:
        # derive from first sentence of the body as a safe default
        first = art.markdown.lstrip("# ").replace("\n", " ")
        art.meta_description = (first[:157] + "…") if len(first) > 158 else first
    art.jsonld = _build_jsonld(art)
    return art


def _build_jsonld(art: Article) -> list:
    graph: list = [{
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": art.h1[:110],
        "description": art.meta_description,
        "inLanguage": art.lang,
        "keywords": ", ".join([art.keyword] + (art.brief.secondary_keywords[:8] if art.brief else [])),
        "datePublished": date.today().isoformat(),
        "author": {"@type": "Organization", "name": "Xalq Sigorta"},
        "publisher": {"@type": "Organization", "name": "Xalq Sigorta"},
    }]
    if art.faq:
        graph.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": q["a"]}}
                for q in art.faq
            ],
        })
    return graph


def onpage_selfcheck(article_html: str) -> dict:
    """Dogfood: run the article's own HTML through our parser + on-page checks.
    Returns a small scorecard proving the draft is built to pass the 2026 checklist.
    """
    from ..audit import checklist
    from ..audit.checklist import AuditContext
    from ..connectors.pagespeed import Vitals
    from ..connectors.robots import RobotsInfo
    from ..htmlparse import parse

    class _F:
        url = "https://example.az/article"
        status = 200
        elapsed_ms = 0
    ctx = AuditContext(url=_F.url, fetched=_F(), page=parse(article_html),
                       robots=RobotsInfo(exists=True), sitemap_ok=True,
                       sitemap_url="", vitals=Vitals())
    # only the checks an unpublished draft controls
    relevant = {"title", "description", "h1", "headings", "lang", "content", "schema", "img_alt"}
    findings = [f for f in checklist.run_all(ctx) if f.id in relevant]
    passed = sum(1 for f in findings if f.status == "pass")
    return {
        "passed": passed, "total": len(findings),
        "findings": [(f.id, f.status, f.title) for f in findings],
    }
