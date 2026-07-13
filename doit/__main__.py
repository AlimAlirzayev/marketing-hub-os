"""CLI:  python -m doit rapidapi [--browser auto|chrome|edge] [--headless] ...

Examples
--------
First time (logs in once in a visible window, then remembers the session):
    .venv\\Scripts\\python -m doit rapidapi

Use the browser you are ALREADY logged into RapidAPI with (close it first):
    .venv\\Scripts\\python -m doit rapidapi --browser chrome ^
        --user-data-dir "%LOCALAPPDATA%\\Google\\Chrome\\User Data" --profile-directory Default

After the session is saved, fully autonomous:
    .venv\\Scripts\\python -m doit rapidapi --headless
"""

from __future__ import annotations

import argparse
import sys

from . import agent


def main(argv: list[str] | None = None) -> int:
    # Azerbaijani status text must survive a cp1252 console, not crash it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(prog="doit", description="autonomous API-key acquisition agent")
    ap.add_argument("provider", nargs="?", default="rapidapi", choices=sorted(agent.RECIPES),
                    help="hansı provider-in açarını gətirsin (default: rapidapi)")
    ap.add_argument("--browser", default="auto", help="auto | chrome | edge (default auto = Chrome varsa Chrome)")
    ap.add_argument("--headless", action="store_true", help="görünməz işlət (yalnız sessiya artıq login olanda)")
    ap.add_argument("--env", default=agent.DEFAULT_ENV, help="hədəf .env yolu")
    ap.add_argument("--user-data-dir", default=None, help="öz real brauzer profilinin User Data qovluğu")
    ap.add_argument("--profile-directory", default=None, help="profil adı (məs. Default)")
    ap.add_argument("--subscribe-url", default=None, help="bir host-un RapidAPI səhifəsi (pulsuz plana abunə üçün)")
    ap.add_argument("--check", action="store_true",
                    help="heç nə açmadan yoxla: miras alına bilən sessiya varmı?")
    args = ap.parse_args(argv)

    if args.check:
        diag = agent.doctor(args.provider)
        print(f"[doit] {diag.get('message', diag.get('error', '?'))}")
        return 0 if diag.get("ok") else 2

    res = agent.acquire(
        args.provider, browser=args.browser, headless=args.headless, env_path=args.env,
        user_data_dir=args.user_data_dir, profile_directory=args.profile_directory,
        subscribe_url=args.subscribe_url,
    )

    if res.get("ok"):
        print(f"\n[doit] UĞUR: {res['env_var']} {res['action']} -> {res['env']}")
        print(f"[doit] açar: {res['key_preview']}  (brauzer: {res['browser']})")
        print(f"[doit] {agent.verify_rapidapi()}")
        return 0
    print(f"\n[doit] alınmadı: {res.get('error', 'naməlum')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
