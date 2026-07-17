"""Untracked-file watchdog — nothing may rot in a corner of the repo.

The sync brain (scripts/sync_engine.py) moves COMMITTED work only; a file that
is never `git add`-ed silently stays on one machine forever and the twin never
sees it. The 2026-07-17 audit found exactly that class: three audio-studio docs
that never traveled, a queue that was meant to be git-ignored but wasn't, and a
stale __pycache__ leftover that broke tests. This sweep makes the class visible.

Called from gateway.engine_sync.refresh() on the supervisor's sync cadence.
Design (no crying wolf, never a gate):
  * a path counts only after UNTRACKED_WATCH_HOURS (default 48h) — fresh
    work-in-progress files stay quiet;
  * the owner is pinged on Telegram only when a NEW stale path appears, and at
    most once per UNTRACKED_WATCH_COOLDOWN_H (default 24h); the sense log
    always records the current list for the panel;
  * state is machine-local in data/untracked_watch.json (git-ignored) —
    staleness is per machine by nature;
  * best-effort: never raises into the sync path.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from . import sense, telegram

_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / "data" / "untracked_watch.json"    # machine-local, git-ignored


def _git_untracked() -> list[str]:
    """Repo-relative paths git sees as untracked (non-ignored) right now."""
    p = subprocess.run(["git", "status", "--porcelain"], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=30,
                       encoding="utf-8", errors="replace")
    return [line[3:].strip() for line in (p.stdout or "").splitlines()
            if line.startswith("?? ")]


def _age_hours(rel: str) -> float:
    """Hours since the path was last touched (top-level stat — cheap proxy)."""
    try:
        return (time.time() - (_ROOT / rel).stat().st_mtime) / 3600.0
    except OSError:
        return 0.0


def stale_paths(min_hours: float | None = None) -> list[str]:
    lim = float(os.getenv("UNTRACKED_WATCH_HOURS", "48")) if min_hours is None else min_hours
    return sorted(p for p in _git_untracked() if _age_hours(p) >= lim)


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


def sweep(notify: bool = True) -> list[str]:
    """One watchdog pass. Returns the current stale list. Never raises."""
    try:
        stale = stale_paths()
    except Exception:
        return []
    state = _load_state()
    if not stale:
        # forget resolved paths so a reappearing one pings again
        if state.get("known"):
            state["known"] = []
            _save_state(state)
        return []
    try:
        sense.emit("hygiene", f"{len(stale)} untracked path(s) sitting outside git",
                   {"paths": stale[:12]})
    except Exception:
        pass
    # "known" = paths the owner has already been TOLD about. A path that shows
    # up during the cooldown must not silently become known, or it would never
    # be announced at all — so known only advances on a successful ping.
    known = set(state.get("known", []))
    fresh = [p for p in stale if p not in known]
    cooldown_s = float(os.getenv("UNTRACKED_WATCH_COOLDOWN_H", "24")) * 3600
    owner = (os.getenv("TELEGRAM_OWNER_CHAT_ID") or "").strip()
    notified = False
    if (notify and fresh and owner and telegram.is_configured()
            and time.time() - float(state.get("last_notify_ts", 0)) >= cooldown_s):
        try:
            listing = "\n".join(f"  • {p}" for p in stale[:10])
            if len(stale) > 10:
                listing += f"\n  … +{len(stale) - 10} daha"
            telegram.send_message(owner, (
                "🧹 Dostum, git-in kənarında qalan fayllar var — sync onları DAŞIMIR, "
                "bu maşında qalıblar:\n" + listing +
                "\nHər biri üçün bir qərar lazımdır: commit et (əkizə getsin), "
                ".gitignore-a sal (bilərəkdən lokaldır), ya da sil."))
            state["last_notify_ts"] = time.time()
            notified = True
        except Exception as exc:  # a ping must never hurt the sync path
            print(f"[untracked_watch] notify failed: {exc}")
    state["known"] = stale if notified else sorted(known & set(stale))
    _save_state(state)
    return stale


if __name__ == "__main__":
    found = sweep(notify=False)
    print(f"[untracked_watch] {len(found)} stale untracked path(s)")
    for p in found:
        print(f"  {p}")
