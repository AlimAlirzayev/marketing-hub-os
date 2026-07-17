"""Bridge between the gateway and the Knowledge Core (``brain``).

Keeps the brain strictly optional: if the package is missing, errors, or the
free tier is unavailable, the gateway behaves exactly as it did before. Every
function is guarded and returns a safe empty value instead of raising, so a
learning feature can never take down task execution.

Two directions:
  - recall_context(task) -> str : pull relevant past knowledge to inject into a
    prompt BEFORE execution (the "stand on what we learned" half).
  - reflect_job(task, result)   : distill a finished job into pending lessons
    AFTER execution (the "learn from what we did" half).

Toggles (env):
  BRAIN_RECALL   default on  -- set 0 to disable injection
  BRAIN_REFLECT  default on  -- set 0 to disable auto-reflection
"""

from __future__ import annotations

import contextvars
import os

from ._bootstrap import load_env

load_env()

# The thread (conversation) the current job belongs to. The executor sets this
# once per job, so any downstream code that calls recall_context — including the
# council path (gateway/council.py) which we do not modify — automatically gets
# the full hierarchical thread memory instead of L2-only recall.
_CURRENT_THREAD: contextvars.ContextVar[str | None] = contextvars.ContextVar("thread_id", default=None)


def set_current_thread(thread_id: str | None) -> None:
    _CURRENT_THREAD.set(str(thread_id) if thread_id else None)


def current_thread() -> str | None:
    return _CURRENT_THREAD.get()


def _off(var: str, default: str = "1") -> bool:
    return os.getenv(var, default).lower() in {"0", "false", "no", "off"}


def recall_context(task: str, *, k: int = 4) -> str:
    """Relevant memory for ``task`` as a markdown block, or "".

    If a conversation thread is active, return the full hierarchical blackboard
    (L1 turns + L3 entities + L4 summary + L2 recall); otherwise plain L2 recall.
    """
    if _off("BRAIN_RECALL"):
        return ""
    tid = current_thread()
    if tid:
        try:
            from brain import assemble_context

            return assemble_context(task, tid, k=k)
        except Exception:
            pass
    try:
        from brain import recall_block

        return recall_block(task, k=k)
    except Exception:
        return ""


def augment_system(system: str, task: str, thread_id: str | None = None) -> str:
    """Append self-identity + memory context to a system prompt. The self-card
    (sense.system_card) goes in unconditionally — a brain that doesn't know what
    Ramin-OS contains answers like a generic consultant (observed on Telegram/panel).
    With a thread_id, memory is the full hierarchical blackboard (L1 turns + L3
    entities + L4 summary + L2 recall); without one, plain L2 recall."""
    try:
        from . import sense

        card = sense.system_card()
    except Exception:
        card = ""
    ctx = thread_context(task, thread_id) if thread_id else recall_context(task)
    # Lab yanaşması: yaddaşda tapşırığa uyğun hazır imkan varsa, sistem bunu
    # gizlətmir — operator "labda nə var" bilməlidir və yığım TƏKLİF olunmalıdır.
    lab_hint = (
        "\n\nLAB QAYDASI: yuxarıdakı yaddaş kontekstində bu tapşırığa uyğun hazır "
        "imkan, radar tapıntısı və ya keçmiş dərs varsa, cavabında bunu açıq de "
        "('labımızda bununla bağlı X var') və onları yığıb təhvil verməyi təklif et."
    )
    parts = [system]
    if card:
        parts.append(card)
    if ctx:
        parts.append(f"{ctx}{lab_hint}")
    return "\n\n".join(parts)


def thread_context(task: str, thread_id: str | None, *, k: int = 4) -> str:
    """Hierarchical blackboard context for a conversation thread, or "" on any issue."""
    if _off("BRAIN_RECALL") or not thread_id:
        return recall_context(task, k=k)
    try:
        from brain import assemble_context

        return assemble_context(task, str(thread_id), k=k)
    except Exception:
        return recall_context(task, k=k)


def record_turn(thread_id: str | None, role: str, content: str) -> None:
    """Write one conversation turn into the shared blackboard. Never raises."""
    if _off("BRAIN_RECALL") or not thread_id or not content:
        return
    try:
        from brain import observe

        observe(str(thread_id), role, content)
    except Exception:
        return


def reflect_job(task: str, result: str) -> int:
    """Queue lessons distilled from a finished job. Returns count; never raises."""
    if _off("BRAIN_REFLECT"):
        return 0
    # Don't try to learn from security blocks or error payloads.
    low = (result or "").lower()
    if not result or any(m in low for m in ("[security:", "icra xətası", "sistem yüklənməsi")):
        return 0
    try:
        from brain import reflect

        return len(reflect(task, result, commit=False))
    except Exception:
        return 0
