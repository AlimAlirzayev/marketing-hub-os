"""Xalq Insurance Digital OS Video Studio - tool discovery.

Node.js and FFmpeg are installed portably under video-studio/tools/ because
winget is blocked by corporate Group Policy on this machine. This module
locates those binaries (falling back to PATH) and builds an environment dict
so subprocesses - FFmpeg and the Remotion CLI - can find everything.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

STUDIO_DIR = Path(__file__).resolve().parent
TOOLS_DIR = STUDIO_DIR / "tools"
REMOTION_DIR = STUDIO_DIR / "remotion"


def _find_in_tools(glob: str, leaf: str) -> Path | None:
    """Return the first matching binary under tools/, or None."""
    for match in TOOLS_DIR.glob(glob):
        candidate = match / leaf
        if candidate.is_file():
            return candidate
    return None


def ffmpeg_bin() -> str:
    """Absolute path to ffmpeg.exe (tools/ first, then PATH)."""
    found = _find_in_tools("ffmpeg-*/bin", "ffmpeg.exe")
    if found:
        return str(found)
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    raise FileNotFoundError(
        "ffmpeg not found. Run scripts/install-video-tools.ps1 or install FFmpeg."
    )


def ffprobe_bin() -> str:
    """Absolute path to ffprobe.exe (tools/ first, then PATH)."""
    found = _find_in_tools("ffmpeg-*/bin", "ffprobe.exe")
    if found:
        return str(found)
    on_path = shutil.which("ffprobe")
    if on_path:
        return on_path
    raise FileNotFoundError("ffprobe not found. Install FFmpeg.")


def node_dir() -> Path | None:
    """Directory holding node.exe / npx.cmd (tools/ first, then PATH)."""
    for match in TOOLS_DIR.glob("node-*-win-x64"):
        if (match / "node.exe").is_file():
            return match
    on_path = shutil.which("node")
    return Path(on_path).parent if on_path else None


def subprocess_env() -> dict[str, str]:
    """A copy of os.environ with the portable tool dirs prepended to PATH.

    Pass this as ``env=`` to every subprocess call so FFmpeg, node, and the
    Remotion CLI resolve regardless of the user's global PATH.
    """
    env = os.environ.copy()
    extra: list[str] = []

    nd = node_dir()
    if nd:
        extra.append(str(nd))

    ffmpeg = _find_in_tools("ffmpeg-*/bin", "ffmpeg.exe")
    if ffmpeg:
        extra.append(str(ffmpeg.parent))

    if extra:
        env["PATH"] = os.pathsep.join(extra) + os.pathsep + env.get("PATH", "")
    return env


if __name__ == "__main__":
    print(f"ffmpeg : {ffmpeg_bin()}")
    print(f"ffprobe: {ffprobe_bin()}")
    print(f"node   : {node_dir()}")
