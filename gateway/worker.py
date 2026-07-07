"""The single background executor.

Loops forever: claim the oldest queued job, run it, store the result, and
notify the originating Telegram chat (if any). One job's failure never kills
the worker -- it's recorded and the loop moves on.

Run it (keep this process alive; this is the "background" in background agent):
    python -m gateway.worker
"""

from __future__ import annotations

import time
import traceback

from ._bootstrap import load_env
from . import knowledge, queue, sense, telegram
from .executor import execute

load_env()

_IDLE_SLEEP = 2.0  # seconds to wait when the queue is empty


def _notify(job: queue.Job, text: str) -> None:
    """Deliver the result back to its source. CLI jobs just rely on the DB."""
    if job.source == "telegram" and job.chat_id and telegram.is_configured():
        try:
            telegram.send_message(job.chat_id, text)
        except Exception as exc:  # delivery failure must not lose the result
            print(f"[worker] notify failed for job {job.id}: {exc}")


# Deliverable file types worth pushing to the chat as real documents. The .md
# result artifact is skipped — it just repeats the text already sent.
_DELIVER_SUFFIXES = {".zip", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
                     ".mp4", ".mp3", ".wav", ".ogg", ".html", ".csv", ".pptx", ".docx"}


def _deliver_files(job: queue.Job, artifacts: list[str] | None) -> None:
    """Hand built deliverables to the owner as downloadable Telegram documents."""
    if not (job.source == "telegram" and job.chat_id and telegram.is_configured()):
        return
    import os as _os
    for path in artifacts or []:
        try:
            if _os.path.splitext(path)[1].lower() in _DELIVER_SUFFIXES and _os.path.exists(path):
                telegram.send_document(job.chat_id, path, caption=_os.path.basename(path))
        except Exception as exc:
            print(f"[worker] file delivery failed for job {job.id} ({path}): {exc}")


def run_once() -> bool:
    """Process one job if available. Returns True if a job was handled."""
    job = queue.claim_next()
    if job is None:
        return False

    print(f"[worker] running job {job.id} ({job.source}): {job.task[:80]!r}")
    try:
        out = execute(job)
        # Outward-facing action -> the job parks at the human checkpoint instead
        # of completing. The operator decides via /approve or /reject (Telegram
        # or the control panel); approval re-queues it with approved=1.
        if out.get("needs_approval"):
            queue.park_for_approval(job.id, "outward_action checkpoint")
            print(f"[worker] job {job.id} parked for operator approval")
            _notify(job, out["result"])
            return True
        queue.complete(job.id, out["result"], out.get("artifacts"))
        print(f"[worker] job {job.id} done -> {out.get('artifacts')}")
        sense.emit("job", f"#{job.id} done ({job.source})", {"task": job.task[:80]})
        _notify(job, f"✅ Job {job.id} done:\n\n{out['result']}")
        _deliver_files(job, out.get("artifacts"))
        # Record the exchange into the shared hierarchical memory (blackboard),
        # keyed by the conversation thread (Telegram chat). CLI jobs have no chat
        # and are skipped. Guarded — memory must never delay or break delivery.
        try:
            knowledge.record_turn(job.chat_id, "user", job.task)
            knowledge.record_turn(job.chat_id, "assistant", out["result"])
        except Exception as exc:
            print(f"[worker] memory record skipped for job {job.id}: {exc}")
        # Learn from the finished job AFTER delivery, so the brain never delays
        # the user's result. Guarded + opt-out; failures here are swallowed.
        try:
            n = knowledge.reflect_job(job.task, out["result"])
            if n:
                print(f"[worker] job {job.id} -> {n} lesson(s) queued for review")
        except Exception as exc:
            print(f"[worker] reflect skipped for job {job.id}: {exc}")
    except Exception as exc:
        err = f"{exc}\n{traceback.format_exc()}"
        queue.fail(job.id, err)
        print(f"[worker] job {job.id} FAILED: {exc}")
        sense.emit("job", f"#{job.id} FAILED ({job.source})", {"error": str(exc)[:120]})
        _notify(job, f"⚠️ Job {job.id} failed: {exc}")
    return True


def main() -> None:
    queue.init_db()
    orphans = queue.recover_stale_running()
    if orphans:
        print(f"[worker] recovered {len(orphans)} orphaned running job(s) {orphans} -> re-queued")
    tg = "on" if telegram.is_configured() else "off (CLI only)"
    print(f"[worker] started. Telegram delivery: {tg}. Polling queue...")
    while True:
        try:
            if not run_once():
                time.sleep(_IDLE_SLEEP)
        except KeyboardInterrupt:
            print("\n[worker] stopped.")
            break
        except Exception as exc:  # never let the loop die
            print(f"[worker] loop error: {exc}")
            time.sleep(_IDLE_SLEEP)


if __name__ == "__main__":
    main()
