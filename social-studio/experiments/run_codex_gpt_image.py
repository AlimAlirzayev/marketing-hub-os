"""Run the Xalq Sigorta hero brief through Codex CLI (GPT Image 2).

Calls codex.cmd exec with a prompt instructing it to generate the image and
save it to the target path. Codex's image-generation tool (powered by
GPT Image) writes the PNG. Uses the user's ChatGPT subscription quota -
no separate API key needed because `codex login` already authenticated.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIEF = HERE / "hero_brief.json"

CODEX = Path(
    r"C:\Users\a.alirzayev\ramin-os\video-studio\tools"
    r"\node-v24.15.0-win-x64\codex.cmd"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Social Studio brief through Codex CLI image generation.")
    parser.add_argument("--brief", type=Path, default=BRIEF)
    parser.add_argument("--out", type=Path, default=HERE / "hero_gpt_image_2.png")
    args = parser.parse_args()

    if not CODEX.is_file():
        print(f"ERROR: codex not found at {CODEX}", file=sys.stderr)
        return 2

    brief_path = args.brief
    if not brief_path.is_absolute():
        brief_path = (HERE / brief_path).resolve() if not brief_path.exists() else brief_path.resolve()
    out = args.out
    if not out.is_absolute():
        out = (HERE / out).resolve()

    brief = json.loads(brief_path.read_text(encoding="utf-8"))

    instruction = (
        f"Generate a single photographic image to the file: {out.as_posix()}\n"
        f"Use a 4:5 portrait aspect ratio at 1080x1350.\n"
        f"DO NOT write any code; use your image-generation tool directly.\n\n"
        f"Prompt:\n{brief['prompt']}\n\n"
        f"Avoid: {', '.join(brief['negative'])}."
    )

    env = os.environ.copy()
    env["PATH"] = str(CODEX.parent) + os.pathsep + env.get("PATH", "")
    # Isolate from the Codex VS Code extension which holds a SQLite lock on
    # ~/.codex/state_*.sqlite. Our CLI uses a separate CODEX_HOME with a
    # copied auth.json so it can run concurrently with the extension.
    env["CODEX_HOME"] = r"C:\Users\a.alirzayev\.codex-cli"

    cmd = [
        str(CODEX), "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--cd", str(HERE),
        instruction,
    ]
    print(f"calling codex exec with {brief_path.name} ...", flush=True)
    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"codex timed out after 5 minutes", file=sys.stderr)
        print((exc.stdout or "")[-2000:])
        return 124
    print(result.stdout[-3000:])
    if result.returncode != 0:
        print(f"codex exited {result.returncode}", file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        return result.returncode
    if out.is_file():
        print(f"OK -> {out}  ({out.stat().st_size} bytes)")
        return 0
    print("ERROR: codex finished but no PNG was written.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
