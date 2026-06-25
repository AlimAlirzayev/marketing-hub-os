"""Safety-net sweep for autonomous session capture.

SessionEnd only fires on a clean exit; a window that is simply closed may never
emit it. This sweep catches those: it scans this project's Claude transcripts and
captures any session that is **idle** (untouched for a while = finished) and not
yet captured. Wire it as a **SessionStart** hook so every time you open Claude, it
quietly picks up whatever you closed silently last time.

Cost/safety bounds (all env-overridable):
  CAPTURE_IDLE_MINUTES   default 10   only sweep transcripts idle >= this
  CAPTURE_LOOKBACK_HOURS default 48   ignore ancient transcripts
  CAPTURE_SWEEP_MAX      default 5    cap captures per run (keeps startup snappy)

Usage:
  python scripts/capture_sweep.py             # capture idle, uncaptured sessions
  python scripts/capture_sweep.py --baseline  # mark current transcripts as seen,
                                              # WITHOUT reflecting (no history blast)
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import session_capture as sc  # noqa: E402  (shares capture_session + markers)


def _transcript_dir() -> Path | None:
    """Locate ~/.claude/projects/<mangled-cwd>/ for this repo.

    Claude mangles the project path by replacing :, \\, /, . with '-'.
    """
    projects = Path.home() / ".claude" / "projects"
    mangled = re.sub(r"[:\\/.]", "-", str(ROOT))
    cand = projects / mangled
    if cand.is_dir():
        return cand
    # Fallback: any project dir that ends with this repo's folder name.
    if projects.is_dir():
        for d in projects.iterdir():
            if d.is_dir() and d.name.endswith(ROOT.name):
                return d
    return None


def _candidates(tdir: Path, *, idle_min: float, lookback_h: float):
    now = time.time()
    idle_cut = now - idle_min * 60
    old_cut = now - lookback_h * 3600
    out = []
    for p in tdir.glob("*.jsonl"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime > idle_cut:      # too fresh -> session may still be active
            continue
        if mtime < old_cut:       # too old -> not worth reflecting
            continue
        if sc.is_captured(p.stem):
            continue
        out.append((mtime, p))
    out.sort()  # oldest first
    return [p for _, p in out]


def main() -> int:
    tdir = _transcript_dir()
    if not tdir:
        sc._log("sweep: transcript dir not found")
        return 0

    baseline = "--baseline" in sys.argv
    if baseline:
        # Mark every existing transcript as seen so the sweep only ever acts on
        # sessions created from now on (no reflecting of historical sessions).
        # Skip the most-recently-modified one: that is the active session, which
        # should still get a proper capture at its real end.
        files = sorted(tdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        n = 0
        for p in files[1:]:
            if not sc.is_captured(p.stem):
                sc.mark_captured(p.stem)
                n += 1
        sc._log(f"sweep --baseline: marked {n} existing transcript(s) as seen (kept active)")
        print(f"baseline: marked {n} transcript(s) as seen, kept the active one")
        return 0

    idle_min = float(os.getenv("CAPTURE_IDLE_MINUTES", "10"))
    lookback_h = float(os.getenv("CAPTURE_LOOKBACK_HOURS", "48"))
    cap = int(os.getenv("CAPTURE_SWEEP_MAX", "5"))

    cands = _candidates(tdir, idle_min=idle_min, lookback_h=lookback_h)[:cap]
    total = 0
    for p in cands:
        total += sc.capture_session(p, p.stem)
    if cands:
        sc._log(f"sweep: processed {len(cands)} session(s), {total} lesson(s) queued")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
