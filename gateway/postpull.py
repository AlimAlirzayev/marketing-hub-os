"""Post-pull tripwire — trust the twin, but verify.

When the mailbox (scripts/sync_engine.py) actually lands NEW engine commits from the
other twin, this runs the test suite and scans the incoming diff, then FLAGS (never
blocks) anything worth a human glance. The pull already happened; this only tells the
owner whether the newly-arrived code:

  * broke a test that USED TO PASS (a real regression — not a pre-existing/env failure),
  * or touched something sensitive (security, sync brain, secrets, deps, big deletions).

Design choices that keep it from crying wolf and from slowing the mailbox:
  * DELTA on tests: alert only on failing-test IDs that are NEW vs a machine-local
    baseline (data/postpull_state.json, git-ignored). Pre-existing failures stay quiet.
  * runs AFTER the pull, on the sync thread's own cadence — never a gate, never blocks
    a worker/bot; a timeout or crash degrades to a plain-language "couldn't verify".
  * stdlib only, venv python for the tests. No new dependency.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / "data" / "postpull_state.json"          # machine-local, git-ignored
_TEST_TIMEOUT = int(os.getenv("POSTPULL_TEST_TIMEOUT", "300"))
_DELETION_ALERT = int(os.getenv("POSTPULL_DELETION_ALERT", "400"))

# Changes worth a human glance even when every test is green.
_SENSITIVE = (
    "gateway/security.py",
    "scripts/sync_engine.py",
    "gateway/keyvault.py",
    "gateway/workspace_agent.py",
    ".gitattributes",
    ".gitignore",
    ".env.example",
)
_REQ_FILES = ("requirements.txt", "requirements-panel.txt")


def _git(*args: str, timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", *args], cwd=str(_ROOT),
                           capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except Exception:
        return 1, ""


def _venv_python() -> str:
    for c in (_ROOT / ".venv" / "bin" / "python", _ROOT / ".venv" / "Scripts" / "python.exe"):
        if c.exists():
            return str(c)
    return sys.executable


def risky_changes(prev: str, new: str) -> list[str]:
    """Human-readable flags for the incoming diff prev..new (may be empty)."""
    flags: list[str] = []
    code, names = _git("diff", "--name-only", f"{prev}..{new}")
    files = [l.strip() for l in names.splitlines() if l.strip()] if code == 0 else []
    for f in files:
        if f in _SENSITIVE:
            flags.append(f"🔐 {f}")
    for req in _REQ_FILES:
        if req in files:
            _, d = _git("diff", f"{prev}..{new}", "--", req)
            for l in d.splitlines():
                if l.startswith("+") and not l.startswith("+++"):
                    dep = l[1:].strip()
                    if dep and not dep.startswith("#"):
                        flags.append(f"📦 yeni asılılıq ({req}): {dep}")
    _, stat = _git("diff", "--numstat", f"{prev}..{new}")
    dels = 0
    for l in stat.splitlines():
        parts = l.split("\t")
        if len(parts) == 3 and parts[1].isdigit():
            dels += int(parts[1])
    if dels >= _DELETION_ALERT:
        flags.append(f"🗑️ böyük silinmə: {dels} sətir")
    return flags


def _failing_ids(output: str) -> set[str]:
    # unittest prints "FAIL: test_x (module.Class.test_x)" / "ERROR: ... (...)"
    return set(re.findall(r"^(?:FAIL|ERROR): \S+ \(([^)]+)\)", output, re.M))


def run_tests() -> tuple[int, set[str]]:
    """Run the suite with the venv python. Returns (total, failing_ids); total<0 on
    a run failure (timeout / couldn't launch)."""
    try:
        p = subprocess.run(
            [_venv_python(), "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=str(_ROOT), capture_output=True, text=True, timeout=_TEST_TIMEOUT, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return -1, set()
    except Exception:
        return -1, set()
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"^Ran (\d+) test", out, re.M)
    total = int(m.group(1)) if m else -1
    return total, _failing_ids(out)


def _load_known() -> set[str]:
    try:
        return set(json.loads(_STATE.read_text()).get("known_failures", []))
    except Exception:
        return set()


def save_baseline(ids: set[str]) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps({"known_failures": sorted(ids)}))
    except Exception:
        pass


def verify(prev: str, new: str) -> str:
    """One short AZ status line for the owner. ALWAYS returns a string.
    ⚠️ on a NEW test regression or a risky change; else a green ✅ line."""
    risky = risky_changes(prev, new)
    total, now_fail = run_tests()
    if total < 0:
        note = "⚠️ testləri qaça bilmədim (timeout/xəta) — yeni kodu bir gözdən keçir."
        return note + (("\n🔎 diqqətlə bax: " + "; ".join(risky[:6])) if risky else "")
    known = _load_known()
    new_fail = now_fail - known
    save_baseline(now_fail)  # today's failures become tomorrow's baseline
    passed = total - len(now_fail)
    if new_fail:
        head = (f"⚠️ TEST REGRESSİYASI — bu pull {len(new_fail)} testi sındırdı: "
                + ", ".join(sorted(new_fail)[:5]))
    else:
        head = f"✅ testlər yaşıl ({passed}/{total} keçdi)"
    if risky:
        head += "\n🔎 diqqətlə bax: " + "; ".join(risky[:6])
    return head


if __name__ == "__main__":
    # `python -m gateway.postpull [prev new]` — seed the baseline or verify a range.
    if len(sys.argv) == 3:
        print(verify(sys.argv[1], sys.argv[2]))
    else:
        t, f = run_tests()
        save_baseline(f)
        print(f"baseline seeded: {len(f)} known failure(s) of {t} tests -> {sorted(f)}")
