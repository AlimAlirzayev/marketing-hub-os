"""Deterministic tests for the LangGraph pipeline — no network, no LLM.

Node internals are faked at module level; what we actually test is the graph's
own value: routing (serp on/off), state serialization, the publish interrupt,
and resume with approve/reject on a shared checkpointer.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import seo.graph as gmod


def _fake_nodes():
    """Return patched (originals) and install cheap fakes for the heavy nodes."""
    originals = (gmod.research_node, gmod.gap_node, gmod.brief_node, gmod.write_node)

    def research(state):
        return {"keywords": ["kasko a", "kasko b"], "clusters": []}

    def gap(state):
        return {"gap": {"keyword": state["keyword"], "source": "llm",
                        "common_subtopics": ["s1"], "content_gaps": ["g1"],
                        "faq_questions": ["q1"], "recommended_outline": []}}

    def brief(state):
        # verify the gap dict round-trips into a GapResult when present
        g = gmod._gap_from_dict(state.get("gap"))
        return {"brief": {"keyword": state["keyword"], "intent": "informational",
                          "gap_seen": bool(g and g.content_gaps == ["g1"])}}

    def write(state):
        return {"article_path": "output/seo/fake.html", "words": 1000,
                "onpage": "7/8", "iterations": [], "improved": True}

    gmod.research_node, gmod.gap_node, gmod.brief_node, gmod.write_node = \
        research, gap, brief, write
    return originals


def _restore(originals):
    (gmod.research_node, gmod.gap_node, gmod.brief_node, gmod.write_node) = originals


def _invoke(inputs, cp=None, thread="t1"):
    app = gmod.build_graph(cp or MemorySaver())
    return app.invoke(inputs, {"configurable": {"thread_id": thread}})


def test_safe_flow_completes_without_gate():
    originals = _fake_nodes()
    try:
        out = _invoke({"keyword": "kasko", "use_serp": False, "publish": False})
    finally:
        _restore(originals)
    assert out["article_path"] == "output/seo/fake.html"
    assert out["published"] is False
    assert "__interrupt__" not in out
    assert "gap" not in out                     # serp off -> gap node skipped


def test_serp_routing_includes_gap():
    originals = _fake_nodes()
    try:
        out = _invoke({"keyword": "kasko", "use_serp": True, "publish": False})
    finally:
        _restore(originals)
    assert out["gap"]["content_gaps"] == ["g1"]
    assert out["brief"]["gap_seen"] is True     # gap dict round-tripped to the brief


def test_publish_pauses_then_approve_resumes():
    originals = _fake_nodes()
    cp = MemorySaver()
    try:
        app = gmod.build_graph(cp)
        cfg = {"configurable": {"thread_id": "t-pub"}}
        out = app.invoke({"keyword": "kasko", "use_serp": False, "publish": True}, cfg)
        assert "__interrupt__" in out           # paused at the human gate
        info = out["__interrupt__"][0].value
        assert info["action"] == "publish"
        out2 = app.invoke(Command(resume="approve"), cfg)
    finally:
        _restore(originals)
    assert out2["approved"] is True
    assert out2["published"] is True


def test_publish_reject_keeps_file_unpublished():
    originals = _fake_nodes()
    cp = MemorySaver()
    try:
        app = gmod.build_graph(cp)
        cfg = {"configurable": {"thread_id": "t-rej"}}
        app.invoke({"keyword": "kasko", "use_serp": False, "publish": True}, cfg)
        out = app.invoke(Command(resume="reject"), cfg)
    finally:
        _restore(originals)
    assert out["approved"] is False
    assert out["published"] is False
    assert "rədd" in out["result"]


def test_brief_dict_roundtrip():
    from seo.content.brief import Brief
    from seo.research.gap import GapResult
    b = Brief(keyword="k", intent="commercial", meta_title="T",
              secondary_keywords=["a"], outline=[{"h2": "X", "h3": []}],
              gap=GapResult(keyword="k", content_gaps=["g"]))
    d = gmod._brief_to_dict(b)
    b2 = gmod._brief_from_dict(d)
    assert b2.keyword == "k" and b2.intent == "commercial"
    assert b2.outline == [{"h2": "X", "h3": []}]
    assert b2.gap.content_gaps == ["g"]
