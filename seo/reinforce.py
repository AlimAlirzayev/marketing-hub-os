"""D1 — the reinforcement loop: the system learns from its own market outcomes.

Not RL-training (that's D2, gated on data volume). This is the *outcome feedback*
loop that makes every future article a little smarter, for free:

    publish → wait ~28 days → GSC measures what actually ranked → distill a lesson
    (brain) + append the outcome to a corpus (data/seo/corpus) → future briefs
    RECALL those lessons before they're written.

Two durable stores, two purposes:
  * brain/ lesson  → recalled into the next brief (immediate compounding).
  * corpus JSONL   → the labelled dataset D2 (fine-tuning) needs; grows for free
    until the ≥500-row trigger in seo/ROADMAP.md fires.

Everything degrades gracefully: no GSC creds → honest demo/label; no brain → the
corpus still grows; nothing is fabricated (every number comes from GSC).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from . import config
from .connectors import gsc

_CORPUS = config.DATA_DIR / "corpus" / "outcomes.jsonl"


@dataclass
class Outcome:
    page_url: str
    keyword: str
    mode: str                    # "live" | "demo"
    clicks: int = 0
    impressions: int = 0
    avg_position: float = 0.0
    ctr: float = 0.0
    top_queries: list[dict] = field(default_factory=list)   # [{query, clicks, position}]
    verdict: str = "no-data"     # winning | climbing | struggling | no-data
    lesson_saved: bool = False
    corpus_size: int = 0
    measured_on: str = ""


def _brain():
    try:
        import brain  # repo-root package
        return brain
    except Exception:  # noqa: BLE001 — reinforcement must survive without brain
        return None


def _summarize(report: gsc.GSCReport, keyword: str, page_url: str) -> Outcome:
    o = Outcome(page_url=page_url, keyword=keyword, mode=report.mode,
                measured_on=date.today().isoformat())
    rows = report.rows
    if not rows:
        return o
    o.clicks = sum(r.clicks for r in rows)
    o.impressions = sum(r.impressions for r in rows)
    o.ctr = round(o.clicks / o.impressions, 4) if o.impressions else 0.0
    # impression-weighted average position (matches how GSC reports it)
    wsum = sum(r.position * r.impressions for r in rows)
    o.avg_position = round(wsum / o.impressions, 1) if o.impressions else 0.0
    o.top_queries = [{"query": r.key, "clicks": r.clicks, "position": r.position}
                     for r in sorted(rows, key=lambda x: x.clicks, reverse=True)[:5]]
    # verdict from the position band (Google's own "page 1 = <10" heuristic)
    if o.avg_position and o.avg_position <= 10 and o.clicks > 0:
        o.verdict = "winning"
    elif o.avg_position and o.avg_position <= 20:
        o.verdict = "climbing"
    elif o.impressions:
        o.verdict = "struggling"
    return o


def _append_corpus(o: Outcome, article: dict | None = None) -> int:
    _CORPUS.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": o.measured_on, "keyword": o.keyword, "page_url": o.page_url,
        "mode": o.mode, "clicks": o.clicks, "impressions": o.impressions,
        "avg_position": o.avg_position, "ctr": o.ctr,
        "verdict": o.verdict, "top_queries": o.top_queries,
    }
    if article:
        rec["article"] = article           # meta_title/intent/words for D2 features
    with _CORPUS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return sum(1 for _ in _CORPUS.open(encoding="utf-8"))


def _remember_lesson(o: Outcome) -> bool:
    b = _brain()
    if b is None or o.verdict == "no-data":
        return False
    tops = ", ".join(f"{q['query']} (poz {q['position']}, {q['clicks']} klik)"
                     for q in o.top_queries[:3])
    body = (
        f"SEO NƏTİCƏ ({o.mode}): '{o.keyword}' üçün yazılan səhifə "
        f"({o.page_url}) 28 günə orta mövqe {o.avg_position}, {o.clicks} klik, "
        f"{o.impressions} göstərim aldı — hökm: {o.verdict}. Ən güclü sorğular: {tops}. "
        f"Gələcək brief-lər bu nəticəni nəzərə alsın: '{o.verdict}' olan mövzu/üslubu "
        f"təkrarla, 'struggling' olanı yenidən düşün."
    )
    try:
        b.remember(
            f"SEO outcome: {o.keyword} → {o.verdict} (poz {o.avg_position})",
            body=body, type="lesson",
            tags="seo,reinforcement,gsc,outcome",
            source=f"GSC reflect {o.measured_on}",
            confidence="high" if o.mode == "live" else "low",
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def reflect_on_published(page_url: str, keyword: str = "", *, days: int = 28,
                         article: dict | None = None) -> Outcome:
    """Pull a published page's real GSC performance → lesson + corpus row."""
    report = gsc.page_performance(page_url, days=days)
    o = _summarize(report, keyword or page_url, page_url)
    o.corpus_size = _append_corpus(o, article)
    o.lesson_saved = _remember_lesson(o)
    return o


def recall_block(keyword: str) -> str:
    """Past SEO outcome lessons relevant to a keyword — injected into new briefs
    so the writer starts from what already ranked. '' when brain/lessons absent."""
    b = _brain()
    if b is None:
        return ""
    try:
        block = b.recall_block(f"SEO ranking outcome for {keyword}")
        return block or ""
    except Exception:  # noqa: BLE001
        return ""
