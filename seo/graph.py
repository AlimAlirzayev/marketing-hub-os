"""Durable SEO pipeline — the engines as a LangGraph, not a script.

Why a graph when the CLI already chains these steps? Three properties a plain
script can't give, inherited from the autonomous spine (orchestrator/graph.py):

  * **Durability.** Every node's output is checkpointed (SqliteSaver). A batch
    of 20 articles that dies at #14 resumes at #14 — the SERP crawls and briefs
    already paid for are never re-bought.
  * **Interrupt before impact.** Publishing is an outward-facing action; the
    graph *pauses* at a human checkpoint (interrupt()) and resumes only on
    explicit approval — AGENTS.md's risky-action rule, enforced by the runtime.
  * **Inspectable state.** Each run's thread can be examined mid-flight; the
    morning report can list every paused-awaiting-approval thread.

Flow:   research → (gap?) → brief → write+refine → (publish? → human gate) → remember

All state kept JSON-serializable (plain dicts) so the checkpointer stays happy;
heavy artifacts (the article HTML) go to disk, the state holds paths.

CLI:    python -m seo pipeline "<keyword>" [--serp] [--no-refine] [--publish]
        python -m seo pipeline --resume <thread_id> --decision approve
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from . import config

_CKPT_DB = config.DATA_DIR / "pipeline_checkpoints.sqlite"
_RUNS_LOG = config.DATA_DIR / "pipeline_runs.jsonl"


class SeoState(TypedDict, total=False):
    # inputs
    keyword: str
    use_serp: bool
    refine: bool
    publish: bool
    # research
    keywords: list[str]
    clusters: list[dict]
    # gap
    gap: dict            # {common_subtopics, content_gaps, faq_questions, recommended_outline, source}
    # brief
    brief: dict
    # article
    article_path: str
    words: int
    onpage: str          # "6/8"
    iterations: list[dict]
    improved: bool
    # publish
    approved: bool
    published: bool
    result: str


# --------------------------------------------------------------------------- #
# (de)serialization helpers — state stays plain-JSON, objects live per-node
# --------------------------------------------------------------------------- #

def _brief_to_dict(b) -> dict:
    return {
        "keyword": b.keyword, "intent": b.intent,
        "title_options": b.title_options, "meta_title": b.meta_title,
        "meta_description": b.meta_description,
        "secondary_keywords": b.secondary_keywords, "outline": b.outline,
        "entities": b.entities, "faqs": b.faqs,
        "internal_links": b.internal_links, "word_target": b.word_target,
        "grounded_keywords": b.grounded_keywords, "source": b.source,
        "gap": _gap_to_dict(b.gap) if b.gap else None,
    }


def _gap_to_dict(g) -> dict:
    return {
        "keyword": g.keyword, "source": g.source,
        "common_subtopics": g.common_subtopics, "content_gaps": g.content_gaps,
        "faq_questions": g.faq_questions, "recommended_outline": g.recommended_outline,
    }


def _gap_from_dict(d: dict | None):
    if not d:
        return None
    from .research.gap import GapResult
    return GapResult(
        keyword=d.get("keyword", ""), source=d.get("source", "raw"),
        common_subtopics=d.get("common_subtopics", []),
        content_gaps=d.get("content_gaps", []),
        faq_questions=d.get("faq_questions", []),
        recommended_outline=d.get("recommended_outline", []),
    )


def _brief_from_dict(d: dict):
    from .content.brief import Brief
    b = Brief(keyword=d["keyword"])
    for k, v in d.items():
        if k == "gap":
            b.gap = _gap_from_dict(v)
        elif hasattr(b, k):
            setattr(b, k, v)
    return b


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #

def research_node(state: SeoState) -> dict:
    from .research.keywords import research_keywords
    r = research_keywords(state["keyword"], cluster=True, max_keywords=80)
    return {
        "keywords": r.keywords,
        "clusters": [{"name": c.name, "intent": c.intent, "primary": c.primary,
                      "keywords": c.keywords} for c in r.clusters],
    }


def gap_node(state: SeoState) -> dict:
    from .research.gap import analyze_gap
    g = analyze_gap(state["keyword"])
    return {"gap": _gap_to_dict(g)}


def brief_node(state: SeoState) -> dict:
    from .content.brief import build_brief
    from .research.keywords import ResearchResult
    research = ResearchResult(seed=state["keyword"], keywords=state.get("keywords", []))
    brief = build_brief(state["keyword"], research=research,
                        gap=_gap_from_dict(state.get("gap")))
    return {"brief": _brief_to_dict(brief)}


def write_node(state: SeoState) -> dict:
    from .content.refine import refine_article
    from .content.writer import write_article
    from .render import save_article_html

    brief = _brief_from_dict(state["brief"])
    if state.get("refine", True):
        rr = refine_article(brief)
        art, improved = rr.article, rr.improved
        iterations = [{"n": i.n, "onpage": f"{i.onpage_passed}/{i.onpage_total}",
                       "verdict": i.verdict, "issues": i.issues} for i in rr.iterations]
        p, t = rr.final_check
    else:
        art, improved, iterations = write_article(brief), False, []
        from .content.writer import onpage_selfcheck
        from .render import article_html
        chk = onpage_selfcheck(article_html(art))
        p, t = chk["passed"], chk["total"]

    path = save_article_html(art)
    return {"article_path": str(path), "words": len(art.markdown.split()),
            "onpage": f"{p}/{t}", "iterations": iterations, "improved": improved}


def publish_gate(state: SeoState) -> dict:
    decision = interrupt({
        "type": "approval_required",
        "action": "publish",
        "keyword": state["keyword"],
        "article": state.get("article_path", ""),
        "onpage": state.get("onpage", ""),
        "question": "Məqalə nəşrə hazırdır. Dərc edilsin? (approve/reject)",
    })
    approved = str(decision).strip().lower() in {
        "approve", "approved", "yes", "ok", "y", "he", "hə", "beli", "bəli", "təsdiq",
    }
    return {"approved": approved}


def publish_node(state: SeoState) -> dict:
    # Publisher wiring (Postiz / CMS API) is a separate arc — see seo/ROADMAP.md.
    # The gate above is the contract; this node records the approved intent.
    return {"published": True,
            "result": "Təsdiqləndi. (Publisher inteqrasiyası ROADMAP-dədir — fayl əllə dərc edilməlidir.)"}


def skip_publish_node(state: SeoState) -> dict:
    if state.get("publish") and not state.get("approved"):
        return {"published": False, "result": "Nəşr rədd edildi — məqalə faylda qalır."}
    return {"published": False, "result": "Nəşr istənilmədi — məqalə faylda hazırdır."}


def remember_node(state: SeoState) -> dict:
    _RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "keyword": state.get("keyword"),
        "use_serp": state.get("use_serp"),
        "onpage": state.get("onpage"),
        "words": state.get("words"),
        "improved": state.get("improved"),
        "published": state.get("published"),
        "article": state.get("article_path"),
    }
    with _RUNS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {}


# --------------------------------------------------------------------------- #
# Routing + build
# --------------------------------------------------------------------------- #

def _after_research(state: SeoState) -> str:
    return "gap" if state.get("use_serp") else "brief"


def _after_write(state: SeoState) -> str:
    return "publish_gate" if state.get("publish") else "skip_publish"


def _after_gate(state: SeoState) -> str:
    return "publish" if state.get("approved") else "skip_publish"


def build_graph(checkpointer=None):
    g = StateGraph(SeoState)
    g.add_node("research", research_node)
    g.add_node("gap", gap_node)
    g.add_node("brief", brief_node)
    g.add_node("write", write_node)
    g.add_node("publish_gate", publish_gate)
    g.add_node("publish", publish_node)
    g.add_node("skip_publish", skip_publish_node)
    g.add_node("remember", remember_node)

    g.add_edge(START, "research")
    g.add_conditional_edges("research", _after_research, {"gap": "gap", "brief": "brief"})
    g.add_edge("gap", "brief")
    g.add_edge("brief", "write")
    g.add_conditional_edges("write", _after_write,
                            {"publish_gate": "publish_gate", "skip_publish": "skip_publish"})
    g.add_conditional_edges("publish_gate", _after_gate,
                            {"publish": "publish", "skip_publish": "skip_publish"})
    g.add_edge("publish", "remember")
    g.add_edge("skip_publish", "remember")
    g.add_edge("remember", END)
    return g.compile(checkpointer=checkpointer)


def _checkpointer() -> SqliteSaver:
    _CKPT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CKPT_DB), check_same_thread=False)
    cp = SqliteSaver(conn)
    try:
        cp.setup()
    except Exception:  # noqa: BLE001 — newer versions auto-setup
        pass
    return cp


def run(keyword: str, *, use_serp: bool = False, refine: bool = True,
        publish: bool = False, thread_id: str | None = None) -> dict:
    """Run the pipeline. Returns final state, or {'__interrupt__': ..., 'thread_id': ...}
    when paused at the publish gate."""
    app = build_graph(_checkpointer())
    tid = thread_id or f"seo-{int(time.time() * 1000)}"
    cfg = {"configurable": {"thread_id": tid}}
    out = app.invoke({"keyword": keyword, "use_serp": use_serp,
                      "refine": refine, "publish": publish}, cfg)
    if "__interrupt__" in out:
        return {"__interrupt__": out["__interrupt__"][0].value, "thread_id": tid}
    out["thread_id"] = tid
    return out


def resume(thread_id: str, decision: str) -> dict:
    """Resume a paused thread with an approval decision."""
    app = build_graph(_checkpointer())
    cfg = {"configurable": {"thread_id": thread_id}}
    out = app.invoke(Command(resume=decision), cfg)
    out["thread_id"] = thread_id
    return out
