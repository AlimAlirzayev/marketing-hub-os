"""Run the Xalq Sigorta hero brief through Gemini Nano Banana 2.

Reads hero_brief.json, calls gemini-2.5-flash-image, writes a PNG.
Requires: GEMINI_API_KEY env var (free tier from aistudio.google.com/apikey).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

HERE = Path(__file__).resolve().parent
BRIEF = HERE / "hero_brief.json"

MODEL = "gemini-2.5-flash-image"  # Nano Banana 1 (free tier; v2 is paid-only)


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("ERROR: GEMINI_API_KEY is not set.", file=sys.stderr)
        return 2

    brief = json.loads(BRIEF.read_text(encoding="utf-8"))
    prompt = brief["prompt"]
    negative = ", ".join(brief["negative"])
    # Gemini doesn't have a structured negative-prompt param, so fold it in.
    full = f"{prompt}\n\nDo NOT include: {negative}."

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=MODEL,
        contents=full,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    out = HERE / "hero_nano_banana_2.png"
    written = False
    for part in resp.candidates[0].content.parts:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            out.write_bytes(part.inline_data.data)
            written = True
            break

    if not written:
        print("ERROR: no image returned. Response text:", file=sys.stderr)
        print(getattr(resp, "text", "<no text>"), file=sys.stderr)
        return 1

    print(f"OK -> {out}  ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
