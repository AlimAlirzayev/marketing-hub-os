"""Put the ONE product key on THIS machine's Desktop.

Doctrine (2026-07-21, Alim's "Ferrari" rule): the Desktop is the PRODUCT plane,
not the workshop. A driver presses ONE button, the factory boots, and the whole
system opens live in front of them. So this installs exactly one launcher —
"Marketing OS" — and actively retires every scattered port/tool shortcut we used
to scatter here. Builder-plane utilities (secure-key, add-Claude-account) live in
the repo, not on the owner's daily Desktop.

Why this file exists (Alim's cross-twin rule): the key must travel to BOTH twins
automatically, not be a per-machine afterthought. The engine already syncs via
git; this makes the *desktop button* part of that engine so opening the system on
either machine puts the one key in reach — no manual copying, no reminders.

Platform-aware, because the twins differ:
  * Windows work PC runs the whole OS LOCALLY -> the key BOOTS everything
    (START_MARKETING_OS.ps1) and the front door opens live.
  * Mac is a thin console -> the key SSH-tunnels to the always-on VPS, then
    opens the same front door.

Idempotent: run it every boot; it retires the old launchers and rewrites the one
key. Called from START_MARKETING_OS.ps1 (Windows) and the Mac session-start.
Never raises in a way that could block boot.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HUB_PORT = os.getenv("HUB_PORT", "8000")  # the front door — the live overview
ROOT = Path(__file__).resolve().parent.parent

# --- Windows: everything runs locally, so the key BOOTS the factory --------
# One button -> START boots every service from services.json (visible progress)
# -> the front door opens live. Absolute paths only (no %~dp0 fragility).
_WIN = {
    "🏎 Marketing OS.bat":
        "@echo off\r\n"
        "title Marketing OS\r\n"
        f'cd /d "{ROOT}"\r\n'
        "powershell -ExecutionPolicy Bypass -NoProfile -File "
        f'"{ROOT}\\START_MARKETING_OS.ps1"\r\n',
}


# --- Mac: thin console -> tunnel to the always-on VPS, open the front door --
def _mac_tunnel(path: str, port: str = HUB_PORT, health: str = "/api/status") -> str:
    # up(): the tunnel is live iff the front door answers. Test for HTTP 200 — the hub's
    # /api/status returns {"ads":true,...} with NO "ok":true key, so the old grep for
    # '"ok":true' never matched, so a 2nd click re-tunneled and collided on the live port.
    return (
        "#!/bin/bash\n"
        f'PORT={port}; URL="http://127.0.0.1:$PORT{path}"\n'
        f'up(){{ [ "$(curl -s -o /dev/null -w \'%{{http_code}}\' --max-time 2 "http://127.0.0.1:{port}{health}")" = "200" ]; }}\n'
        'if ! up; then ssh -f -N -L "$PORT:127.0.0.1:$PORT" -o ExitOnForwardFailure=yes hetzner-agents || { echo "tunel alinmadi"; sleep 3; exit 1; }\n'
        '  for _ in {1..10}; do up && break; sleep 1; done\nfi\n'
        'open -a "Google Chrome" "$URL" 2>/dev/null || open "$URL"\n'
    )


_MAC = {
    "🏎 Marketing OS.command": _mac_tunnel("/"),
}

# --- Old scattered launchers we now retire (the one-key doctrine) ----------
# Deleted by exact name only — never touches arbitrary user files. Safe if absent.
_RETIRED = [
    # Windows
    "Secure API Key.bat",
    "🎛 Idareetme Merkezi.bat",
    "🗺 Canli Xerite.bat",
    "📈 Ads Studio.bat",
    "📊 Dashboard.bat",
    "🔑 Beyin Girisi (Claude).bat",
    # Mac
    "Təhlükəsiz API Açarı.command",
    "🎛 İdarəetmə Mərkəzi.command",
    "🗺 Canlı Xəritə.command",
    "📈 Ads Studio.command",
    "🔑 Beyin Girişi (Claude).command",
    "📊 Dashboard.command",
]


def _desktop() -> Path:
    home = Path.home()
    for c in (home / "Desktop", home / "OneDrive" / "Desktop", home / "Masaüstü"):
        if c.is_dir():
            return c
    return home / "Desktop"


def install() -> list[str]:
    dst = _desktop()
    dst.mkdir(parents=True, exist_ok=True)

    # Retire the old scattered launchers first — the Desktop is one key only.
    for name in _RETIRED:
        try:
            (dst / name).unlink(missing_ok=True)
        except Exception as exc:  # never let cleanup break a boot
            print(f"[launchers] retire skip {name}: {exc}")

    files = _WIN if os.name == "nt" else _MAC
    written = []
    for name, body in files.items():
        try:
            p = dst / name
            p.write_text(body, encoding="utf-8")
            if os.name != "nt":
                p.chmod(0o755)
            written.append(name)
        except Exception as exc:  # never let a boot step fail on one file
            print(f"[launchers] skip {name}: {exc}")
    return written


if __name__ == "__main__":
    try:
        w = install()
        print(f"[launchers] {len(w)} key -> {_desktop()}")
    except Exception as exc:  # noqa: BLE001 — boot must never break on this
        print(f"[launchers] install skipped: {exc}", file=sys.stderr)
