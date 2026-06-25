"""Xalq Insurance Digital OS Video Studio - FFmpeg operations.

The deterministic half of the pipeline. Every function here is a thin, typed
wrapper around one FFmpeg invocation: probe, trim, cut, retime, reformat,
normalise, and mix music. render.py sequences these; the LLM never calls them.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from paths import ffmpeg_bin, ffprobe_bin, subprocess_env

# Pixel dimensions per aspect ratio. 1080 on the short edge keeps every
# platform happy without paying for 4K render time.
ASPECT_RESOLUTION: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}


@dataclass(frozen=True)
class Probe:
    """The handful of facts about a video that the pipeline actually needs."""

    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an FFmpeg/ffprobe command, raising with stderr on failure."""
    result = subprocess.run(
        args,
        env=subprocess_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(args[:3])} ...\n"
            f"{result.stderr.strip()[-2000:]}"
        )
    return result


def probe(path: str | Path) -> Probe:
    """Read duration, resolution, fps, and audio presence from a media file."""
    result = _run(
        [
            ffprobe_bin(), "-v", "error",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(path),
        ]
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"no video stream in {path}")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    num, den = (video.get("r_frame_rate", "30/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)

    return Probe(
        duration=float(data["format"]["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        has_audio=has_audio,
    )


def _atempo_chain(speed: float) -> str:
    """FFmpeg atempo accepts 0.5-2.0 per filter; chain factors for the rest."""
    factors: list[float] = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return ",".join(f"atempo={f:.6f}" for f in factors)


def _format_filter(w: int, h: int, fit: str) -> str:
    """Video filter that fits any source into a w*h frame.

    cover   = scale up and crop (fills the frame, no bars).
    contain = scale to fit on a blurred copy of itself (no crop, no black).
    """
    if fit == "contain":
        return (
            f"split=2[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},gblur=sigma=20[bgb];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
        )
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}"
    )


def trim(src: Path, dst: Path, start: str | None, end: str | None) -> None:
    """Cut the head/tail off a clip. Re-encodes for frame-accurate edges."""
    args = [ffmpeg_bin(), "-y"]
    if start:
        args += ["-ss", start]
    if end:
        args += ["-to", end]
    args += ["-i", str(src), "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(dst)]
    _run(args)


def remove_cuts(
    src: Path,
    dst: Path,
    cuts: list[dict],
    total_duration: float,
) -> None:
    """Delete inner ranges from a clip and concat what's left.

    ``cuts`` is a list of {"from","to"} HH:MM:SS strings. The kept segments
    are the complement of those ranges within [0, total_duration].
    """
    ranges = sorted((_to_seconds(c["from"]), _to_seconds(c["to"])) for c in cuts)
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in ranges:
        if start > cursor:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total_duration:
        keep.append((cursor, total_duration))

    # Build one filtergraph: trim each kept segment, then concat.
    parts: list[str] = []
    labels: list[str] = []
    for i, (start, end) in enumerate(keep):
        parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
        )
        labels += [f"[v{i}]", f"[a{i}]"]
    concat = "".join(labels) + f"concat=n={len(keep)}:v=1:a=1[v][a]"
    filtergraph = ";".join(parts + [concat])

    _run([
        ffmpeg_bin(), "-y", "-i", str(src),
        "-filter_complex", filtergraph,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", str(dst),
    ])


def _to_seconds(timestamp: str) -> float:
    """Parse an HH:MM:SS(.mmm) string into float seconds."""
    parts = [float(p) for p in timestamp.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def build_base(
    src: Path,
    dst: Path,
    *,
    speed: float,
    width: int,
    height: int,
    fps: int,
    fit: str,
    normalize: bool,
    has_audio: bool,
) -> None:
    """Produce the clean base clip: retimed, reformatted, loudness-normalised.

    This is the single re-encode that does speed + aspect + audio in one
    filtergraph, so quality is only lost once.
    """
    vf = f"setpts=PTS/{speed},{_format_filter(width, height, fit)},fps={fps}"
    args = [ffmpeg_bin(), "-y", "-i", str(src), "-vf", vf]

    if has_audio:
        af = _atempo_chain(speed)
        if normalize:
            af += ",loudnorm=I=-16:TP=-1.5:LRA=11"
        args += ["-af", af]
    else:
        # Silent source: synthesise a quiet track so later stages always
        # have an audio channel to mix against.
        args = [
            ffmpeg_bin(), "-y", "-i", str(src),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf", vf, "-shortest",
        ]

    args += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        str(dst),
    ]
    _run(args)


def cut_clip(
    src: Path,
    dst: Path,
    *,
    start: float,
    end: float,
    width: int,
    height: int,
    fit: str = "cover",
    has_audio: bool = True,
) -> None:
    """Cut the [start, end] second window out of src and reframe to width×height.

    One re-encode that does seek + trim + aspect reframe, so a long 16:9 source
    becomes a platform-ready vertical short in a single pass. Used by the viral
    clipper. ``-ss`` before ``-i`` is a fast input seek; ``-t`` is the duration.
    """
    vf = _format_filter(width, height, fit)
    args = [
        ffmpeg_bin(), "-y",
        "-ss", f"{max(0.0, start):.3f}",
        "-i", str(src),
        "-t", f"{max(0.1, end - start):.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p",
    ]
    args += ["-c:a", "aac", "-b:a", "192k"] if has_audio else ["-an"]
    args.append(str(dst))
    _run(args)


def extract_audio(src: Path, dst: Path) -> None:
    """Pull a 16 kHz mono WAV out of a video for speech transcription."""
    _run([
        ffmpeg_bin(), "-y", "-i", str(src),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(dst),
    ])


def mix_music(
    video: Path,
    music: Path,
    dst: Path,
    *,
    gain_db: float,
    ducking: bool,
) -> None:
    """Lay a music bed under a finished video.

    With ducking on, the music dips automatically whenever the speaker talks
    (sidechain compression keyed off the voice track).
    """
    music_chain = f"volume={gain_db}dB"
    if ducking:
        filter_complex = (
            f"[1:a]aloop=loop=-1:size=2e9,{music_chain}[mraw];"
            f"[mraw][0:a]sidechaincompress=threshold=0.03:ratio=8:"
            f"attack=20:release=400[mduck];"
            f"[0:a][mduck]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
    else:
        filter_complex = (
            f"[1:a]aloop=loop=-1:size=2e9,{music_chain}[mraw];"
            f"[0:a][mraw]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
    _run([
        ffmpeg_bin(), "-y",
        "-i", str(video), "-i", str(music),
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(dst),
    ])
