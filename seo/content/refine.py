"""Self-reflection loop — the article improves itself before a human sees it.

This turns the dogfooding seed (onpage_selfcheck) into a full iterative cycle:

    write → measure (own 2026 checklist) → critique (AI editor, grounded in the
    brief + SERP gap) → revise → re-measure → ... until publish-grade or capped.

Design rules:
  * Bounded. max_iters caps LLM spend (free tier is a budget too). One revision
    pass fixes most drafts; two is the ceiling.
  * Grounded critique. The critic judges against the brief's real keywords and
    the SERP gap's must-cover topics — not vibes.
  * Honest trace. Every iteration's scores are kept, so the operator sees the
    draft actually improved (or that it was already publish-grade).
  * Never worse. If a revision scores lower than what it replaced, we keep the
    better version — reflection must not regress the deliverable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import llm
from .brief import Brief
from .writer import Article, _build_jsonld, onpage_selfcheck, write_article


@dataclass
class Iteration:
    n: int
    onpage_passed: int
    onpage_total: int
    verdict: str                 # "publish" | "revise" | "error"
    issues: list[str] = field(default_factory=list)


@dataclass
class RefineResult:
    article: Article
    iterations: list[Iteration] = field(default_factory=list)
    improved: bool = False       # a revision actually replaced the draft

    @property
    def final_check(self) -> tuple[int, int]:
        if not self.iterations:
            return (0, 0)
        last = self.iterations[-1]
        return (last.onpage_passed, last.onpage_total)


_CRITIQUE_PROMPT = """Sən tələbkar SEO redaktorusan. Aşağıdakı Azərbaycan dilində məqaləni
hədəf açar söz "{kw}" üçün qiymətləndir.

BRIEF (məqalə bunları örtməli idi):
- İkincili açar sözlər: {secondary}
- Örtüləcək anlayışlar: {entities}
- Mütləq mövzular (rəqib table-stakes): {stakes}
- Sıralanma fürsəti (boşluqlar — örtülsə böyük üstünlük): {gaps}

MƏQALƏ:
{article}

Yalnız bu JSON formatında cavab ver:
{{
 "verdict": "publish|revise",
 "issues": ["konkret problem 1", "konkret problem 2", "..."],
 "coverage_missing": ["brief-də olub məqalədə örtülməyən mövzular"]
}}
Qaydalar: yalnız REAL problemləri göstər (uydurma tənqid yox). Məqalə brief-i
yaxşı örtürsə və təbii oxunursa "publish" ver. Xırda üslub zövqü "revise" səbəbi deyil."""


_REVISE_PROMPT = """Sən Azərbaycan dilində yazan peşəkar SEO redaktorusan. Aşağıdakı məqaləni
redaktor tənqidinə əsasən TƏKMİLLƏŞDİR (yenidən yazma — problemləri həll et,
yaxşı hissələri saxla).

Hədəf açar söz: "{kw}"

TƏNQİD (bunları həll et):
{issues}

ÖRTÜLMƏYƏN MÖVZULAR (əlavə et):
{missing}

MÖVCUD MƏQALƏ:
{article}

Yalnız bu JSON formatında cavab ver:
{{
 "markdown": "təkmilləşdirilmiş tam məqalə (## və ### başlıqlarla, H1-siz)",
 "faq": [{{"q":"sual","a":"cavab"}}]
}}
Uydurma statistika/rəqəm əlavə etmə. Mövcud FAQ-ları saxla/yaxşılaşdır."""


def _critique(art: Article, brief: Brief) -> dict:
    gap = brief.gap
    data = llm.ask_json(_CRITIQUE_PROMPT.format(
        kw=brief.keyword,
        secondary=", ".join(brief.secondary_keywords[:10]) or "—",
        entities=", ".join(brief.entities[:10]) or "—",
        stakes=", ".join(gap.common_subtopics[:8]) if gap else "—",
        gaps=", ".join(gap.content_gaps[:6]) if gap else "—",
        article=art.markdown[:9000],
    ))
    if not data or data.get("verdict") not in ("publish", "revise"):
        return {"verdict": "error", "issues": [], "coverage_missing": []}
    return {
        "verdict": data["verdict"],
        "issues": [str(x) for x in data.get("issues", []) if str(x).strip()][:8],
        "coverage_missing": [str(x) for x in data.get("coverage_missing", []) if str(x).strip()][:8],
    }


def _revise(art: Article, brief: Brief, critique: dict) -> Article | None:
    data = llm.ask_json(_REVISE_PROMPT.format(
        kw=brief.keyword,
        issues="\n".join(f"- {i}" for i in critique["issues"]) or "—",
        missing="\n".join(f"- {m}" for m in critique["coverage_missing"]) or "—",
        article=art.markdown[:9000],
    ), smart=True, temperature=0.5)
    if not data or not data.get("markdown"):
        return None
    new = Article(
        keyword=art.keyword, h1=art.h1,
        meta_title=art.meta_title, meta_description=art.meta_description,
        markdown=str(data["markdown"]).strip(),
        faq=[{"q": str(x.get("q", "")).strip(), "a": str(x.get("a", "")).strip()}
             for x in data.get("faq", []) if isinstance(x, dict) and x.get("q")] or art.faq,
        brief=brief, source="llm", lang=art.lang,
    )
    new.jsonld = _build_jsonld(new)
    return new


def _measure(art: Article) -> tuple[int, int]:
    from ..render import article_html
    check = onpage_selfcheck(article_html(art))
    return check["passed"], check["total"]


def refine_article(brief: Brief, *, max_iters: int = 2,
                   article: Article | None = None) -> RefineResult:
    """Write (or take) a draft, then self-reflect until publish-grade or capped."""
    art = article or write_article(brief)
    res = RefineResult(article=art)
    if art.source != "llm":               # fallback skeleton — nothing to refine
        p, t = _measure(art)
        res.iterations.append(Iteration(0, p, t, "error", ["LLM əlçatmaz — skelet"]))
        return res

    for n in range(1, max_iters + 1):
        passed, total = _measure(art)
        critique = _critique(art, brief)
        it = Iteration(n, passed, total, critique["verdict"],
                       critique["issues"] + critique["coverage_missing"])
        res.iterations.append(it)
        if critique["verdict"] != "revise":
            break
        revised = _revise(art, brief, critique)
        if revised is None:
            break
        new_passed, _ = _measure(revised)
        if new_passed >= passed:          # never regress the deliverable
            art = revised
            res.improved = True
        else:
            break

    # final state always measured & recorded
    p, t = _measure(art)
    if not res.iterations or (res.iterations[-1].onpage_passed, res.iterations[-1].onpage_total) != (p, t):
        res.iterations.append(Iteration(len(res.iterations) + 1, p, t, "publish", []))
    res.article = art
    return res
