"""SEO content brief — the strategy that makes an article rank.

Grounded, not guessed: we first harvest the REAL long-tail (Google Suggest) and
its intent clusters, then the LLM turns that evidence into a brief — target +
secondary keywords, title options, meta, a semantic H2/H3 outline, entities to
cover, and the exact People-Also-Ask-style questions to answer in an FAQ block.

The brief is where E-E-A-T and GEO are engineered in: an outline that answers the
real questions, in the real language, with the real entities, is what both Google
and AI Overviews reward.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .. import llm
from ..research.gap import GapResult, analyze_gap
from ..research.keywords import ResearchResult, research_keywords


@dataclass
class Brief:
    keyword: str
    intent: str = "informational"
    title_options: list[str] = field(default_factory=list)
    meta_title: str = ""
    meta_description: str = ""
    secondary_keywords: list[str] = field(default_factory=list)
    outline: list[dict] = field(default_factory=list)      # [{"h2":.., "h3":[..]}]
    entities: list[str] = field(default_factory=list)
    faqs: list[str] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    word_target: int = 1200
    grounded_keywords: list[str] = field(default_factory=list)
    gap: GapResult | None = None      # SERP competitor gap, when use_serp
    source: str = "llm"           # "llm" | "fallback"


_BRIEF_PROMPT = """Sən Azərbaycan bazarı üçün SEO strateqisən. Hədəf açar söz: "{kw}".

Aşağıda Google Autocomplete-dən çıxarılmış REAL axtarış sorğuları var — briefi
YALNIZ bu real datanı əsas götürərək qur (uydurma açar söz əlavə etmə):
{kws}

Bu dəqiq JSON strukturunda, bütün mətn Azərbaycan dilində cavab ver:
{{
 "intent": "informational|commercial|transactional|navigational",
 "title_options": ["3 fərqli, cəlbedici, açar-sözlü başlıq (<=60 simvol)"],
 "meta_title": "ən yaxşı başlıq (<=60 simvol)",
 "meta_description": "cəlbedici meta təsvir (140-160 simvol)",
 "secondary_keywords": ["real datadan 6-10 ikincili açar söz"],
 "outline": [{{"h2":"bölmə başlığı","h3":["alt-başlıq","alt-başlıq"]}}],
 "entities": ["mövzunu tam örtmək üçün 6-10 vacib anlayış/entity"],
 "faqs": ["real sorğulardan 4-6 FAQ sualı"],
 "internal_links": ["3-5 daxili keçid üçün mövzu"],
 "word_target": 1200
}}
Outline məntiqli semantik iyerarxiya olsun (giriş→əsas bölmələr→FAQ→nəticə).{gap}{learned}"""


def _gap_context(gap: GapResult | None) -> str:
    """Inject live-SERP competitor intelligence into the brief prompt."""
    if not gap or gap.source != "llm":
        return ""
    parts = ["\n\nCANLI SERP RƏQİB TƏHLİLİ (bunları nəzərə al):"]
    if gap.common_subtopics:
        parts.append("Rəqiblərin örtdüyü (mütləq daxil et): " + "; ".join(gap.common_subtopics[:8]))
    if gap.content_gaps:
        parts.append("Boşluqlar (SIRALANMA FÜRSƏTİ — mütləq örtməyə çalış): " + "; ".join(gap.content_gaps[:6]))
    if gap.faq_questions:
        parts.append("Real FAQ sualları: " + "; ".join(gap.faq_questions[:7]))
    return "\n".join(parts)


def _learned_context(keyword: str, learn: bool) -> str:
    """Inject past GSC outcome lessons (D1 reinforcement) into the brief prompt."""
    if not learn:
        return ""
    try:
        from .. import reinforce
        block = reinforce.recall_block(keyword)
    except Exception:  # noqa: BLE001
        block = ""
    if not block:
        return ""
    return ("\n\nKEÇMİŞ NƏTİCƏ DƏRSLƏRİ (öz saytımızın real GSC datası — bunları təkrarla/qaçın):\n"
            + block[:1500])


def build_brief(keyword: str, *, research: ResearchResult | None = None,
                gap: GapResult | None = None, use_serp: bool = False,
                learn: bool = True, max_keywords: int = 80) -> Brief:
    research = research or research_keywords(keyword, cluster=True, max_keywords=max_keywords)
    grounded = research.keywords[:max_keywords]
    if use_serp and gap is None:
        gap = analyze_gap(keyword)
    brief = Brief(keyword=keyword, grounded_keywords=grounded, gap=gap)

    data = llm.ask_json(_BRIEF_PROMPT.format(kw=keyword, kws="\n".join(grounded),
                                             gap=_gap_context(gap),
                                             learned=_learned_context(keyword, learn)), smart=True)
    if not data:
        # graceful fallback — still useful without an LLM; prefer live-SERP gap data
        brief.source = "fallback"
        brief.title_options = [keyword.capitalize()]
        brief.meta_title = keyword.capitalize()
        brief.secondary_keywords = grounded[:10]
        brief.outline = (gap.recommended_outline if gap and gap.recommended_outline
                         else [{"h2": kw.capitalize(), "h3": []} for kw in grounded[:6]])
        brief.faqs = (gap.faq_questions if gap and gap.faq_questions
                      else [k for k in grounded if any(q in k for q in ("nə", "necə", "niyə", "?"))][:5])
        return brief

    brief.intent = str(data.get("intent", "informational")).lower()
    brief.title_options = [str(t) for t in data.get("title_options", []) if str(t).strip()]
    brief.meta_title = str(data.get("meta_title", "")).strip() or (brief.title_options[0] if brief.title_options else keyword)
    brief.meta_description = str(data.get("meta_description", "")).strip()
    brief.secondary_keywords = [str(k) for k in data.get("secondary_keywords", []) if str(k).strip()]
    brief.entities = [str(e) for e in data.get("entities", []) if str(e).strip()]
    brief.faqs = [str(q) for q in data.get("faqs", []) if str(q).strip()]
    brief.internal_links = [str(x) for x in data.get("internal_links", []) if str(x).strip()]
    try:
        brief.word_target = int(data.get("word_target", 1200))
    except (TypeError, ValueError):
        brief.word_target = 1200
    outline = []
    for sec in data.get("outline", []):
        if isinstance(sec, dict) and sec.get("h2"):
            outline.append({"h2": str(sec["h2"]).strip(),
                            "h3": [str(h) for h in sec.get("h3", []) if str(h).strip()]})
    brief.outline = outline
    return brief
