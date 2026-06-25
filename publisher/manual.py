"""Xalq Insurance Digital OS Publisher - manual handoff.

The cascade's always-works floor: when no live publisher can deliver a platform
(Postiz down, channel not connected, or a dry run), the plan is written to disk
as paste-ready blocks. A labelled fallback, never a silent omission.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO / "output" / "publish"


def write_manual(plan: dict, entries: list[dict] | None = None, *, reason: str = "") -> Path:
    """Write plan.json + one paste-ready .txt per platform. Returns the folder."""
    entries = plan["entries"] if entries is None else entries
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = OUT_ROOT / plan["slug"] / ts
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "plan.json").write_text(
        json.dumps({**plan, "manual_reason": reason}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    for e in entries:
        lines = [
            f"# {e['platform'].upper()}  ({e['caption_source']})",
            f"# when: {e['scheduled_at']}   media: {e['media'] or '(none)'}",
            "",
            e["caption"],
        ]
        (folder / f"{e['platform']}.txt").write_text("\n".join(lines), encoding="utf-8")

    return folder
