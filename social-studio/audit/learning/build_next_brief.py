"""Build the next Social Studio image brief from review feedback.

This is the first practical self-improvement loop:
base brief + creative review + feedback memory -> next prompt version.
It does not pretend to train a model yet; it turns taste decisions into a
repeatable prompt compiler.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FEEDBACK = ROOT / "social-studio" / "audit" / "learning" / "creative_feedback.jsonl"


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return ROOT / p


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_feedback(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            out.append(item.strip())
            seen.add(key)
    return out


def build_next_prompt(
    base_prompt: str,
    review: dict[str, Any],
    feedback: list[dict[str, Any]],
    version: str,
) -> str:
    review_patch = review.get("next_prompt_patch", [])
    memory_patch: list[str] = []
    for record in feedback[-5:]:
        memory_patch.extend(record.get("review_prompt_patch", []))

    patch_lines = unique([*review_patch, *memory_patch])
    patch_text = "\n".join(f"- {line}" for line in patch_lines)

    invariant_patch: list[str] = []
    for record in feedback[-8:]:
        if record.get("decision") == "rejected":
            invariant_patch.extend(record.get("review_prompt_patch", []))
    invariant_text = "\n".join(f"- {line}" for line in unique(invariant_patch))
    if not invariant_text:
        invariant_text = "- Keep every concrete scene requirement from the base brief."

    return (
        f"{base_prompt}\n\n"
        "NON-NEGOTIABLE BRIEF INVARIANTS:\n"
        "These constraints override every creative upgrade below. Do not reinterpret the campaign as a studio, office, desk, moodboard, agency, creator, or production setup.\n"
        f"{invariant_text}\n\n"
        f"{version.upper()} CREATIVE DIRECTOR UPGRADE:\n"
        "The previous version passed production safety but was not yet world-class. "
        "Improve concept strength, brand distinctiveness, art direction quality, "
        "craft realism, platform performance, and memorability without losing the "
        "successful v6 restraint.\n\n"
        "Hard creative corrections from review memory:\n"
        f"{patch_text}\n\n"
        "World-class promotion standard:\n"
        "- The image should feel like an authored financial-services campaign, not stock photography.\n"
        "- The Baku-Tbilisi rail context must be legible through authentic regional detail, not text.\n"
        "- The subjects should feel candid, calm, and protected, with natural micro-expression rather than posed lifestyle smiling.\n"
        "- Make one clear visual idea: travel freedom plus quiet insurance protection.\n"
        "- Keep negative space elegant and premium; no extra props or clutter.\n"
        "- Keep the bottom footer zone clean and dark because final legal/contact layers will be added by code.\n"
        "- No generated readable text anywhere in the image.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build next Social Studio brief from feedback.")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--feedback", type=Path, default=DEFAULT_FEEDBACK)
    parser.add_argument("--version", default="v7")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    base = load_json(resolve_path(args.base))
    review = load_json(resolve_path(args.review))
    feedback = load_feedback(resolve_path(args.feedback))

    out = dict(base)
    out["$comment"] = (
        f"{args.version.upper()} brief generated from v6 creative review and feedback memory. "
        "This is prompt-compilation, not model fine-tuning."
    )
    out["version"] = args.version
    out["generated_from"] = {
        "base": str(resolve_path(args.base).relative_to(ROOT)),
        "review": str(resolve_path(args.review).relative_to(ROOT)),
        "feedback_records_used": len(feedback[-5:]),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    out["prompt"] = build_next_prompt(base["prompt"], review, feedback, args.version)

    negative = list(base.get("negative", []))
    negative.extend(
        [
            "generic stock photo",
            "posed stock lifestyle smile",
            "obvious AI shield icon",
            "tourism brochure look",
            "extra text on documents",
            "fake station signage",
            "overly perfect plastic faces",
        ]
    )
    out["negative"] = unique(negative)
    if "providers" in out and "gpt_image_2" in out["providers"]:
        out["providers"]["gpt_image_2"]["output"] = f"experiments/hero_gpt_image_2_{args.version}.png"

    out_path = resolve_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote next brief -> {out_path}")
    print(f"Prompt chars: {len(out['prompt'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
