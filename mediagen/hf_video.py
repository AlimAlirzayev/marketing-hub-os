#!/usr/bin/env python3
"""
HuggingFace Spaces video generator.
Calls open video model Spaces via gradio_client — free, no API key needed.

Supported models (all free on HF Spaces):
  wan21-t2v      Wan2.1 T2V  (Alibaba, Kling-quality, text→video)
  wan21-i2v      Wan2.1 I2V  (image→video)
  ltx2           LTX-Video-2 Turbo  (Lightricks, fastest cinematic)
  cogvideox      CogVideoX-5B  (Zhipu AI, text→video)
  hunyuan-i2v    HunyuanVideo I2V 1.5  (Tencent, image→video)
  wan22-s2v      Wan2.2 S2V  (audio-driven video)

Usage:
  python3 hf_video.py --prompt "..." --out output.mp4
  python3 hf_video.py --space wan21-i2v --image photo.jpg --prompt "camera slowly zooms in" --out clip.mp4
  python3 hf_video.py --list-spaces
"""

import argparse
import sys
import os
import shutil
from pathlib import Path

SPACES = {
    "wan21-t2v": {
        "id": "Wan-AI/Wan2.1-T2V-A14B",
        "api_name": "/generate_video",
        "mode": "t2v",
        "params": lambda prompt, image, duration, w, h: {
            "prompt": prompt,
            "num_frames": int(duration * 16),
            "width": w,
            "height": h,
            "num_inference_steps": 50,
            "guidance_scale": 7.5,
            "seed": -1,
        },
        "result_key": "video",
    },
    "wan21-i2v": {
        "id": "Wan-AI/Wan2.1-I2V-A14B",
        "api_name": "/generate_video",
        "mode": "i2v",
        "params": lambda prompt, image, duration, w, h: {
            "prompt": prompt,
            "image": image,
            "num_frames": int(duration * 16),
            "width": w,
            "height": h,
            "num_inference_steps": 50,
            "guidance_scale": 7.5,
            "seed": -1,
        },
        "result_key": "video",
    },
    "ltx2": {
        "id": "Lightricks/LTX-Video",
        "api_name": "/generate",
        "mode": "t2v",
        "params": lambda prompt, image, duration, w, h: {
            "prompt": prompt,
            "negative_prompt": "blurry, low quality, watermark, text",
            "num_frames": int(duration * 24),
            "width": w,
            "height": h,
            "num_inference_steps": 40,
            "guidance_scale": 7.5,
            "seed": -1,
        },
        "result_key": 0,
    },
    "cogvideox": {
        "id": "zai-org/CogVideoX-5B-Space",
        "api_name": "/generate_video",
        "mode": "t2v",
        "params": lambda prompt, image, duration, w, h: {
            "prompt": prompt,
            "num_frames": 49,
            "guidance_scale": 6.0,
            "num_inference_steps": 50,
            "seed": -1,
        },
        "result_key": "video_path",
    },
    "hunyuan-i2v": {
        "id": "multimodalart/Hunyuan-Video-1-5",
        "api_name": "/generate",
        "mode": "i2v",
        "params": lambda prompt, image, duration, w, h: {
            "prompt": prompt,
            "image": image,
            "num_frames": int(duration * 24),
            "guidance_scale": 6.0,
            "num_inference_steps": 50,
            "seed": -1,
        },
        "result_key": 0,
    },
    "wan22-s2v": {
        "id": "Wan-AI/Wan2.2-S2V",
        "api_name": "/generate",
        "mode": "s2v",
        "params": lambda prompt, image, duration, w, h: {
            "image": image,
            "prompt": prompt,
            "num_frames": int(duration * 16),
            "seed": -1,
        },
        "result_key": 0,
    },
    "lipsync": {
        "id": "linoyts/LTX-2-3-sync",
        "api_name": "/generate",
        "mode": "lipsync",
        "params": lambda prompt, image, duration, w, h: {
            "image": image,
            "prompt": prompt,
        },
        "result_key": 0,
    },
}

PRIORITY_ORDER = ["wan21-t2v", "ltx2", "cogvideox"]
PRIORITY_I2V = ["wan21-i2v", "hunyuan-i2v", "ltx2"]


def list_spaces():
    print("Available video spaces:")
    for alias, info in SPACES.items():
        mode = info.get("mode", "?")
        print(f"  {alias:20s}  [{mode:8s}]  {info['id']}")


def extract_path(result, key):
    if isinstance(result, (list, tuple)):
        if isinstance(key, int):
            val = result[key]
        else:
            val = result[0]
        if isinstance(val, dict):
            return val.get("path") or val.get("name") or val.get("video") or list(val.values())[0]
        return val
    if isinstance(result, dict):
        return result.get(key) or result.get("path") or result.get("video") or list(result.values())[0]
    return result


def generate(space_alias, prompt, image_path, out_path, duration, width, height):
    try:
        from gradio_client import Client, handle_file
    except ImportError:
        print("ERROR: gradio_client not installed. Run: pip3 install gradio_client", file=sys.stderr)
        sys.exit(1)

    if space_alias not in SPACES:
        print(f"ERROR: unknown space '{space_alias}'. Use --list-spaces to see options.", file=sys.stderr)
        sys.exit(1)

    cfg = SPACES[space_alias]
    space_id = cfg["id"]
    mode = cfg["mode"]

    if mode in ("i2v", "s2v", "lipsync") and not image_path:
        print(f"ERROR: space '{space_alias}' requires --image", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to Space: {space_id}", file=sys.stderr)
    try:
        client = Client(space_id, verbose=False)
    except Exception as e:
        print(f"ERROR connecting: {e}", file=sys.stderr)
        sys.exit(1)

    image_arg = handle_file(image_path) if image_path and os.path.exists(image_path) else image_path
    params = cfg["params"](prompt, image_arg, duration, width, height)

    print(f"Generating video ({width}x{height}, {duration}s)...", file=sys.stderr)
    try:
        result = client.predict(**params, api_name=cfg["api_name"])
    except Exception as e:
        print(f"ERROR during prediction: {e}", file=sys.stderr)
        sys.exit(1)

    result_file = extract_path(result, cfg["result_key"])

    if not result_file or not os.path.exists(str(result_file)):
        print(f"ERROR: No output file in result: {result}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(result_file), str(out_path))
    print(str(out_path))
    return str(out_path)


def auto_generate(prompt, image_path, out_path, duration, width, height):
    """Try spaces in priority order until one succeeds."""
    order = PRIORITY_I2V if image_path else PRIORITY_ORDER
    for alias in order:
        print(f"Trying {alias}...", file=sys.stderr)
        try:
            return generate(alias, prompt, image_path, out_path, duration, width, height)
        except SystemExit:
            print(f"  {alias} failed, trying next...", file=sys.stderr)
    print("ERROR: All video spaces failed.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="HuggingFace Spaces video generator")
    parser.add_argument("--space", default="auto",
                        help="Space alias (default: auto — tries best spaces in order)")
    parser.add_argument("--prompt", required=False)
    parser.add_argument("--image", help="Input image for I2V mode")
    parser.add_argument("--duration", type=float, default=5.0, help="Video duration in seconds")
    parser.add_argument("--width", type=int, default=848)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--out", default="output.mp4")
    parser.add_argument("--list-spaces", action="store_true")

    args = parser.parse_args()

    if args.list_spaces:
        list_spaces()
        return

    if not args.prompt:
        if not sys.stdin.isatty():
            args.prompt = sys.stdin.read().strip()
        else:
            print("ERROR: --prompt required", file=sys.stderr)
            sys.exit(1)

    if args.space == "auto":
        auto_generate(args.prompt, args.image, args.out, args.duration, args.width, args.height)
    else:
        generate(args.space, args.prompt, args.image, args.out, args.duration, args.width, args.height)


if __name__ == "__main__":
    main()
