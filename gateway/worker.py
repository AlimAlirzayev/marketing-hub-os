"""The single background executor.

Loops forever: claim the oldest queued job, run it, store the result, and
notify the originating Telegram chat (if any). One job's failure never kills
the worker -- it's recorded and the loop moves on.

Run it (keep this process alive; this is the "background" in background agent):
    python -m gateway.worker
"""

from __future__ import annotations

import re
import threading
import time
import traceback
from pathlib import Path

from ._bootstrap import load_env
from . import knowledge, mic, queue, sense, skills, telegram, voice
from .executor import execute
from .contracts import ExecutionOutcome

load_env()

_IDLE_SLEEP = 2.0  # seconds to wait when the queue is empty

# Executor results carry a leading `_[label]_` source tag (which model/mode
# produced this). The tag is for the STORES (panel + memory render it as a
# small source chip) — a human in Telegram must never see it raw.
_SOURCE_TAG = re.compile(r"^_\[([^\]\n]*)\]_\s*")


def _split_source_tag(result: str) -> tuple[str | None, str]:
    """Return (label, clean_text) — label is None when the result carries no tag."""
    m = _SOURCE_TAG.match(result or "")
    if not m:
        return None, result
    return m.group(1), result[m.end():]


def _notify(job: queue.Job, text: str) -> bool:
    """Deliver the result back to its source. CLI jobs just rely on the DB."""
    if job.source == "telegram" and job.chat_id and telegram.is_configured():
        try:
            telegram.send_message(job.chat_id, text)
            return True
        except Exception as exc:  # delivery failure must not lose the result
            print(f"[worker] notify failed for job {job.id}: {exc}")
    return False


def _progress(job: queue.Job, text: str, *, buttons=None) -> None:
    """Best-effort edit of the one durable Telegram progress card."""
    try:
        queue.set_progress(job.id, text)
    except Exception:
        pass
    if not (
        job.source == "telegram"
        and job.chat_id
        and job.telegram_status_message_id
        and telegram.is_configured()
    ):
        return
    try:
        telegram.edit_status(
            job.chat_id,
            job.telegram_status_message_id,
            text,
            buttons=buttons,
        )
    except Exception as exc:
        print(f"[worker] progress edit failed for job {job.id}: {exc}")


def _cancel_buttons(job_id: int):
    return [[("✕ Dayandır", f"job:cancel:{job_id}")]]


class _TelegramProgressRelay:
    """Debounce executor events into one quiet Telegram progress card."""

    def __init__(self, job: queue.Job, interval: float = 2.5):
        self.job = job
        self.interval = interval
        self._pending: str | None = None
        self._last_edit = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._unsubscribe = None
        self._thread: threading.Thread | None = None

    def _on_event(self, event: dict) -> None:
        data = event.get("data") or {}
        if event.get("kind") != "progress" or str(data.get("job")) != str(self.job.id):
            return
        summary = str(event.get("summary") or "").strip()
        if summary:
            with self._lock:
                self._pending = summary

    def _run(self) -> None:
        while not self._stop.wait(0.25):
            with self._lock:
                pending = self._pending
            if not pending or time.time() - self._last_edit < self.interval:
                continue
            current = queue.get(self.job.id)
            if current and current.cancel_requested:
                with self._lock:
                    self._pending = None
                continue
            _progress(self.job, pending, buttons=_cancel_buttons(self.job.id))
            self._last_edit = time.time()
            with self._lock:
                if self._pending == pending:
                    self._pending = None

    def start(self) -> None:
        self._unsubscribe = sense.subscribe(self._on_event)
        self._thread = threading.Thread(
            target=self._run,
            name=f"telegram-progress-{self.job.id}",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)


def _close_progress(job: queue.Job, delivered: bool) -> None:
    """Delete a completed draft, or keep an honest delivery-failure marker."""
    if not (job.chat_id and job.telegram_status_message_id):
        return
    try:
        if delivered:
            telegram.delete_message(job.chat_id, job.telegram_status_message_id)
        else:
            telegram.edit_status(
                job.chat_id,
                job.telegram_status_message_id,
                "⚠️ Nəticə saxlanıldı, amma Telegram çatdırılması alınmadı. "
                "Hub → İş masasında nəticəni aça bilərsiniz.",
            )
    except Exception as exc:
        print(f"[worker] progress close failed for job {job.id}: {exc}")


# Deliverable file types worth pushing to the chat as real documents. The .md
# result artifact is skipped — it just repeats the text already sent.
_DELIVER_SUFFIXES = {".zip", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
                     ".mp4", ".mp3", ".wav", ".ogg", ".html", ".csv", ".pptx", ".docx"}
_DELIVER_ROOT = (Path(__file__).resolve().parent.parent / "output" / "jobs").resolve()


def _safe_deliverable(path: str) -> Path | None:
    """Resolve an artifact only inside the governed job-output tree."""
    try:
        candidate = Path(path).resolve(strict=True)
        if candidate.is_file() and candidate.is_relative_to(_DELIVER_ROOT):
            return candidate
    except (OSError, RuntimeError, ValueError):
        pass
    return None


def _deliver_files(job: queue.Job, artifacts: list[str] | None) -> None:
    """Hand built deliverables to the owner as downloadable Telegram documents."""
    if not (job.source == "telegram" and job.chat_id and telegram.is_configured()):
        return
    for path in artifacts or []:
        try:
            candidate = _safe_deliverable(path)
            if candidate and candidate.suffix.lower() in _DELIVER_SUFFIXES:
                telegram.send_document(job.chat_id, str(candidate), caption=candidate.name)
        except Exception as exc:
            print(f"[worker] file delivery failed for job {job.id} ({path}): {exc}")


def run_once() -> bool:
    """Process one job if available. Returns True if a job was handled."""
    expired = queue.expire_approvals()
    for expired_id in expired:
        expired_job = queue.get(expired_id)
        if expired_job:
            _progress(
                expired_job,
                "⌛ Təsdiq müddəti bitdi — əməliyyat icra olunmadı.",
            )
    job = queue.claim_next()
    if job is None:
        return bool(expired)

    print(f"[worker] running job {job.id} ({job.source}): {job.task[:80]!r}")
    _progress(
        job,
        "⚙️ İcra başladı — agent planlayır və alətləri işə salır.",
        buttons=_cancel_buttons(job.id),
    )
    if job.source == "telegram" and job.chat_id and telegram.is_configured():
        try:  # "typing..." while the job runs — the chat feels alive, not queued
            telegram.send_chat_action(job.chat_id, "typing")
        except Exception:
            pass
    relay = _TelegramProgressRelay(job)
    relay.start()
    try:
        out = ExecutionOutcome.model_validate(execute(job))
        queue.cancellation_checkpoint(job.id)
    except queue.JobCancelled:
        relay.close()
        queue.mark_cancelled(job.id)
        _progress(job, "✕ Dayandırıldı — növbəti təhlükəsiz checkpoint-də icra kəsildi.")
        sense.emit("job", f"#{job.id} cancelled ({job.source})")
        return True
    except Exception as exc:
        relay.close()
        err = f"{exc}\n{traceback.format_exc()}"
        queue.fail(job.id, err)
        print(f"[worker] job {job.id} FAILED: {exc}")
        sense.emit("job", f"#{job.id} FAILED ({job.source})", {"error": str(exc)[:120]})
        delivered = _notify(job, f"⚠️ İş #{job.id} alınmadı: {exc}")
        _close_progress(job, delivered)
        return True
    else:
        relay.close()
    try:
        if out.status == "failure":
            queue.fail(job.id, out.result)
            print(f"[worker] job {job.id} FAILED ({out.error_code})")
            sense.emit("job", f"#{job.id} FAILED ({job.source})", {
                "error_code": out.error_code,
                "retryable": out.retryable,
            })
            delivered = _notify(job, out.result)
            _close_progress(job, delivered)
            return True
        # Outward-facing action -> the job parks at the human checkpoint instead
        # of completing. The operator decides via /approve or /reject (Telegram
        # or the control panel); approval re-queues it with approved=1.
        if out.needs_approval:
            if not queue.park_for_approval(job.id, "outward_action checkpoint"):
                queue.cancellation_checkpoint(job.id)
                raise RuntimeError("job could not enter approval checkpoint")
            print(f"[worker] job {job.id} parked for operator approval")
            buttons = [[
                ("✅ Təsdiqlə", f"job:approve:{job.id}"),
                ("🚫 İmtina", f"job:reject:{job.id}"),
            ]]
            if job.telegram_status_message_id:
                _progress(
                    job,
                    "🛡️ Təsdiq lazımdır\n\n"
                    + out.result[:3400]
                    + f"\n\n30 dəqiqə ərzində seçin. Əl ilə: /approve {job.id} və ya /reject {job.id}",
                    buttons=buttons,
                )
            else:
                _notify(job, out.result)
            return True
        if not queue.complete(job.id, out.result, out.artifacts):
            queue.cancellation_checkpoint(job.id)
            raise RuntimeError("job could not complete from running state")
        print(f"[worker] job {job.id} done -> {out.artifacts}")
        sense.emit("job", f"#{job.id} done ({job.source})", {"task": job.task[:80]})
        # The stored result keeps its `_[label]_` tag (the panel renders it as a
        # source chip); the HUMAN delivery must read like ONE continuous
        # conversation, not a ticket system. Chat turns AND work results both
        # arrive as plain teammate text — no "İş #N hazırdır" header, no job
        # number (the owner wants Telegram to feel like the Claude chat, where a
        # result is just presented). The label still drives voice + memory below.
        label, clean = _split_source_tag(out.result)
        delivered = _notify(job, clean)
        _close_progress(job, delivered)
        # Voice in -> voice out: a job that arrived as a voice note is answered
        # with an Azerbaijani voice note too (the text is already delivered above,
        # so a TTS failure never costs the reply). Only conversational turns are
        # spoken; long work deliverables stay text.
        if (voice.replies_enabled() and label and label.startswith("chat:")
                and job.source == "telegram" and job.chat_id
                and voice.take_voice_job(job.id)):
            try:
                audio = voice.synthesize(clean)
                if audio:
                    telegram.send_voice(job.chat_id, audio)
            except Exception as exc:
                print(f"[worker] voice reply failed for job {job.id}: {exc}")
        _deliver_files(job, out.artifacts)
        # Record the exchange into the shared hierarchical memory (blackboard),
        # keyed by the conversation thread (Telegram chat). CLI jobs have no chat
        # and are skipped. Guarded — memory must never delay or break delivery.
        try:
            # Record into the ONE shared conversation (mic thread), tagged with
            # the source, so every microphone's turns land in the same memory —
            # not fragmented per chat id.
            thread = mic.thread_for(job)
            knowledge.record_turn(thread, "user", f"[{job.source}] {job.task}")
            knowledge.record_turn(thread, "assistant", out.result)
        except Exception as exc:
            print(f"[worker] memory record skipped for job {job.id}: {exc}")
        # Learn from the finished job AFTER delivery, so the brain never delays
        # the user's result. Guarded + opt-out; failures here are swallowed.
        try:
            n = knowledge.reflect_job(job.task, out.result)
            if n:
                print(f"[worker] job {job.id} -> {n} lesson(s) queued for review")
        except Exception as exc:
            print(f"[worker] reflect skipped for job {job.id}: {exc}")
        # Hermes-style: turn a successful WORK job into a reusable skill card the
        # work lanes reuse next time. Also post-delivery + guarded (never blocks).
        try:
            slug = skills.learn_from_job(job.task, out.result)
            if slug:
                print(f"[worker] job {job.id} -> learned skill '{slug}'")
        except Exception as exc:
            print(f"[worker] skill learn skipped for job {job.id}: {exc}")
    except queue.JobCancelled:
        queue.mark_cancelled(job.id)
        _progress(job, "✕ Dayandırıldı — növbəti təhlükəsiz checkpoint-də icra kəsildi.")
        sense.emit("job", f"#{job.id} cancelled ({job.source})")
    except Exception as exc:
        err = f"{exc}\n{traceback.format_exc()}"
        queue.fail(job.id, err)
        print(f"[worker] job {job.id} FAILED: {exc}")
        sense.emit("job", f"#{job.id} FAILED ({job.source})", {"error": str(exc)[:120]})
        delivered = _notify(job, f"⚠️ İş #{job.id} alınmadı: {exc}")
        _close_progress(job, delivered)
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
