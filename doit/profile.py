"""Borrow the operator's REAL browser session — the reason doit never logs in.

Why this exists (2026-07-11): a login flow inside an automation-driven browser
is a dead end, not a bug to fix. Google answers OAuth in a Playwright-driven
Chrome with "Couldn't sign you in — this browser or app may not be secure", and
a CAPTCHA is a human's job by design. So doit must never *authenticate*; it must
*inherit* the session the operator already has.

It also must not fight the operator's live browser: instead of demanding Chrome
be closed (profile lock), we take a SNAPSHOT of the session-bearing files into a
scratch user-data-dir. Chrome stays open; the snapshot has its own singleton.

Provider-aware: the operator has many Chrome profiles (Default, "Work", …). We
pick the one whose cookie jar actually carries the provider's domain — so doit
lands in an already-logged-in dashboard on the FIRST try.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile

# Only the files that carry a session. Copying the whole profile means gigabytes
# of cache for nothing.
# Cookies-wal / Cookies-shm are the WAL sidecars: while Chrome is open the freshest
# cookies live there, not in the main Cookies file (see _copy_sqlite). Snapshot them
# too or the borrowed session is stale for exactly the login the operator just made.
_SESSION_FILES = ("Cookies", "Cookies-journal", "Cookies-wal", "Cookies-shm",
                  "Preferences", "Secure Preferences", "Login Data", "Web Data")
_SESSION_DIRS = ("Network", "Local Storage", "Session Storage", "IndexedDB")


def user_data_root(channel: str = "chrome") -> str | None:
    """The operator's real browser User Data directory for this OS."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        roots = {
            "chrome": f"{home}/Library/Application Support/Google/Chrome",
            "msedge": f"{home}/Library/Application Support/Microsoft Edge",
        }
    elif os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        roots = {
            "chrome": os.path.join(local, "Google", "Chrome", "User Data"),
            "msedge": os.path.join(local, "Microsoft", "Edge", "User Data"),
        }
    else:
        roots = {
            "chrome": f"{home}/.config/google-chrome",
            "msedge": f"{home}/.config/microsoft-edge",
        }
    root = roots.get(channel)
    return root if root and os.path.isdir(root) else None


def _copy_sqlite(src: str, dest: str) -> None:
    """Copy a live Chrome SQLite DB so its NEWEST cookies are readable.

    Chrome runs its cookie store in WAL mode. While the browser is OPEN — exactly
    the case doit is built for — the freshest cookies (a login made seconds ago) live
    in the `-wal` file and are not yet checkpointed into the main DB. Copying only the
    main file reads a STALE snapshot, so a fresh session is invisible.

    We copy the main DB and its `-wal`, but deliberately NOT the `-shm`: the shared-
    memory index is being mutated by the running browser, and a half-written copy of
    it makes SQLite reject the whole WAL. Omitting it lets SQLite rebuild a consistent
    `-shm` from the `-wal` on our private copy. host_key only; values never read.
    """
    shutil.copy2(src, dest)
    sib = src + "-wal"
    if os.path.exists(sib):
        try:
            shutil.copy2(sib, dest + "-wal")
        except Exception:  # noqa: BLE001 — a missing/locked -wal just means no fresh data
            pass


def _cookie_hits(profile_dir: str, domain: str) -> int:
    """How many cookies this profile holds for the provider's domain. The DB is
    copied first — Chrome holds a lock on the live file while it runs. Only
    host_key is read; cookie VALUES are never touched or decrypted."""
    for rel in ("Cookies", os.path.join("Network", "Cookies")):
        src = os.path.join(profile_dir, rel)
        if not os.path.exists(src):
            continue
        tmp = os.path.join(tempfile.mkdtemp(), "c.db")
        try:
            _copy_sqlite(src, tmp)
            con = sqlite3.connect(tmp)
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # fold the -wal into the copy
            n = con.execute(
                "SELECT count(*) FROM cookies WHERE host_key LIKE ?",
                (f"%{domain}%",),
            ).fetchone()[0]
            con.close()
            if n:
                return int(n)
        except Exception:  # noqa: BLE001 — an unreadable profile is just a miss
            pass
        finally:
            shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    return 0


def find_profile(domain, channel: str = "chrome") -> tuple[str, str, int] | None:
    """Pick the operator profile already logged into the provider.

    ``domain`` may be a single host substring or an ordered iterable of markers.
    Some providers keep NO first-party session cookie: RapidAPI authenticates
    through Auth0, so a logged-in profile carries `auth0.com` cookies but zero
    `rapidapi.com` ones (this cost us a full debugging session on 2026-07-14).
    The markers are tried in order; the first that any profile matches wins, so a
    precise first-party marker is preferred and a shared IdP marker is the fallback.
    Returns (user_data_root, profile_name, cookie_hits) or None.
    """
    markers = (domain,) if isinstance(domain, str) else tuple(domain)
    root = user_data_root(channel)
    if not root:
        return None
    names = []
    try:
        state = json.load(open(os.path.join(root, "Local State"), encoding="utf-8"))
        names = list(state.get("profile", {}).get("info_cache", {}).keys())
    except Exception:  # noqa: BLE001
        pass
    if not names:
        names = [d for d in os.listdir(root)
                 if d == "Default" or d.startswith("Profile ")]
    for marker in markers:
        if not marker:
            continue
        best = max(
            ((n, _cookie_hits(os.path.join(root, n), marker)) for n in names),
            key=lambda t: t[1], default=(None, 0),
        )
        if best[0] and best[1] > 0:
            return root, best[0], best[1]
    return None


def snapshot(root: str, profile: str, dest: str) -> str:
    """Copy the session-bearing files of one profile into a fresh user-data-dir
    that Playwright can drive while the operator's browser stays open. The
    snapshot is placed as 'Default' so Chrome opens it without a profile flag."""
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(os.path.join(dest, "Default"), exist_ok=True)
    src_profile = os.path.join(root, profile)
    ls = os.path.join(root, "Local State")
    if os.path.exists(ls):
        shutil.copy2(ls, os.path.join(dest, "Local State"))
    for name in _SESSION_FILES:
        p = os.path.join(src_profile, name)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(dest, "Default", name))
    def _copy_available(src: str, dst: str) -> str:
        """Copy one live-profile file, skipping only files Chrome keeps locked."""
        try:
            return shutil.copy2(src, dst)
        except OSError:
            return dst

    for name in _SESSION_DIRS:
        p = os.path.join(src_profile, name)
        if os.path.isdir(p):
            ignore = None
            if name == "Network":
                # Cookies is copied separately above. Copying the same live DB
                # through copytree raises WinError 32 while Chrome is open and
                # used to abort the entire otherwise-usable session snapshot.
                ignore = shutil.ignore_patterns("Cookies", "Cookies-*")
            shutil.copytree(p, os.path.join(dest, "Default", name),
                            dirs_exist_ok=True, ignore=ignore,
                            copy_function=_copy_available)
    return dest
