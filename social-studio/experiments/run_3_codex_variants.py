"""Generate 3 Xalq Sigorta variants via Codex CLI (GPT Image 2) sequentially.

Sequential to avoid OpenAI server-side duplicate-session detection. Each
run produces one raw photographic background; render_post.compose() then
adds the brand-locked top tag, headline, body, and footer.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIO = HERE.parent
PY = sys.executable

# Import compose from the sibling render_post module without rerunning the
# Pollinations pipeline.
sys.path.insert(0, str(STUDIO))
from render_post import compose  # noqa: E402

SEEDS = [1, 2, 3]


def run_codex(out_path: Path) -> bool:
    cmd = [
        PY, "-u", str(HERE / "run_codex_gpt_image.py"),
        "--out", str(out_path),
    ]
    print(f"\n=== variant {out_path.stem} - codex CLI ===", flush=True)
    try:
        result = subprocess.run(cmd, timeout=420)
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after 7 min", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"  exit {result.returncode}", file=sys.stderr)
        return False
    return out_path.is_file()


def main() -> int:
    raws: list[Path] = []
    for i in SEEDS:
        raw = HERE / f"raw_codex_{i}.png"
        if run_codex(raw):
            raws.append(raw)

    print(f"\ngenerated {len(raws)}/{len(SEEDS)} raw backgrounds")
    if not raws:
        return 1

    print("\n=== compositing brand overlays ===")
    finals: list[Path] = []
    for raw in raws:
        final = HERE / f"post_codex_{raw.stem.split('_')[-1]}.png"
        compose(raw, final)
        finals.append(final)

    print(f"\nDONE - {len(finals)} production-ready posts:")
    for f in finals:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
