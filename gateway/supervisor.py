"""Always-on supervisor — the single 24/7 entrypoint for the autonomous agent.

Keeps the three long-running loops alive in one process, each restarted on crash:
  * worker    — executes queued jobs (gateway.worker.run_once)
  * scheduler — enqueues due recurring jobs (gateway.scheduler.run_pending)
  * bot       — Telegram intake long-poll (gateway.bot.main), only if configured

This is what makes the system *always-on* rather than "alive only while you keep a
terminal open": run ``python -m gateway.supervisor`` on whatever host you choose
(personal PC overnight, a free micro-VPS, etc.) and the agent keeps receiving,
scheduling, and executing on its own. The *where it runs* is your infra choice;
the *staying alive* is handled here.

No new dependencies: stdlib threads + the existing modules.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from ._bootstrap import load_env
from . import queue, scheduler, sense, telegram, worker

load_env()

_ROOT = Path(__file__).resolve().parent.parent
_stop = threading.Event()
_SCHED_TICK = 30.0   # seconds between schedule checks
_WORKER_IDLE = 2.0   # seconds to wait when the queue is empty
# Periodic engine sync for the always-on host: a 24/7 supervisor never reboots,
# so without this it would only learn about the other machine's pushed updates
# when a human said so. Minutes between checks; 0 disables.
_SYNC_MIN = float(os.getenv("ENGINE_SYNC_MIN", "60"))


def _supervise(name: str, step, idle: float) -> None:
    """Run ``step`` forever. step() returns True if it did work (loop again
    immediately), False if idle (wait). Any crash is logged and the loop resumes
    after a short backoff — one failure never stops the agent."""
    while not _stop.is_set():
        try:
            did_work = step()
        except Exception as exc:  # noqa: BLE001
            print(f"[supervisor] {name} error: {exc}")
            _stop.wait(2.0)
            continue
        if not did_work:
            _stop.wait(idle)


def _bot_forever() -> None:
    """The Telegram bot has its own blocking long-poll loop; keep restarting it."""
    while not _stop.is_set():
        try:
            bot_main()
        except Exception as exc:  # noqa: BLE001
            print(f"[supervisor] bot error: {exc}")
            _stop.wait(3.0)


def bot_main() -> None:
    from . import bot
    bot.main()


def _sync_once() -> str:
    """Run the shared sync brain (scripts/sync_engine.py); return its summary."""
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "sync_engine.py")],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120,
    )
    return (proc.stdout or proc.stderr or "").strip()


def _announce_if_updated(summary: str) -> bool:
    """If the sync actually pulled new engine commits, tell the owner on Telegram
    ('dostum, yeniliklər gəldi') and log the event. Returns True on an update."""
    if "pulled new engine" not in summary:
        return False
    sense.emit("sync", "engine updated from origin", {"summary": summary[:120]})
    owner = (os.getenv("TELEGRAM_OWNER_CHAT_ID") or "").strip()
    if owner and telegram.is_configured():
        try:
            telegram.send_message(
                owner,
                "🔄 Dostum, o biri sistemdən yeniliklər gəldi — GitHub-dan çəkib "
                f"yerləşdirdim.\n{summary}\n"
                "Qeyd: işləyən proseslər yeni kodu növbəti restartda tam götürür.",
            )
        except Exception as exc:  # announcement must never hurt the loop
            print(f"[supervisor] sync announce failed: {exc}")
    return True


def _sync_forever() -> None:
    """Keep the always-on host current on its own: pull at start, then every
    _SYNC_MIN minutes. Best-effort — a network hiccup never stops the agent."""
    while not _stop.is_set():
        try:
            summary = _sync_once()
            print(f"[supervisor] engine sync: {summary}")
            _announce_if_updated(summary)
        except Exception as exc:  # noqa: BLE001
            print(f"[supervisor] engine sync error: {exc}")
        _stop.wait(max(_SYNC_MIN, 1.0) * 60)


def _start(name: str, target) -> threading.Thread:
    t = threading.Thread(target=target, name=name, daemon=True)
    t.start()
    print(f"[supervisor] started {name}")
    return t


def _singleton_lock() -> socket.socket | None:
    """One supervisor per machine: hold a localhost port as a process-wide lock.
    Lets the launcher blindly 'start supervisor' on every boot — a second copy
    (double Telegram polling, double workers) simply refuses to start."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", int(os.getenv("SUPERVISOR_LOCK_PORT", "8899"))))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main() -> None:
    lock = _singleton_lock()
    if lock is None:
        print("[supervisor] another supervisor is already running on this machine — exiting.")
        return

    queue.init_db()
    scheduler.init_db()
    orphans = queue.recover_stale_running()
    if orphans:
        print(f"[supervisor] recovered {len(orphans)} orphaned running job(s) {orphans} -> re-queued")
    try:
        from brain import blackboard
        blackboard.init()
    except Exception:
        pass

    tg = telegram.is_configured()
    print(f"[supervisor] starting. Telegram intake: {'on' if tg else 'off (CLI/schedule only)'}")

    _start("worker", lambda: _supervise("worker", worker.run_once, _WORKER_IDLE))
    _start("scheduler", lambda: _supervise("scheduler", lambda: bool(scheduler.run_pending()), _SCHED_TICK))
    if tg:
        _start("bot", _bot_forever)
    if _SYNC_MIN > 0:
        _start("engine-sync", _sync_forever)

    print("[supervisor] running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[supervisor] stopping...")
        _stop.set()
        time.sleep(0.3)


if __name__ == "__main__":
    main()
