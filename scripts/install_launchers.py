"""Put the one-click access launchers on THIS machine's Desktop.

Why this exists (2026-07-13, Alim's rule): the access launchers must travel to
BOTH twins automatically, not be a Mac-local afterthought. The engine already
syncs via git; this makes the *desktop buttons* part of that engine so opening
the system on either machine puts them in reach — no manual copying, no reminders.

It is platform-aware because the twins differ:
  * Windows work PC runs the whole OS LOCALLY -> launchers open localhost URLs.
  * Mac is a thin console -> launchers SSH-tunnel to the VPS first.

Idempotent: run it every boot; it just rewrites the current launchers. Called
from START_MARKETING_OS.ps1 (Windows) and the Mac session-start. Never raises
in a way that could block boot.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PANEL_PORT = os.getenv("PANEL_PORT", "8890")
DASH_PORT = os.getenv("DASHBOARD_PORT", "7733")
ADS_PORT = os.getenv("ADS_STUDIO_PORT", "8800")

# --- Windows: everything runs locally, so just open localhost -------------
_WIN = {
    "🎛 Idareetme Merkezi.bat":
        f'@echo off\r\nstart "" "http://localhost:{PANEL_PORT}/"\r\n',
    "🗺 Canli Xerite.bat":
        f'@echo off\r\nstart "" "http://localhost:{PANEL_PORT}/map"\r\n',
    "📈 Ads Studio.bat":
        f'@echo off\r\nstart "" "http://localhost:{ADS_PORT}/"\r\n',
    "📊 Dashboard.bat":
        f'@echo off\r\nstart "" "http://localhost:{DASH_PORT}/"\r\n',
    "🔑 Beyin Girisi (Claude).bat":
        '@echo off\r\ncd /d "%~dp0..\\"\r\n'
        'powershell -ExecutionPolicy Bypass -NoProfile -File '
        '"%~dp0..\\scripts\\add_claude_account.ps1"\r\n'
        'pause\r\n',
}

# --- Mac: thin console -> tunnel to the VPS -------------------------------
def _mac_tunnel(path: str, port: str = PANEL_PORT) -> str:
    return (
        "#!/bin/bash\n"
        f'PORT={port}; URL="http://127.0.0.1:$PORT{path}"\n'
        f'up(){{ curl -s --max-time 2 "http://127.0.0.1:{port}/api/health" | grep -q \'"ok":true\'; }}\n'
        'if ! up; then ssh -f -N -L "$PORT:127.0.0.1:$PORT" -o ExitOnForwardFailure=yes hetzner-agents || { echo "tunel alinmadi"; sleep 3; exit 1; }\n'
        '  for _ in {1..10}; do up && break; sleep 1; done\nfi\n'
        'open -a "Google Chrome" "$URL" 2>/dev/null || open "$URL"\n'
    )


_MAC = {
    "🎛 İdarəetmə Mərkəzi.command": _mac_tunnel("/"),
    "🗺 Canlı Xəritə.command": _mac_tunnel("/map"),
    "📈 Ads Studio.command": _mac_tunnel("/", ADS_PORT),
    "🔑 Beyin Girişi (Claude).command": (
        "#!/bin/bash\n"
        'echo "Claude hesab(lar) əlavə edirik (2 hesab tövsiyə olunur)..."\n'
        "n=1\n"
        "while true; do\n"
        '  ssh -t hetzner-agents "cd /opt/marketing-hub-os && scripts/add_claude_account.sh account-$n"\n'
        '  read -p "Başqa hesab? (b=bəli): " m; case "$m" in b|B) n=$((n+1));; *) break;; esac\n'
        "done\n"
    ),
    "📊 Dashboard.command": (
        "#!/bin/bash\n"
        'cd "$HOME/control-center/dashboard" 2>/dev/null || { echo "dashboard tapılmadı"; sleep 2; exit 1; }\n'
        'PY="$(command -v python3 || echo /usr/bin/python3)"; exec "$PY" server.py\n'
    ),
}


def _desktop() -> Path:
    home = Path.home()
    for c in (home / "Desktop", home / "OneDrive" / "Desktop", home / "Masaüstü"):
        if c.is_dir():
            return c
    return home / "Desktop"


def install() -> list[str]:
    dst = _desktop()
    dst.mkdir(parents=True, exist_ok=True)
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
        print(f"[launchers] {len(w)} launcher(s) -> {_desktop()}")
    except Exception as exc:  # noqa: BLE001 — boot must never break on this
        print(f"[launchers] install skipped: {exc}", file=sys.stderr)
