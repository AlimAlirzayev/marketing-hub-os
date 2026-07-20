"""Service watchdog — the standing organs must heal themselves.

audit_services.py already knows a registered service is down (rows[].up); the
gap this closes: nothing continuously WATCHED for that state, nothing tried to
bring the process back, and nothing told the owner past a manual CLI run. This
runs as a supervisor thread (like signal_radar), reusing the same registry
(services.json) and the same up/down math (audit_services.audit_data) so there
is exactly one truth about what should be running — never a second registry.

Design (mirrors untracked_watch.py — no crying wolf, best-effort, machine-local):
  * only services whose venv EXISTS locally are watched — the same
    "if -not Test-Path $py" gate START_MARKETING_OS.ps1 uses, so a twin that
    doesn't run every organ never chases a service it was never meant to run;
  * a service must be down for WATCHDOG_GRACE_CHECKS consecutive ticks before
    any action — a developer's deliberate bounce (stop it, edit, restart by
    hand) must not race the watchdog;
  * each incident is circuit-broken: after WATCHDOG_MAX_RESTARTS attempts
    inside WATCHDOG_WINDOW_MIN minutes, the watchdog stops trying and pings
    once that it gave up — a crash-looping service must never spin forever;
  * WATCHDOG_AUTO_RESTART defaults to 1 (ON): relaunching a crashed LOCAL
    service is an internal, no-outward-action, circuit-broken heal — exactly
    the operator's "internal work runs itself, outward actions ask" policy —
    so it must not depend on anyone remembering to flip a flag. Set it to 0
    only to pause healing (e.g. while hand-debugging a service);
  * the owner is pinged on Telegram only on a STATE TRANSITION (newly down,
    restarted, gave up, recovered) — never every tick;
  * state is machine-local in data/watchdog_state.json (git-ignored);
  * best-effort throughout: a watchdog bug must never take the supervisor with it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import sense, telegram

_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / "data" / "watchdog_state.json"      # machine-local, git-ignored
_REGISTRY = _ROOT / "services.json"

_GRACE_CHECKS = int(os.getenv("WATCHDOG_GRACE_CHECKS", "2"))
_MAX_RESTARTS = int(os.getenv("WATCHDOG_MAX_RESTARTS", "3"))
_WINDOW_MIN = float(os.getenv("WATCHDOG_WINDOW_MIN", "30"))


def _auto_restart() -> bool:
    return os.getenv("WATCHDOG_AUTO_RESTART", "1").lower() not in {"0", "false", "no", "off"}


def _load_registry() -> list[dict]:
    try:
        data = json.loads(_REGISTRY.read_text(encoding="utf-8"))
        return data.get("services", [])
    except Exception:
        return []


def _venv_python(venv_rel: str) -> Path | None:
    base = _ROOT / (venv_rel or ".venv")
    for candidate in (base / "Scripts" / "python.exe", base / "bin" / "python"):
        if candidate.exists():
            return candidate
    return None


def _local_services() -> dict[str, dict]:
    """Registered services this machine actually runs (venv present)."""
    out: dict[str, dict] = {}
    for s in _load_registry():
        py = _venv_python(s.get("venv", ".venv"))
        if py:
            out[s["key"]] = {**s, "_python": str(py)}
    return out


def local_keys() -> set[str]:
    """Public: service keys this machine watches. Used by advisor.py so a twin
    that doesn't run every organ never flags a service it was never meant to run."""
    try:
        return set(_local_services().keys())
    except Exception:
        return set()


def active_incidents() -> list[dict]:
    """Services the watchdog has CONFIRMED down (past the grace period,
    already notified) and not yet recovered. This is what advisor.py surfaces
    — reading the watchdog's own judgment, not a raw one-shot audit read, so a
    session where the stack simply hasn't been started yet never gets flagged
    as '15 services down'. Never raises."""
    try:
        state = _load_state().get("services", {})
        return [{"key": k, "gave_up": bool(v.get("gave_up"))}
                for k, v in state.items() if v.get("notified")]
    except Exception:
        return []


def _audit_rows() -> list[dict]:
    """Live up/down per registered service — audit_services is the one truth."""
    try:
        if str(_ROOT) not in sys.path:
            sys.path.insert(0, str(_ROOT))
        import audit_services
        return audit_services.audit_data().get("services", [])
    except Exception:
        return []


def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def _launch(service: dict) -> bool:
    """Spawn the service exactly like START_MARKETING_OS.ps1 does, detached so it
    outlives this tick. Best-effort: False on any failure, never raises."""
    py = service.get("_python")
    launch = service.get("launch")
    if not py or not service.get("target") or not service.get("port"):
        return False
    if launch == "uvicorn":
        args = [py, "-m", "uvicorn", service["target"], "--host", "127.0.0.1",
                "--port", str(service["port"])]
    elif launch == "streamlit":
        args = [py, "-m", "streamlit", "run", service["target"],
                "--server.port", str(service["port"]), "--server.headless", "true"]
    else:
        return False
    cwd = str(_ROOT / (service.get("cwd") or "."))
    try:
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            )
        else:
            kwargs["start_new_session"] = True
        log = _ROOT / "data" / "logs" / f"watchdog-{service.get('key', 'svc')}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        lf = open(log, "a", encoding="utf-8")
        subprocess.Popen(args, cwd=cwd, stdout=lf, stderr=lf, stdin=subprocess.DEVNULL, **kwargs)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[watchdog] launch failed for {service.get('key')}: {exc}")
        return False


def _attempts_in_window(attempts: list[float], now: float, window_s: float) -> list[float]:
    return [t for t in (attempts or []) if now - t < window_s]


def _ping(text: str) -> None:
    owner = (os.getenv("TELEGRAM_OWNER_CHAT_ID") or os.getenv("GATEWAY_OWNER_ID") or "").strip()
    if not owner or not telegram.is_configured():
        return
    try:
        telegram.send_message(owner, "\U0001fa7a Watchdog: " + text)
    except Exception as exc:  # noqa: BLE001
        print(f"[watchdog] notify failed: {exc}")


def tick(rows: list[dict] | None = None, local: dict[str, dict] | None = None, *,
         notify: bool = True, restart: bool | None = None, now: float | None = None) -> dict:
    """One watchdog pass. Returns {"down", "restarted", "gave_up", "recovered"}
    (lists of service keys). Never raises — a watchdog bug must not take the
    always-on supervisor down with it."""
    result = {"down": [], "restarted": [], "gave_up": [], "recovered": []}
    try:
        now = now if now is not None else time.time()
        local = local if local is not None else _local_services()
        rows = rows if rows is not None else _audit_rows()
        do_restart = _auto_restart() if restart is None else restart
        window_s = _WINDOW_MIN * 60

        state = _load_state()
        services_state = state.setdefault("services", {})
        seen: set[str] = set()

        for row in rows:
            key = row.get("key")
            if key not in local:
                continue  # not ours to watch on this machine
            seen.add(key)
            st = services_state.setdefault(
                key, {"down_count": 0, "attempts": [], "notified": False, "gave_up": False})

            if row.get("up"):
                if st.get("notified"):
                    result["recovered"].append(key)
                    if notify:
                        _ping(f"✅ {row.get('name', key)} ({key}:{row.get('port')}) "
                              "yenidən ayaqdadır.")
                st.update({"down_count": 0, "attempts": [], "notified": False, "gave_up": False})
                continue

            st["down_count"] = int(st.get("down_count", 0)) + 1
            if st["down_count"] < _GRACE_CHECKS:
                continue  # too fresh — could be a deliberate bounce

            result["down"].append(key)
            if not st.get("notified"):
                st["notified"] = True
                if notify:
                    _ping(f"\U0001f534 {row.get('name', key)} ({key}:{row.get('port')}) dayanıb.")
                try:
                    sense.emit("watchdog", f"{key} down", {"port": row.get("port")})
                except Exception:
                    pass

            if st.get("gave_up"):
                continue  # circuit open — silent until a human resolves it

            attempts = _attempts_in_window(st.get("attempts", []), now, window_s)
            if len(attempts) >= _MAX_RESTARTS:
                st["gave_up"] = True
                result["gave_up"].append(key)
                if notify:
                    _ping(f"\U0001f6d1 {row.get('name', key)} ({key}) {_MAX_RESTARTS} cəhddən "
                          "sonra özü qalxmadı — insan baxışı lazımdır.")
            elif do_restart:
                launched = _launch(local[key])
                attempts.append(now)
                st["attempts"] = attempts
                if launched:
                    result["restarted"].append(key)

        for key in list(services_state.keys()):
            if key not in seen:
                services_state.pop(key, None)  # deregistered / no longer local

        _save_state(state)
        return result
    except Exception as exc:  # noqa: BLE001
        print(f"[watchdog] tick failed: {exc}")
        return result


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = tick()
    print(f"[watchdog] down={r['down']} restarted={r['restarted']} "
          f"gave_up={r['gave_up']} recovered={r['recovered']}")
