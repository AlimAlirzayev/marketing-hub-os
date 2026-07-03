"""One safe, DRY engine-sync brain shared by every trigger.

Same logic is reused by:
  - the SessionStart hook (pull on open)      -> `python scripts/sync_engine.py --pull-only`
  - the SessionEnd hook (push my commits)     -> `python scripts/sync_engine.py --push-only`
  - the launcher / one-click PULL.bat         -> `python scripts/sync_engine.py`
  - the Telegram `/update` command on the VPS -> gateway.bot calls sync()

Why one file: three shell copies drift. This is stdlib-only (no deps, no venv),
so it runs identically on the work PC, the MacBook, and the Hetzner VPS.

The contract (see docs/SYNC.md): move only the ENGINE. Private business data is
git-ignored, so `git push` can physically only ship engine code -- the boundary
is enforced by .gitignore, not by trust. This script is deliberately conservative:

  * fast-forward pulls only (never a merge/rebase that could mangle local work)
  * push only already-committed commits that are strictly ahead (never auto-commit
    a dirty tree, never force-push)
  * a short network timeout so a hook can never hang a session
  * never raises on a network/git hiccup -- prints one line and exits 0

Result strings are single-line and human-readable so the SessionStart hook output
reads cleanly back into chat ("engine up to date" / "pulled 3 new commits").
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NET_TIMEOUT = 20  # seconds; keep a hook from ever blocking on a dead network


def _git(*args: str, timeout: int | None = None) -> tuple[int, str]:
    """Run a git command in the repo. Returns (returncode, combined output)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError:
        return 127, "git not found on PATH"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def _rev(ref: str) -> str | None:
    code, out = _git("rev-parse", ref)
    return out if code == 0 else None


def _apply_vault_keys() -> None:
    """After a pull, decrypt any newly-arrived API keys from the encrypted vault
    (secrets/keys.vault) into this machine's .env — the other half of the
    'keys travel encrypted' rule (docs/SYNC.md). Best-effort: needs the repo
    venv's `cryptography` and a KEY_VAULT_SECRET in .env; silently skips
    otherwise so this stdlib-only script never gains a hard dependency."""
    if not (ROOT / "secrets" / "keys.vault").exists():
        return
    py = ROOT / ".venv" / "Scripts" / "python.exe"          # Windows venv
    if not py.exists():
        py = ROOT / ".venv" / "bin" / "python"              # Linux/mac venv
    try:
        proc = subprocess.run(
            [str(py) if py.exists() else sys.executable, "-m", "gateway.keyvault", "apply"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
        )
        line = (proc.stdout or "").strip()
        if line and "applied 0" not in line:
            print(line)
    except Exception:
        pass


def sync(*, pull: bool = True, push: bool = True, quiet: bool = False) -> str:
    """Safely reconcile local engine with origin. Returns a one-line summary."""

    def say(msg: str) -> str:
        if not quiet:
            print(f"[sync] {msg}")
        return msg

    # Is there an upstream at all?
    if _rev("@{u}") is None:
        return say("no upstream set (run once: git push -u origin master) -- skipped")

    # Fetch (the only network read). Offline -> skip gracefully, never block.
    code, out = _git("fetch", "origin", timeout=NET_TIMEOUT)
    if code != 0:
        reason = "offline/timeout" if code == 124 else out.splitlines()[-1:] or ["fetch failed"]
        return say(f"could not reach origin ({reason if isinstance(reason, str) else reason[0]}) -- kept local")

    local = _rev("@")
    remote = _rev("@{u}")
    base = _rev("--fork-point @{u} @") or (_git("merge-base", "@", "@{u}")[1] or None)
    dirty = bool(_git("status", "--porcelain")[1])

    if local == remote:
        return say(f"engine up to date (HEAD {local[:7] if local else '?'})")

    # Behind only -> pull (fast-forward). Safe even with a dirty tree if the ff
    # doesn't touch changed files; git refuses otherwise, which we surface.
    if pull and local == base and remote != base:
        code, out = _git("pull", "--ff-only", timeout=NET_TIMEOUT)
        if code == 0:
            _apply_vault_keys()  # newly-arrived encrypted keys -> this .env
            return say(f"pulled new engine updates -> {(_rev('@') or '')[:7]}")
        return say(f"update available but ff-pull blocked (likely local edits): {out.splitlines()[-1] if out else ''}")

    # Ahead only -> push my committed engine work so the other machine can pull it.
    if push and remote == base and local != base:
        if dirty:
            say("you have UNCOMMITTED changes; pushing committed engine commits only")
        code, out = _git("push", "origin", "HEAD", timeout=NET_TIMEOUT)
        if code == 0:
            return say(f"pushed local engine commits -> origin ({(local or '')[:7]})")
        return say(f"push failed: {out.splitlines()[-1] if out else 'unknown'}")

    # Diverged -> never auto-merge; the human decides.
    if local != base and remote != base:
        return say("branches DIVERGED -- manual review needed (no auto-merge)")

    return say("nothing to do")


def _main(argv: list[str]) -> int:
    pull = "--push-only" not in argv
    push = "--pull-only" not in argv
    quiet = "--quiet" in argv
    try:
        sync(pull=pull, push=push, quiet=quiet)
    except Exception as exc:  # never let a sync hiccup crash a hook/launcher
        if not quiet:
            print(f"[sync] skipped ({exc.__class__.__name__})")
    return 0  # always success: sync is best-effort, never fatal to the caller


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(_main(sys.argv[1:]))
