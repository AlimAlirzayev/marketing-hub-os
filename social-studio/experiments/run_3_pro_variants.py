"""Generate 3 Xalq Sigorta variants via Codex CLI using the v2 pro prompt.

Same orchestration as run_3_codex_variants.py but:
- Reads hero_brief_v2.json (the prompt_kit v2 master-level prompt).
- After each codex invocation, harvests the NEWEST ig_*.png from
  ~/.codex-cli/generated_images/<session>/ - codex's image_gen tool
  stores there, ignoring --out. This bypass is documented in
  prompt_kit/model_dialects/gpt-image-2.md.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIO = HERE.parent
PY = sys.executable
BRIEF = HERE / "hero_brief_v2.json"
GEN_DIR = Path.home() / ".codex-cli" / "generated_images"

sys.path.insert(0, str(STUDIO))
from render_post import compose  # noqa: E402

CODEX_RUN = HERE / "run_codex_gpt_image.py"


def latest_ig_png() -> Path | None:
    """Return the most recently modified ig_*.png across all sessions."""
    candidates = list(GEN_DIR.glob("*/ig_*.png"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_one(out: Path) -> bool:
    """Run codex with the v2 brief; harvest the resulting ig_*.png."""
    before = latest_ig_png()
    before_mtime = before.stat().st_mtime if before else 0.0

    cmd = [PY, "-u", str(CODEX_RUN), "--brief", str(BRIEF),
           "--out", str(out)]
    print(f"\n=== {out.name} - codex CLI (v2 prompt) ===", flush=True)
    try:
        subprocess.run(cmd, timeout=600)
    except subprocess.TimeoutExpired:
        print("  subprocess timed out at 10min, checking session dir anyway",
              flush=True)

    # Even if codex returned non-zero or timed out, the image_gen tool may
    # have written a fresh ig_*.png to the session directory.
    time.sleep(2)
    latest = latest_ig_png()
    if latest and latest.stat().st_mtime > before_mtime + 1:
        shutil.copy2(latest, out)
        print(f"  harvested {latest.name} -> {out.name}", flush=True)
        return True

    print(f"  no new image produced", flush=True)
    return False


def main() -> int:
    raws: list[Path] = []
    for i in (1, 2, 3):
        raw = HERE / f"raw_pro_{i}.png"
        if run_one(raw):
            raws.append(raw)

    print(f"\ngenerated {len(raws)}/3 raw backgrounds")
    if not raws:
        return 1

    print("\n=== compositing brand overlays ===")
    finals = []
    for raw in raws:
        final = HERE / f"post_pro_{raw.stem.split('_')[-1]}.png"
        compose(raw, final)
        finals.append(final)

    print(f"\nDONE - {len(finals)} production-ready posts:")
    for f in finals:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
