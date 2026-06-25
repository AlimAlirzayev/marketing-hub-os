"""Run the v2 master-level prompt through Pollinations (free FLUX schnell)
to demonstrate pure prompt-engineering ROI on the same model.

This is the apples-to-apples comparison vs the original render_post.py run:
- Same model (Pollinations turbo / FLUX schnell)
- Same compositing layer
- Different prompt (amateur v1 vs master-level v2)
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
STUDIO = HERE.parent
sys.path.insert(0, str(STUDIO))
from render_post import compose, W, H  # noqa: E402

BRIEF = json.loads((HERE / "hero_brief_v2.json").read_text(encoding="utf-8"))
PROMPT = BRIEF["prompt"]
NEG = ", ".join(BRIEF["negative"])


def generate(seed: int, out: Path) -> bool:
    full = f"{PROMPT}\n\nDO NOT: {NEG}"
    # Pollinations URL length tolerates ~4k chars; v2 prompt is ~3.5k.
    encoded = urllib.parse.quote(full)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={W}&height={H}&model=turbo&seed={seed}&nologo=true&enhance=true"
    )
    print(f"  seed={seed}: requesting (URL {len(encoded)} chars)", flush=True)
    try:
        r = requests.get(url, timeout=240)
        r.raise_for_status()
        out.write_bytes(r.content)
        print(f"  seed={seed}: got {out.stat().st_size // 1024} KB", flush=True)
        return True
    except Exception as exc:
        print(f"  seed={seed}: FAILED - {exc}", file=sys.stderr)
        return False


def main() -> int:
    seeds = [42, 1337, 7890]
    raws = []
    for s in seeds:
        raw = HERE / f"raw_pro_flux_{s}.png"
        if generate(s, raw):
            raws.append(raw)

    print("\ncompositing ...")
    finals = []
    for raw in raws:
        final = HERE / f"post_pro_flux_{raw.stem.split('_')[-1]}.png"
        compose(raw, final)
        finals.append(final)

    print(f"\nDONE - {len(finals)} v2 FLUX variants:")
    for f in finals:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
