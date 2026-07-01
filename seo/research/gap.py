"""Content-gap analysis — what actually ranks, and what everyone is missing.

The pipeline pro tools charge for, built from free parts:
  1. SERP (DuckDuckGo) → the top competitor URLs for the keyword.
  2. Our own crawler reads each competitor's heading structure (H2/H3) — the
     real shape of ranking content.
  3. The LLM synthesizes: the subtopics everyone covers (table stakes), the
     high-value questions to answer (FAQ), and the GAPS — angles few competitors
     cover, i.e. the ranking opportunity.

Feeds the brief so our articles are grounded in the live SERP, not guesses.
"""

from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass, field

from .. import llm
from ..connectors import serp as serp_mod
from ..connectors.suggest import AZ_QUESTIONS, suggest
from ..htmlparse import parse
from ..http import fetch


@dataclass
class Competitor:
    rank: int
    title: str
    url: str
    domain: str
    headings: list[str] = field(default_factory=list)


@dataclass
class GapResult:
    keyword: str
    competitors: list[Competitor] = field(default_factory=list)
    common_subtopics: list[str] = field(default_factory=list)
    content_gaps: list[str] = field(default_factory=list)
    faq_questions: list[str] = field(default_factory=list)
    recommended_outline: list[dict] = field(default_factory=list)
    source: str = "raw"          # "llm" | "raw"

    @property
    def analyzed(self) -> int:
        return sum(1 for c in self.competitors if c.headings)


def _crawl_headings(sr) -> Competitor:
    c = Competitor(rank=sr.rank, title=sr.title, url=sr.url, domain=sr.domain)
    f = fetch(sr.url)
    if not f.error and f.html:
        page = parse(f.html)
        c.headings = [t for lvl, t in page.headings if lvl in (2, 3) and t][:14]
    return c


_GAP_PROMPT = """Sən SEO content strateqisən. Hədəf açar söz: "{kw}".

Google/DuckDuckGo-da bu sorğu üzrə TOP sıralanan rəqiblər və onların
başlıq strukturu (H2/H3):
{comp}

İstifadəçilərin real sualları (Google Autocomplete):
{qs}

Bu real rəqib datasını təhlil et və YALNIZ bu JSON formatında (hamısı Azərbaycan dilində) cavab ver:
{{
 "common_subtopics": ["əksər rəqibin örtdüyü 5-8 mövzu — bunlar mütləq lazımdır"],
 "content_gaps": ["rəqiblərin zəif örtdüyü və ya heç örtmədiyi 3-6 mövzu — sıralanma fürsəti"],
 "faq_questions": ["real suallardan 5-7 FAQ sualı"],
 "recommended_outline": [{{"h2":"bölmə","h3":["alt","alt"]}}]
}}
recommended_outline rəqibləri üstələyəcək qədər hərtərəfli, amma məntiqli olsun."""


def analyze_gap(keyword: str, *, top_n: int = 5) -> GapResult:
    res = GapResult(keyword=keyword)
    results = serp_mod.search(keyword, n=top_n)
    if not results:
        return res
    with cf.ThreadPoolExecutor(max_workers=min(len(results), 5)) as ex:
        res.competitors = list(ex.map(_crawl_headings, results))

    # real questions from autocomplete (PAA-style)
    questions: list[str] = []
    for q in AZ_QUESTIONS[:5]:
        questions += suggest(f"{q} {keyword}")[:3]
    questions = list(dict.fromkeys(questions))[:20]

    if not llm.available():
        return res
    comp_txt = "\n".join(
        f"[{c.rank}] {c.domain} — {c.title}\n    " + " | ".join(c.headings[:10])
        for c in res.competitors if c.headings
    ) or "(rəqib başlıqları oxunmadı)"

    data = llm.ask_json(_GAP_PROMPT.format(kw=keyword, comp=comp_txt,
                                           qs="\n".join(questions)), smart=True)
    if not data:
        return res
    res.common_subtopics = [str(x) for x in data.get("common_subtopics", []) if str(x).strip()]
    res.content_gaps = [str(x) for x in data.get("content_gaps", []) if str(x).strip()]
    res.faq_questions = [str(x) for x in data.get("faq_questions", []) if str(x).strip()]
    outline = []
    for sec in data.get("recommended_outline", []):
        if isinstance(sec, dict) and sec.get("h2"):
            outline.append({"h2": str(sec["h2"]).strip(),
                            "h3": [str(h) for h in sec.get("h3", []) if str(h).strip()]})
    res.recommended_outline = outline
    res.source = "llm"
    return res
