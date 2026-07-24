"""The single microphone — one ordered conversation for every input channel.

The system is ONE entity reached through many microphones: this Claude Code
chat, Telegram, Codex, the control panel. Without a single front door each
channel becomes its own island and the system's memory fragments — the
"pərakəndə giriş / qarışıqlıq" the operator wants gone.

`mic.speak()` is that front door. Every channel calls it, so:
  * ONE shared conversation thread (MIC_THREAD) — the brain answers with the
    full cross-channel history, not a per-channel silo.
  * ONE serialized queue (the durable FIFO job queue, single worker) — strict
    turn-taking: whoever speaks now has taken the mic; the next waits its turn.
  * delivery still returns to whichever channel spoke (Telegram chat / panel / CLI).

So "today you here, tomorrow Telegram, next Codex" is literally one continuous
conversation — each source just takes the mic in its turn.

The conversation lives in the per-deployment blackboard (data/, git-ignored), so
it never travels between the two friend-systems — only the ENGINE does. Each
system keeps its own single microphone.
"""

from __future__ import annotations

from . import queue, sense

# The one conversation thread every microphone shares (per deployment).
MIC_THREAD = "main"


def speak(text: str, *, source: str, chat_id: str | None = None) -> int:
    """Take the mic: enqueue one input from any channel into the single shared
    conversation and return its job id. The turn itself is recorded (under
    MIC_THREAD) by the worker after execution, so history stays unified whether
    the words came from chat, Telegram, Codex or the panel."""
    text = (text or "").strip()
    job_id = queue.submit(text, source=source, chat_id=chat_id)
    sense.emit("mic", f"{source} took the mic -> job #{job_id}", {"task": text[:80]})
    return job_id


def speak_once(
    text: str,
    *,
    source: str,
    chat_id: str | None,
    ingress_key: str,
) -> tuple[int, bool]:
    """Take the mic once for a durable external event.

    Telegram can replay an update after a process crash. Its event identity is
    carried into the queue so that replay returns the original job rather than
    executing the same user request twice.
    """
    text = (text or "").strip()
    job_id, created = queue.submit_once(
        text,
        source=source,
        chat_id=chat_id,
        ingress_key=ingress_key,
    )
    if created:
        sense.emit("mic", f"{source} took the mic -> job #{job_id}", {"task": text[:80]})
    else:
        sense.emit("telegram", f"duplicate ingress ignored -> job #{job_id}")
    return job_id, created


def thread_for(job) -> str:
    """The conversation thread a job belongs to — always the single mic thread,
    so every channel shares one memory (delivery still uses job.chat_id)."""
    return MIC_THREAD
