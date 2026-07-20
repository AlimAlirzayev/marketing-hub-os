"""The brain's governed door for starting heavy background work.

"The model is the router" (operator directive 2026-07-20): the conversational
Claude brain decides when a turn deserves the standing crew workforce and
summons it HERE as a tool call — instead of keyword lists hijacking turns
before the brain sees them (4 keyword misroutes in 3 days forced this).

The summon is ASYNC by design: it only enqueues a durable job on the proven
explicit "/crew" rail (gateway/executor._wants_crew), the worker runs it and
delivers the deliverable to the owner's Telegram as a separate message. So the
chat turn stays fast, the bridge timeout can never truncate crew work, and the
crew job itself never re-enters the bridge (no recursion).

Usage (allowlisted for bridge turns in claude_bridge._HANDS_TOOLS):
    python3 -m gateway.summon crew "<goal>"            # enqueue for the crew
    python3 -m gateway.summon crew "<goal>" --dry-run  # validate only
Prints one Azerbaijani line the brain can relay to the operator verbatim.
"""

from __future__ import annotations

import os
import sys

from ._bootstrap import load_env

load_env()

_KINDS = ("crew",)
_MIN_GOAL = 12    # shorter than this is not a heavy deliverable goal
_MAX_GOAL = 600   # longer than this is a prompt-injection / runaway risk


def _owner() -> str | None:
    """The delivery address. TELEGRAM_OWNER_CHAT_ID is canonical (see bot.py);
    GATEWAY_OWNER_ID honored as the legacy fleet name."""
    for var in ("TELEGRAM_OWNER_CHAT_ID", "GATEWAY_OWNER_ID"):
        val = (os.getenv(var) or "").strip()
        if val:
            return val
    return None


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    if len(args) < 2 or args[0] not in _KINDS:
        print(f'usage: python3 -m gateway.summon {"|".join(_KINDS)} "<goal>" [--dry-run]')
        return 2
    goal = " ".join(args[1:]).replace("\n", " ").strip()
    if not (_MIN_GOAL <= len(goal) <= _MAX_GOAL):
        print(f"rədd: məqsəd {_MIN_GOAL}-{_MAX_GOAL} simvol aralığında olmalıdır (indi {len(goal)}).")
        return 2
    owner = _owner()
    if not owner:
        print("rədd: TELEGRAM_OWNER_CHAT_ID qurulmayıb — nəticəni çatdıracaq ünvan yoxdur.")
        return 2
    task = f"/crew {goal}"
    if dry:
        print(f"quru sınaq OK: '{task}' → owner {owner} (növbəyə salınmadı)")
        return 0
    from . import mic
    job_id = mic.speak(task, source="telegram", chat_id=owner)
    print(f"✅ Krew işə salındı (iş #{job_id}). Nəticə hazır olanda ayrıca mesajla gələcək "
          f"(adətən 3-6 dəqiqə).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
