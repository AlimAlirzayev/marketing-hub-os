"""gateway/brain.py — the system's single resilient quality brain.

ONE entry point, ONE policy, used everywhere the system THINKS (conversational
answers, crew synthesis, digests, planning). The operator's rule (2026-07-19):
the DEFAULT brain is Claude — the strongest/latest model FIRST, stepping DOWN the
Claude model ladder as rungs cap out, and only THEN falling to the other providers.
That whole Claude ladder + two-account rotation already lives in gateway.claude_bridge
(_full_ladder: claude-fable-5 -> claude-sonnet-5 -> ... -> claude-haiku); the free
cascade (Gemini -> Groq -> ...) lives in orchestrator.router + gateway.llm. This
module is the thin seam that ties them into ONE call so no caller re-implements the
fallback and no single provider stopping ever stops the work:

    answer(prompt, system=None, prefer="claude", timeout=120) -> (text, model_label)

  prefer="claude" (default): the full Claude ladder first, free cascade only when
                             EVERY Claude rung/account is capped.
  prefer="free":  skip Claude entirely (cheap mechanical steps like classification
                  or routing, so bulk work never burns the subscription cap).

Never raises: a caller always gets the best answer currently reachable, plus a
label naming who answered (claude:<model> | <provider>/<model>) for transparency —
so the operator can always see which brain handled a request.
"""

from __future__ import annotations


def answer(prompt: str, system: str | None = None,
           prefer: str = "claude", timeout: int = 120) -> tuple[str, str]:
    """Best reachable answer, resilient across providers. Returns (text, model)."""
    if prefer != "free":
        try:
            from gateway import claude_bridge
            if claude_bridge.is_available():
                text, model = claude_bridge.complete(prompt, system=system, timeout=timeout)
                if text and text.strip():
                    return text.strip(), f"claude:{model}"
        except Exception:
            pass  # every Claude rung/account capped or unauthed -> free cascade below
    try:
        from gateway import llm
        from orchestrator.router import route
        choice = route(prompt)
        text, used = llm.complete(choice, prompt, system=system)
        return (text or "").strip(), f"{used.provider}/{used.model}"
    except Exception as exc:  # never crash the caller
        return f"[brain error] {type(exc).__name__}: {exc}", "none"
