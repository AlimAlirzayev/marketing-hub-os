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
from . import engine_sync, queue, scheduler, sense, telegram, worker

load_env()

_ROOT = Path(__file__).resolve().parent.parent
_stop = threading.Event()
_SCHED_TICK = 30.0   # seconds between schedule checks
_WORKER_IDLE = 2.0   # seconds to wait when the queue is empty
# Periodic engine sync for the always-on host: a 24/7 supervisor never reboots,
# so without this it would only learn about the other machine's pushed updates
# when a human said so. Minutes between checks; 0 disables.
_SYNC_MIN = float(os.getenv("ENGINE_SYNC_MIN", "15"))
_SIGNAL_RADAR_TICK = float(os.getenv("SIGNAL_RADAR_TICK_SECONDS", "3600"))
_SIGNAL_RADAR_ENABLED = os.getenv("SIGNAL_RADAR_ENABLED", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# Service watchdog: health-checks the standing services.json organs and (auto-
# restart ON by default; WATCHDOG_AUTO_RESTART=0 to pause) relaunches a crashed
# one. See gateway.watchdog.
_WATCHDOG_TICK = float(os.getenv("WATCHDOG_TICK_SECONDS", "90"))
_WATCHDOG_ENABLED = os.getenv("WATCHDOG_ENABLED", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# Impact Ledger: the monthly "what the OS did for Xalq" scorecard, delivered on
# its own when a new month turns. Slow tick — it self-gates to once a month.
_IMPACT_TICK = float(os.getenv("IMPACT_LEDGER_TICK_SECONDS", "21600"))  # 6h
_IMPACT_ENABLED = os.getenv("IMPACT_LEDGER_ENABLED", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}


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


def _sync_forever() -> None:
    """Keep the always-on host current on its own: pull at start, then every
    _SYNC_MIN minutes. Delegates to the one canonical brain (gateway.engine_sync)
    that every entry point shares — pull-first, post-pull tripwire, owner announce —
    so nothing drifts. Best-effort: a network hiccup never stops the agent."""
    while not _stop.is_set():
        try:
            summary = engine_sync.refresh(announce=True)
            print(f"[supervisor] engine sync: {summary}")
        except Exception as exc:  # noqa: BLE001
            print(f"[supervisor] engine sync error: {exc}")
        _stop.wait(max(_SYNC_MIN, 1.0) * 60)


def _signal_radar_forever() -> None:
    """Run the read-only public signal radar when due.

    This is research intake only: public sources in, local lab/report artifacts
    out. Provider setup, spending, publishing, connector use, and hardware
    actions still require the normal human approval rails.
    """
    while not _stop.is_set():
        try:
            from . import signal_radar

            summary = signal_radar.run_if_due()
            if not summary.get("skipped"):
                print(f"[supervisor] signal radar: {summary}")
                try:
                    sense.emit("signal-radar", "public signal intake", summary)
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001
            print(f"[supervisor] signal radar error: {exc}")
        _stop.wait(max(_SIGNAL_RADAR_TICK, 60.0))


def _impact_ledger_forever() -> None:
    """Deliver the monthly Xalq Impact Ledger to the owner when a new month turns.
    Self-gating (impact_ledger.run_if_due): a slow tick, but the report is emitted
    exactly once per month. Delivering the owner their own scorecard is an
    owner-facing report like the morning briefing — not a risky outward action."""
    while not _stop.is_set():
        try:
            from . import impact_ledger
            res = impact_ledger.run_if_due()
            if not res.get("skipped"):
                owner = (os.getenv("TELEGRAM_OWNER_CHAT_ID")
                         or os.getenv("GATEWAY_OWNER_ID") or "").strip()
                if owner and telegram.is_configured():
                    telegram.send_message(owner, res["text"])
                try:
                    sense.emit("impact-ledger", f"monthly ledger {res['month']} delivered",
                               {"month": res["month"]})
                except Exception:
                    pass
                print(f"[supervisor] impact ledger delivered {res['month']}")
        except Exception as exc:  # noqa: BLE001
            print(f"[supervisor] impact ledger error: {exc}")
        _stop.wait(max(_IMPACT_TICK, 3600.0))


def _watchdog_forever() -> None:
    """Health-check + (opt-in) heal the standing services.json organs on this
    machine. A crashed uvicorn service currently stays down until a human
    notices; this closes that gap the same way _sync_forever closes the
    engine-drift gap — best-effort, never stops the agent."""
    while not _stop.is_set():
        try:
            from . import watchdog
            r = watchdog.tick()
            if any(r.values()):
                print(f"[supervisor] watchdog: {r}")
        except Exception as exc:  # noqa: BLE001
            print(f"[supervisor] watchdog error: {exc}")
        _stop.wait(max(_WATCHDOG_TICK, 20.0))


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
        s.bind(("127.0.0.1", int(os.getenv("SUPERVISOR_LOCK_PORT", "18999"))))
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
    if _SIGNAL_RADAR_ENABLED:
        _start("signal-radar", _signal_radar_forever)
    if _WATCHDOG_ENABLED:
        _start("watchdog", _watchdog_forever)
    if _IMPACT_ENABLED:
        _start("impact-ledger", _impact_ledger_forever)

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
