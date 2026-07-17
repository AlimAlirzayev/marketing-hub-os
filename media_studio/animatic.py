"""FREE local animatic: selected keyframes -> a timed Ken Burns cut.

Professionals never go to the expensive shoot before cutting an animatic from
the boards. Same here: this stage costs ZERO credits — pure local ffmpeg. Each
selected keyframe becomes a beat-length clip with a slow push-in/out (alternating
for rhythm), the clips are concatenated to the exact storyboard timing, and the
result lets a human approve TIMING + LOOK before any paid video generation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FPS = 30
W, H = 1080, 1920


def find_ffmpeg() -> str | None:
    hits = sorted((ROOT / "video-studio" / "tools").rglob("ffmpeg.exe"))
    if hits:
        return str(hits[0])
    import shutil
    return shutil.which("ffmpeg")


def beat_clip_cmd(ffmpeg: str, image: Path, out: Path, *, seconds: float,
                  zoom_in: bool = True) -> list[str]:
    """One keyframe -> one beat-length Ken Burns clip (build the command only)."""
    frames = max(1, int(round(seconds * FPS)))
    # Oversample before zoompan to avoid subpixel jitter.
    if zoom_in:
        zexpr = f"min(zoom+{0.10 / frames:.6f},1.10)"
    else:
        zexpr = f"max(1.10-{0.10 / frames:.6f}*on,1.0)"
    vf = (
        f"scale={W * 2}:{H * 2},"
        f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p"
    )
    return [
        ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(image),
        "-vf", vf, "-t", f"{seconds:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(out),
    ]


def build_animatic(frame_paths: list[Path | None], durations: list[float],
                   out_path: Path) -> dict[str, Any]:
    """Render the animatic. Returns a status dict; never raises on a beat gap."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg tapılmadı (video-studio/tools və PATH yoxlandı)"}

    usable = [(i, p, durations[i]) for i, p in enumerate(frame_paths) if p and p.exists()]
    if not usable:
        return {"ok": False, "error": "seçilmiş keyframe yoxdur — əvvəlcə --frames mərhələsini işə sal"}

    work = out_path.parent / "_animatic_work"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for n, (i, img, dur) in enumerate(usable):
        clip = work / f"beat{i}.mp4"
        cmd = beat_clip_cmd(ffmpeg, img, clip, seconds=dur, zoom_in=(n % 2 == 0))
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return {"ok": False, "error": f"beat{i} klip xətası: {res.stderr[-300:]}"}
        clips.append(clip)

    concat_list = work / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{c.resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    res = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-c", "copy", str(out_path)],
        capture_output=True, text=True)
    if res.returncode != 0:
        return {"ok": False, "error": f"concat xətası: {res.stderr[-300:]}"}

    total = sum(d for _, _, d in usable)
    return {"ok": True, "path": str(out_path), "beats": len(clips),
            "duration_s": round(total, 2), "cost": "0 kredit (lokal ffmpeg)"}


def stitch_beats(clip_paths: list[Path], durations: list[float],
                 out_path: Path) -> dict[str, Any]:
    """Trim each generated beat clip to its storyboard duration and concat.

    Generated clips are longer than the beat (models have minimum durations);
    pros shoot long and cut short — same rule here. Everything is re-encoded to
    one uniform format so concat is bulletproof.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg tapılmadı"}
    if not clip_paths:
        return {"ok": False, "error": "beat klipləri yoxdur"}

    work = out_path.parent / "_stitch_work"
    work.mkdir(parents=True, exist_ok=True)
    trimmed: list[Path] = []
    for i, (clip, dur) in enumerate(zip(clip_paths, durations)):
        if not clip.exists():
            return {"ok": False, "error": f"klip yoxdur: {clip.name}"}
        t = work / f"trim{i}.mp4"
        res = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(clip), "-t", f"{dur:.3f}",
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},fps={FPS},format=yuv420p",
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(t)],
            capture_output=True, text=True)
        if res.returncode != 0:
            return {"ok": False, "error": f"trim{i} xətası: {res.stderr[-300:]}"}
        trimmed.append(t)

    concat_list = work / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{c.resolve().as_posix()}'\n" for c in trimmed), encoding="utf-8")
    res = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-c", "copy", str(out_path)],
        capture_output=True, text=True)
    if res.returncode != 0:
        return {"ok": False, "error": f"concat xətası: {res.stderr[-300:]}"}
    return {"ok": True, "path": str(out_path),
            "duration_s": round(sum(durations), 2), "beats": len(trimmed)}
