"""DEPRECATED — superseded by ``gateway/council.py``.

These CrewAI crews (marketing / business / developer) and ``jarvis_bridge`` are
unwired skeletons: ``crew.kickoff()`` is never called and they depend on CrewAI,
which is deliberately NOT installed on this locked-down machine.

The LIVE multi-agent layer is ``gateway/council.py`` — a zero-budget,
subscriber-CLI council (Codex + Claude + Gemini) that actually consults in
parallel, synthesizes a decision, and executes. See ``DEPRECATED.md``.

Kept (not deleted) for reference and a possible CrewAI-free reimplementation on
the council pattern. Importing this package emits a DeprecationWarning.
"""

import warnings

warnings.warn(
    "orchestrator.crews is deprecated; the live multi-agent layer is gateway.council "
    "(see orchestrator/crews/DEPRECATED.md).",
    DeprecationWarning,
    stacklevel=2,
)
