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

import threading
import time

from ._bootstrap import load_env
from . import queue, scheduler, telegram, worker

load_env()

_stop = threading.Event()
_SCHED_TICK = 30.0   # seconds between schedule checks
_WORKER_IDLE = 2.0   # seconds to wait when the queue is empty


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


def _start(name: str, target) -> threading.Thread:
    t = threading.Thread(target=target, name=name, daemon=True)
    t.start()
    print(f"[supervisor] started {name}")
    return t


def main() -> None:
    queue.init_db()
    scheduler.init_db()
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
