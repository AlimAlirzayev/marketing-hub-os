"""Xalq Insurance Digital OS - Jarvis bridge.

Connects the Jarvis voice assistant to the CrewAI crews. Jarvis recognizes a
spoken intent and calls ``dispatch_from_jarvis`` with a normalized intent name
and a payload; this module routes it to the matching crew.
"""

from __future__ import annotations

from typing import Any

from crews import business_crew, developer_crew, marketing_crew

# Maps a Jarvis intent to the crew module that handles it.
_INTENT_CREWS = {
    "marketing": marketing_crew,
    "campaign": marketing_crew,
    "business": business_crew,
    "leads": business_crew,
    "sales": business_crew,
    "developer": developer_crew,
    "code": developer_crew,
    "deploy": developer_crew,
}


def resolve_crew(intent: str):
    """Return the crew module for an intent, or None if unmatched."""
    return _INTENT_CREWS.get(intent.lower().strip())


def dispatch_from_jarvis(intent: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Route a voice intent from Jarvis to the correct crew.

    Parameters
    ----------
    intent:
        Normalized intent keyword recognized by Jarvis (e.g. "marketing").
    payload:
        Structured data from the voice command; expects a "brief" key with
        the free-text task description.

    Returns
    -------
    A result dict with the resolved domain and crew status. The crew is built
    but not kicked off here - that happens once LLM providers are wired.
    """
    crew_module = resolve_crew(intent)
    if crew_module is None:
        return {
            "status": "unrecognized_intent",
            "intent": intent,
            "hint": f"known intents: {sorted(_INTENT_CREWS)}",
        }

    brief = payload.get("brief", "")
    crew = crew_module.build_crew(brief=brief)

    # TODO: call crew.kickoff() once router LLM wiring is complete.
    return {
        "status": "crew_ready",
        "intent": intent,
        "domain": crew_module.__name__.split(".")[-1],
        "agent_count": len(crew.agents),
        "brief": brief,
    }


if __name__ == "__main__":
    demo = dispatch_from_jarvis("marketing", {"brief": "draft 3 LinkedIn posts"})
    print(demo)
