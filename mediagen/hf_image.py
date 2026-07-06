#!/usr/bin/env python3
"""
HuggingFace Spaces image generator.
Calls any public Gradio Space via gradio_client — free, no API key needed.

Usage:
  python3 hf_image.py --prompt "..." --out output.jpg
  python3 hf_image.py --space stabilityai/stable-diffusion-3.5-large --prompt "..." --out output.jpg
  python3 hf_image.py --list-spaces
"""

import argparse
import sys
import os
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Space registry — tested and working as of 2026-04
# ---------------------------------------------------------------------------
SPACES = {
    "flux-dev": {
        "id": "black-forest-labs/FLUX.1-dev",
        "api_name": "/infer",
        "params": lambda p, w, h, steps, guidance, neg: {
            "prompt": p,
            "width": w,
            "height": h,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "seed": 0,
        },
        "result_index": 0,
    },
    "flux-schnell": {
        "id": "black-forest-labs/FLUX.1-schnell",
        "api_name": "/infer",
        "params": lambda p, w, h, steps, guidance, neg: {
            "prompt": p,
            "width": w,
            "height": h,
            "num_inference_steps": min(steps, 4),
            "seed": 0,
        },
        "result_index": 0,
    },
    "sd35-large": {
        "id": "stabilityai/stable-diffusion-3.5-large",
        "api_name": "/infer",
        "params": lambda p, w, h, steps, guidance, neg: {
            "prompt": p,
            "negative_prompt": neg,
            "width": w,
            "height": h,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "seed": 0,
        },
        "result_index": 0,
    },
    "flux-lora": {
        "id": "multimodalart/flux-lora-the-explorer",
        "api_name": "/run_lora",
        "params": lambda p, w, h, steps, guidance, neg: {
            "prompt": p,
            "image_size": f"{w}x{h}",
            "num_inference_steps": steps,
            "guidance_scale": guidance,
        },
        "result_index": 0,
    },
}

DEFAULT_SPACE = "flux-dev"
DEFAULT_NEGATIVE = (
    "blurry, low quality, watermark, text, logo, distorted faces, "
    "bad anatomy, extra limbs, deformed, ugly, worst quality"
)


def list_spaces():
    print("Available spaces:")
    for alias, info in SPACES.items():
        print(f"  {alias:20s}  {info['id']}")


def generate(space_id_or_alias, prompt, out_path, width, height, steps, guidance, negative):
    try:
        from gradio_client import Client
    except ImportError:
        print("ERROR: gradio_client not installed. Run: pip3 install gradio_client", file=sys.stderr)
        sys.exit(1)

    # Resolve alias or direct Space ID
    if space_id_or_alias in SPACES:
        space_cfg = SPACES[space_id_or_alias]
        space_id = space_cfg["id"]
    else:
        # Treat as raw Space ID, use flux-dev param pattern as default
        space_id = space_id_or_alias
        space_cfg = SPACES["flux-dev"]
        space_cfg = dict(space_cfg, id=space_id)

    print(f"Connecting to Space: {space_id}", file=sys.stderr)

    try:
        client = Client(space_id, verbose=False)
    except Exception as e:
        print(f"ERROR connecting to {space_id}: {e}", file=sys.stderr)
        sys.exit(1)

    params = space_cfg["params"](prompt, width, height, steps, guidance, negative)
    print(f"Generating image ({width}x{height}, {steps} steps)...", file=sys.stderr)

    try:
        result = client.predict(**params, api_name=space_cfg["api_name"])
    except Exception as e:
        print(f"ERROR during prediction: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract file path from result
    idx = space_cfg.get("result_index", 0)
    if isinstance(result, (list, tuple)):
        result_file = result[idx]
        if isinstance(result_file, dict):
            result_file = result_file.get("path") or result_file.get("name") or list(result_file.values())[0]
    elif isinstance(result, dict):
        result_file = result.get("path") or result.get("name") or list(result.values())[0]
    else:
        result_file = result

    if not result_file or not os.path.exists(str(result_file)):
        print(f"ERROR: No output file found in result: {result}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(result_file), str(out_path))
    print(str(out_path))
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="HuggingFace Spaces image generator")
    parser.add_argument("--space", default=DEFAULT_SPACE,
                        help=f"Space alias or HF Space ID (default: {DEFAULT_SPACE})")
    parser.add_argument("--prompt", required=False, help="Image generation prompt")
    parser.add_argument("--negative", default=DEFAULT_NEGATIVE, help="Negative prompt")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--guidance", type=float, default=7.5)
    parser.add_argument("--out", default="output.jpg", help="Output file path")
    parser.add_argument("--list-spaces", action="store_true", help="List available spaces and exit")

    args = parser.parse_args()

    if args.list_spaces:
        list_spaces()
        return

    if not args.prompt:
        # Read from stdin
        if not sys.stdin.isatty():
            args.prompt = sys.stdin.read().strip()
        else:
            print("ERROR: --prompt required or pipe prompt via stdin", file=sys.stderr)
            sys.exit(1)

    generate(
        space_id_or_alias=args.space,
        prompt=args.prompt,
        out_path=args.out,
        width=args.width,
        height=args.height,
        steps=args.steps,
        guidance=args.guidance,
        negative=args.negative,
    )


if __name__ == "__main__":
    main()
