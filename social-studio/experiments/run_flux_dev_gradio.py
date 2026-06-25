"""Generate via FLUX.1-dev hosted on a public HF Gradio Space.

Uses gradio_client to call the Space directly (no API key, no MCP). FLUX.1-dev
is the 12B-parameter mid-tier model — significantly better photorealism and
prompt adherence than FLUX schnell (4-step distilled). 28 inference steps
default. ZeroGPU queuing applies; 2-5 min per request when the space is busy.

This is the documented `gradio_client` fallback in the cascade defined in
`prompt_kit/model_dialects/flux-schnell.md` (note: schnell-specific dialect;
flux-dev tolerates the longer master prompts).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from gradio_client import Client

HERE = Path(__file__).resolve().parent
DEFAULT_BRIEF = HERE / "xs_georgia_train_new_route_v3_flux.json"


def run(brief_path: Path, out_dir: Path, seeds: list[int]) -> list[Path]:
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    prompt = brief["prompt"]
    w, h = brief["format"]["resolution"]

    print(f"connecting to FLUX.1-dev Space ...", flush=True)
    client = Client("black-forest-labs/FLUX.1-dev", verbose=False)
    print(f"connected. prompt = {len(prompt)} chars", flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    delivered: list[Path] = []

    for seed in seeds:
        print(f"\nseed={seed}: submitting to ZeroGPU queue ...", flush=True)
        t0 = time.time()
        try:
            result = client.predict(
                prompt=prompt,
                seed=seed,
                randomize_seed=False,
                width=w,
                height=h,
                guidance_scale=3.5,
                num_inference_steps=28,
                api_name="/infer",
            )
        except Exception as exc:
            print(f"  FAILED: {exc}", flush=True)
            continue

        dt = time.time() - t0
        print(f"  rendered in {dt:.1f}s", flush=True)

        # client returns (image_path, seed) — image_path is a local tmp file.
        img_path = result[0] if isinstance(result, (list, tuple)) else result
        if isinstance(img_path, dict):
            img_path = img_path.get("path") or img_path.get("url")
        if not img_path:
            print(f"  no image path in result: {result}", flush=True)
            continue

        out = out_dir / f"raw_flux_dev_{seed}.png"
        shutil.copy2(img_path, out)
        print(f"  saved -> {out.relative_to(HERE.parent)}", flush=True)
        delivered.append(out)

    return delivered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", type=Path, default=DEFAULT_BRIEF)
    parser.add_argument("--out", type=Path,
                        default=HERE.parent / "output" / "georgia-train-new-route")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 1337, 7890])
    args = parser.parse_args()

    paths = run(args.brief, args.out, args.seeds)
    print(f"\nDONE: {len(paths)}/{len(args.seeds)} variants via FLUX.1-dev")
    return 0 if paths else 1


if __name__ == "__main__":
    raise SystemExit(main())
