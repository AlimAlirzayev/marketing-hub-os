"""Append a Social Studio creative feedback record to JSONL memory."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = ROOT / "social-studio" / "audit" / "learning" / "creative_feedback.jsonl"


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return ROOT / p


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Record creative feedback memory.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--decision", required=True, choices=["accepted", "rejected", "revise"])
    parser.add_argument("--notes", default="")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    report_path = resolve_path(args.report)
    review_path = resolve_path(args.review)
    out_path = resolve_path(args.out)
    report = load_json(report_path)
    review = load_json(review_path)

    record = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "campaign": report.get("campaign"),
        "brand": report.get("brand"),
        "decision": args.decision,
        "notes": args.notes,
        "audit_report": str(report_path.relative_to(ROOT) if report_path.is_relative_to(ROOT) else report_path),
        "creative_review": str(review_path.relative_to(ROOT) if review_path.is_relative_to(ROOT) else review_path),
        "automated_gate_score": report.get("automated_gate_score"),
        "final_score": report.get("overall_score"),
        "creative_judgment": report.get("creative_judgment"),
        "prompt_patch": report.get("prompt_patch", []),
        "review_prompt_patch": review.get("next_prompt_patch", []),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Recorded feedback -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
