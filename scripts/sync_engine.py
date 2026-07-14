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

  * fast-forward pulls only for the common case (never a blind merge/rebase that
    could mangle local work)
  * for the ONE unavoidable two-writer case -- the append-only shared decisions
    log -- it (a) auto-commits that single union-merge-safe file before syncing so
    an uncommitted handoff can never jam the pull, and (b) does a GUARDED union
    auto-merge that aborts on any real conflict and falls back to manual review
  * push only committed commits; never force-push
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

# The only paths sync is allowed to auto-commit. Must be append-only shared logs
# carrying a `merge=union` driver in .gitattributes, so committing + merging them
# can never lose data or conflict. Keep this list tiny and boring.
_AUTOCOMMIT_SAFE = ("memory/decisions.jsonl",)


def _git(*args: str, timeout: int | None = None) -> tuple[int, str]:
    """Run a git command in the repo. Returns (returncode, combined output)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError:
        return 127, "git not found on PATH"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def _rev(ref: str) -> str | None:
    code, out = _git("rev-parse", ref)
    return out if code == 0 else None


def _autocommit_shared_logs(say) -> bool:
    """Commit ONLY the union-merge-safe shared append-log(s) if a session left them
    dirty, so an uncommitted handoff never blocks the ff-pull mailbox. Never touches
    any other path (a partial, path-limited commit). Skips a file whose last line is
    torn (mid-write) -- it'll be caught on the next pass. Returns True if it committed."""
    to_commit: list[str] = []
    for rel in _AUTOCOMMIT_SAFE:
        _, status = _git("status", "--porcelain", "--", rel)
        if not status:
            continue  # clean -> nothing to do
        try:
            data = (ROOT / rel).read_bytes()
        except OSError:
            continue
        if data and not data.endswith(b"\n"):
            continue  # a write is in flight; leave it for the next sync
        to_commit.append(rel)
    if not to_commit:
        return False
    _git("add", "--", *to_commit)
    code, _ = _git(
        "commit",
        "-m",
        "chore(memory): checkpoint shared decisions log before sync [auto]",
        "--",
        *to_commit,
    )
    if code == 0:
        say(f"checkpointed shared log before sync ({', '.join(to_commit)})")
        return True
    return False


def _apply_vault_keys() -> None:
    """After a pull, decrypt any newly-arrived API keys from the encrypted vault
    (secrets/keys.vault) into this machine's .env -- the other half of the
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
            cwd=str(ROOT), capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
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

    # A session may have appended a shared handoff without committing it, which
    # would leave the tree dirty and silently block the ff-pull. Checkpoint that
    # one safe file first so the mailbox never jams on it.
    if pull or push:
        _autocommit_shared_logs(say)

    # Fetch (the only network read). Offline -> skip gracefully, never block.
    code, out = _git("fetch", "origin", timeout=NET_TIMEOUT)
    if code != 0:
        reason = "offline/timeout" if code == 124 else out.splitlines()[-1:] or ["fetch failed"]
        return say(f"could not reach origin ({reason if isinstance(reason, str) else reason[0]}) -- kept local")

    local = _rev("@")
    remote = _rev("@{u}")
    # merge-base, NOT --fork-point: fork-point reads reflog heuristics and
    # mislabels a local merge commit as "diverged", stalling the auto-push.
    base = _git("merge-base", "@", "@{u}")[1] or None
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

    # Diverged (both sides moved). The only expected cause after the checkpoint
    # above is two twins each appending to the union-merge decisions log. Attempt
    # a GUARDED union auto-merge; abort on ANY real conflict so we never mangle
    # local work, and fall back to the human.
    if local != base and remote != base:
        if dirty:
            return say("branches DIVERGED with uncommitted local edits -- manual review needed")
        code, out = _git("merge", "--no-edit", "@{u}", timeout=NET_TIMEOUT)
        if code != 0:
            _git("merge", "--abort")
            return say("branches DIVERGED -- auto-merge would conflict, manual review needed")
        _apply_vault_keys()
        merged = (_rev("@") or "")[:7]
        if push:
            pcode, _ = _git("push", "origin", "HEAD", timeout=NET_TIMEOUT)
            if pcode == 0:
                # keep the "pulled new engine" phrase so the supervisor announces it
                return say(f"pulled new engine updates (auto-merged divergent log) -> {merged}")
            return say(f"pulled new engine updates (auto-merged, push pending) -> {merged}")
        return say(f"pulled new engine updates (auto-merged divergent log) -> {merged}")

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
