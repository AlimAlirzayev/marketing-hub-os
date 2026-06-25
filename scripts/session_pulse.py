"""SessionStart hook — inject the live system pulse into every new session.

The reflex that fixes cold-start blindness (the "barber" problem): before an agent
asserts anything, the session opens with the body's CURRENT state — env credentials
(masked), job queue, memory, schedules, git, recent events — read from reality, not
from stale memory. Output goes to stdout, which Claude Code adds to the session
context. Fully guarded: a sensing failure must never block a session from starting.
"""

from __future__ import annotations

import os
import sys

# Make the repo importable regardless of where the hook is invoked from.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> None:
    try:
        from gateway import sense
        board = sense.pulse()
    except Exception as exc:  # never block a session
        print(f"[pulse] live state unavailable: {exc}")
        return
    # Frame it so the model treats it as authoritative current state, not a claim.
    print("LIVE SYSTEM STATE (read now — trust this over memory):")
    print(board)
    # The proactive voice: the advisor's grounded risk/watch findings, so every
    # session opens not just with WHAT IS but with WHAT TO DO NEXT — no LLM call
    # here (kept fast and token-free; run `python -m gateway.advisor` for AI ranking).
    try:
        from gateway import advisor
        findings = [f for f in advisor.observe_state() if f.level in ("risk", "watch")]
        if findings:
            print("\nADVISOR — diqqət tələb edən (proaktiv):")
            for f in findings:
                print(f"  {advisor._LEVEL_LAMP.get(f.level, '·')} {f.title} → {f.suggestion or f.detail}")
    except Exception:
        pass  # advisor is additive; never block a session


if __name__ == "__main__":
    main()
