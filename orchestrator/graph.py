"""Autonomous spine (PoC) — LangGraph StateGraph on top of our free llm_router.

This proves the 2026-honest verdict with code, not words: keep the lean LiteLLM
gateway (`llm_router`) for model calls, and use **LangGraph** only for the part it
is genuinely best at — a *stateful, durable, interruptible* agent graph. It maps
1:1 onto the goals we set:

    intake -> plan -> [risk gate] -> (risky?) human checkpoint -> execute -> remember

- **Checkpointer (SqliteSaver):** every step's state is persisted, so a run can
  crash/resume and survive token/process death — the durability our token-bound
  chat sessions lack.
- **interrupt():** before any risky action (post/send/pay/delete/call) the graph
  *pauses* for human approval — exactly AGENTS.md's "risky actions need checkpoints."
- **llm_router:** the planning/execution thinking runs on FREE models; LangGraph
  only orchestrates. No LangChain LCEL rewrite of what we already have.

Run the demo:  python -m orchestrator.graph
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Command

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_RUNS_LOG = ROOT / "data" / "graph_runs.jsonl"
_CKPT_DB = ROOT / "data" / "graph_checkpoints.sqlite"

# Actions that must never fire autonomously without a human checkpoint. Mirrors
# AGENTS.md ("posting, sending, spending, deleting, ...") in AZ + EN.
_RISKY = (
    "post", "publish", "send", "email", "dm", "tweet", "pay", "spend", "buy",
    "delete", "remove", "deploy", "call", "phone",
    "paylaş", "göndər", "öde", "ödə", "sil", "zəng", "yüklə", "yayımla",
)


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    task: str
    plan: str
    model: str
    risk: str          # "safe" | "risky"
    approved: bool
    result: str


# --------------------------------------------------------------------------
# Model access — through our free-first router, never a hardcoded provider.
# --------------------------------------------------------------------------
def _llm(prompt: str, *, system: str = "") -> tuple[str, str]:
    try:
        import llm_router
        text, model = llm_router.complete(prompt, system=system or None, tier="cheap")
        return (text or "").strip(), model
    except Exception as exc:  # noqa: BLE001 — PoC must run even with no key/router
        return f"[stub plan — router unavailable: {str(exc)[:60]}]", "stub"


def _classify_risk(task: str) -> str:
    # Classify on the TASK (the action the user asked for), NOT the LLM plan prose
    # — a plan for "summarize ad performance" mentions "spend" as data, not as a
    # spending action. PoC heuristic; production would use a structured action type.
    low = task.lower()
    return "risky" if any(w in low for w in _RISKY) else "safe"


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------
def plan_node(state: AgentState) -> dict:
    task = state["task"]
    # Recall before acting: inject the shared, git-traveling context so the planner
    # honors decisions/direction made on any machine or channel.
    system = "You are the planner of an autonomous marketing OS. Be concise."
    try:
        import shared_memory
        ctx = shared_memory.context()
        if ctx:
            system += "\n\nShared project context (honor it):\n" + ctx
    except Exception:  # noqa: BLE001 — planning must work even if memory is absent
        pass
    plan, model = _llm(
        f"Make a short, concrete execution plan (3-5 bullet steps) for this task. "
        f"No preamble.\n\nTASK: {task}",
        system=system,
    )
    return {"plan": plan, "model": model, "risk": _classify_risk(task)}


def human_checkpoint(state: AgentState) -> dict:
    # Pauses the graph; the value is surfaced to the operator. Resume with
    # Command(resume="approve"/"reject"). On resume this node re-runs and
    # interrupt() returns the supplied decision.
    decision = interrupt(
        {
            "type": "approval_required",
            "task": state["task"],
            "plan": state["plan"],
            "risk": state["risk"],
            "question": "Risky action (post/send/pay/delete/call). Approve? (approve/reject)",
        }
    )
    approved = str(decision).strip().lower() in {
        "approve", "approved", "yes", "ok", "y", "he", "hə", "beli", "bəli", "təsdiq",
    }
    return {"approved": approved}


def execute_node(state: AgentState) -> dict:
    text, model = _llm(
        f"Carry out this task and report the outcome in 2-3 sentences.\n\n"
        f"TASK: {state['task']}\nPLAN:\n{state.get('plan','')}",
        system="You are the executor of an autonomous marketing OS.",
    )
    return {"result": text, "model": model}


def reject_node(state: AgentState) -> dict:
    return {"result": "Rejected at human checkpoint — not executed."}


def remember_node(state: AgentState) -> dict:
    _RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "task": state.get("task"),
        "risk": state.get("risk"),
        "approved": state.get("approved"),
        "model": state.get("model"),
        "result": (state.get("result") or "")[:500],
    }
    with _RUNS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {}


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------
def _after_plan(state: AgentState) -> str:
    return "human_checkpoint" if state.get("risk") == "risky" else "execute"


def _after_checkpoint(state: AgentState) -> str:
    return "execute" if state.get("approved") else "reject"


# --------------------------------------------------------------------------
# Graph builder
# --------------------------------------------------------------------------
def build_graph(checkpointer):
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("human_checkpoint", human_checkpoint)
    g.add_node("execute", execute_node)
    g.add_node("reject", reject_node)
    g.add_node("remember", remember_node)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", _after_plan, {"human_checkpoint": "human_checkpoint", "execute": "execute"})
    g.add_conditional_edges("human_checkpoint", _after_checkpoint, {"execute": "execute", "reject": "reject"})
    g.add_edge("execute", "remember")
    g.add_edge("reject", "remember")
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


def run(task: str, thread_id: str | None = None) -> dict:
    """Run a task through the graph. Returns the final state, or an interrupt
    marker (dict with '__interrupt__') when it pauses for human approval."""
    cp = _checkpointer()
    app = build_graph(cp)
    cfg = {"configurable": {"thread_id": thread_id or f"t-{int(time.time()*1000)}"}}
    out = app.invoke({"task": task}, config=cfg)
    return out, cfg


def resume(decision: str, cfg: dict) -> dict:
    """Resume a paused graph after a human approval decision."""
    cp = _checkpointer()
    app = build_graph(cp)
    return app.invoke(Command(resume=decision), config=cfg)


# --------------------------------------------------------------------------
# Demo: a safe task runs straight through; a risky one pauses then resumes.
# --------------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    print("=== SAFE task (should run straight through) ===")
    out, _ = run("Summarize our Q2 ad performance into 3 bullet points.")
    print("risk:", out.get("risk"), "| model:", out.get("model"))
    print("result:", (out.get("result") or "")[:200])

    print("\n=== RISKY task (should pause at human checkpoint) ===")
    out, cfg = run("Publish the new KASKO promo video to YouTube and post it on Instagram.")
    interrupts = out.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        print("PAUSED for approval. risk:", payload.get("risk"))
        print("question:", payload.get("question"))
        print("\n-> resuming with 'approve' ...")
        final = resume("approve", cfg)
        print("approved:", final.get("approved"), "| model:", final.get("model"))
        print("result:", (final.get("result") or "")[:200])
    else:
        print("Did NOT pause (unexpected). risk:", out.get("risk"))

    print(f"\nRuns logged to: {_RUNS_LOG}")
