"""Xalq Insurance Digital OS Video Studio - render pipeline.

Turns one edit_spec.json into one finished video. This is the deterministic
executor: it never improvises. The LLM (the marketing crew's Video Editor
agent, or Claude Code via /edit-video) decides *what* to do and writes the
spec; this file does *exactly* that and nothing else.

Pipeline:
    raw.mp4
      -> trim          (drop dead head/tail)
      -> remove_cuts   (drop inner mistakes/pauses)
      -> build_base    (speed + aspect/resolution + loudness)   = base.mp4
      -> transcribe    (Whisper -> word-timed English captions)
      -> Remotion      (intro + outro + lower-thirds + captions) = rendered.mp4
      -> mix_music     (energetic electronic bed, ducked)        = output.mp4

Usage:
    python render.py edit_spec.json
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import ffmpeg_ops as ff
from paths import REMOTION_DIR, STUDIO_DIR, node_dir, subprocess_env
from transcribe import transcribe

WORK_DIR = STUDIO_DIR / "work"
LOG_DIR = STUDIO_DIR.parent / "data" / "logs"
MUSIC_DIR = STUDIO_DIR / "music"
REMOTION_PUBLIC = REMOTION_DIR / "public"


# --------------------------------------------------------------------------
# Spec loading
# --------------------------------------------------------------------------

def load_spec(spec_path: Path) -> dict:
    """Read an edit spec and validate it against edit_spec.schema.json."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    schema_path = STUDIO_DIR / "edit_spec.schema.json"
    try:
        import jsonschema

        jsonschema.validate(spec, json.loads(schema_path.read_text("utf-8")))
    except ImportError:
        print("! jsonschema not installed - skipping spec validation")
    return spec


def resolve_resolution(fmt: dict) -> tuple[int, int]:
    """Pick the output [width, height] from explicit value or aspect ratio."""
    if fmt.get("resolution"):
        w, h = fmt["resolution"]
        return int(w), int(h)
    return ff.ASPECT_RESOLUTION[fmt["aspect"]]


# --------------------------------------------------------------------------
# Music selection
# --------------------------------------------------------------------------

def pick_music(music_spec: dict) -> Path | None:
    """Resolve the music bed: explicit file, or auto-pick by mood tag."""
    track = music_spec.get("track", "auto")
    if track and track != "auto":
        candidate = STUDIO_DIR / track
        return candidate if candidate.is_file() else None

    manifest_path = MUSIC_DIR / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mood = music_spec.get("mood", "energetic-electronic")
    matches = [
        t for t in manifest.get("tracks", [])
        if mood in t.get("moods", []) and (MUSIC_DIR / t["file"]).is_file()
    ]
    if not matches:
        return _generate_music_bed(mood, music_spec)
    return MUSIC_DIR / random.choice(matches)["file"]


def _generate_music_bed(mood: str, music_spec: dict) -> Path | None:
    """No royalty-free track matched the mood — optionally generate one via Audio Studio.

    Off by default; opt in with AUDIO_STUDIO_GENERATE=1. Routes through the same
    free-first audio-gen cascade (HF Space -> ElevenLabs). Never a silent drop: on
    failure it prints why and returns None so render falls back to "no bed".
    """
    if os.environ.get("AUDIO_STUDIO_GENERATE", "").strip().lower() not in {"1", "true", "yes"}:
        return None
    audio_dir = STUDIO_DIR.parent / "audio-studio"
    try:
        sys.path.insert(0, str(audio_dir))
        import audio_studio as aud  # type: ignore

        prompt = music_spec.get("prompt") or f"{mood.replace('-', ' ')} background music bed, instrumental, loopable"
        duration = int(music_spec.get("duration", 30))
        out_dir = MUSIC_DIR / "_generated"
        providers = aud.cascade_for("music", quality=False, force=None)
        result = aud.run_cascade("music", providers, {
            "prompt": prompt, "duration": duration, "out": out_dir,
        })
        if result.get("path"):
            print(f"      music - generated a bed via Audio Studio [{result['provider']}]")
            return Path(result["path"])
        print("      music - Audio Studio cascade produced nothing; no bed")
        return None
    except Exception as e:
        print(f"      music - Audio Studio generation unavailable ({e}); no bed")
        return None


# --------------------------------------------------------------------------
# Remotion bridge
# --------------------------------------------------------------------------

def _npx() -> str:
    """Absolute path to npx.cmd from the portable Node install."""
    nd = node_dir()
    if nd is None:
        raise FileNotFoundError("Node.js not found - run scripts/install-video-tools.ps1")
    return str(nd / "npx.cmd")


def _npm() -> str:
    nd = node_dir()
    if nd is None:
        raise FileNotFoundError("Node.js not found - run scripts/install-video-tools.ps1")
    return str(nd / "npm.cmd")


def ensure_remotion_deps() -> None:
    """Install the Remotion project's node_modules on first run."""
    if (REMOTION_DIR / "node_modules").is_dir():
        return
    print("Installing Remotion dependencies (first run, one-off)...")
    subprocess.run(
        [_npm(), "install", "--no-audit", "--no-fund"],
        cwd=REMOTION_DIR,
        env=subprocess_env(),
        check=True,
    )


def render_remotion(props: dict, out_path: Path) -> None:
    """Render the Final composition with the given input props."""
    ensure_remotion_deps()
    REMOTION_PUBLIC.mkdir(parents=True, exist_ok=True)
    props_file = REMOTION_PUBLIC / "props.json"
    props_file.write_text(json.dumps(props, indent=2), encoding="utf-8")

    subprocess.run(
        [
            _npx(), "remotion", "render",
            "src/index.ts", "Final", str(out_path),
            f"--props={props_file}",
        ],
        cwd=REMOTION_DIR,
        env=subprocess_env(),
        check=True,
    )


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def render(spec_path: Path) -> Path:
    """Run the full pipeline for one spec and return the output path."""
    spec = load_spec(spec_path)
    job = spec["job"]
    timeline = spec.get("timeline", {})
    fmt = spec["format"]
    audio = spec.get("audio", {})
    caps = spec.get("captions", {})
    mg = spec.get("motion_graphics", {})

    src = (STUDIO_DIR / job["input"]).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"input video not found: {src}")
    out_path = (STUDIO_DIR / job["output"]).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    name = spec_path.stem
    work = WORK_DIR / name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    width, height = resolve_resolution(fmt)
    fps = int(fmt.get("fps", 30))
    speed = float(timeline.get("speed", 1.0))

    print(f"[1/6] probing {src.name}")
    info = ff.probe(src)
    clip = src

    trim = timeline.get("trim") or {}
    if trim.get("start") or trim.get("end"):
        print(f"[2/6] trim {trim.get('start') or 'start'} -> {trim.get('end') or 'end'}")
        trimmed = work / "trimmed.mp4"
        ff.trim(clip, trimmed, trim.get("start"), trim.get("end"))
        clip = trimmed
    else:
        print("[2/6] trim - skipped")

    cuts = timeline.get("cuts") or []
    if cuts:
        print(f"[3/6] removing {len(cuts)} inner cut(s)")
        cut = work / "cut.mp4"
        ff.remove_cuts(clip, cut, cuts, ff.probe(clip).duration)
        clip = cut
    else:
        print("[3/6] inner cuts - none")

    print(f"[4/6] base render: {speed}x speed, {width}x{height}@{fps}")
    base = work / "base.mp4"
    ff.build_base(
        clip, base,
        speed=speed, width=width, height=height, fps=fps,
        fit=fmt.get("fit", "cover"),
        normalize=audio.get("normalize", True),
        has_audio=info.has_audio,
    )
    base_info = ff.probe(base)

    # Captions: transcribe the base clip (post-speed, so timings are final).
    # A transcription failure must not sink the whole render - it degrades
    # gracefully to a captionless video.
    words: list[dict] = []
    if caps.get("enabled", True):
        print("[5/6] transcribing captions (Whisper, local)")
        try:
            wav = work / "base.wav"
            ff.extract_audio(base, wav)
            result = transcribe(wav, work / "captions.json",
                                language=caps.get("language", "en"))
            words = result["words"]
            print(f"      {len(words)} caption words")
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash
            print(f"      ! transcription failed ({exc}); continuing without captions")
    else:
        print("[5/6] captions - disabled")

    # Compose with Remotion - or skip it when there is nothing to draw.
    intro = mg.get("intro", {})
    outro = mg.get("outro", {})
    lowers = mg.get("lower_thirds", [])
    needs_remotion = (
        words or intro.get("enabled") or outro.get("enabled") or lowers
    )

    if needs_remotion:
        print("[6/6] compositing motion graphics (Remotion)")
        rendered = work / "rendered.mp4"
        render_remotion(
            build_props(base, base_info.duration, width, height, fps,
                        intro, outro, lowers, caps, words, mg.get("brand", {})),
            rendered,
        )
    else:
        print("[6/6] motion graphics - none, using base clip")
        rendered = base

    # Music bed.
    music = pick_music(audio.get("music", {}))
    if music:
        print(f"      mixing music: {music.name}")
        m = audio["music"]
        ff.mix_music(rendered, music, out_path,
                     gain_db=m.get("gain_db", -18),
                     ducking=m.get("ducking", True))
    else:
        if audio.get("music"):
            print("      music - no matching track in music/, skipping bed")
        shutil.copyfile(rendered, out_path)

    _write_log(name, spec, out_path)
    print(f"\nDONE -> {out_path}")
    return out_path


def build_props(
    base: Path, base_duration: float, width: int, height: int, fps: int,
    intro: dict, outro: dict, lowers: list[dict], caps: dict,
    words: list[dict], brand: dict,
) -> dict:
    """Translate the spec into Remotion input props (seconds -> frames)."""
    REMOTION_PUBLIC.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base, REMOTION_PUBLIC / "base.mp4")

    def frames(seconds: float) -> int:
        return max(1, round(seconds * fps))

    logo = brand.get("logo")
    if logo:
        logo_src = (STUDIO_DIR / logo)
        if logo_src.is_file():
            shutil.copyfile(logo_src, REMOTION_PUBLIC / "logo.png")
            logo = "logo.png"
        else:
            logo = None

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "baseVideo": "base.mp4",
        "baseDurationInFrames": frames(base_duration),
        "intro": {
            "enabled": bool(intro.get("enabled")),
            "title": intro.get("title", ""),
            "subtitle": intro.get("subtitle", ""),
            "durationInFrames": frames(intro.get("duration_s", 2.5)),
        },
        "outro": {
            "enabled": bool(outro.get("enabled")),
            "cta": outro.get("cta", ""),
            "durationInFrames": frames(outro.get("duration_s", 3)),
        },
        "lowerThirds": [
            {
                "atFrame": frames(ff._to_seconds(lt["at"])),
                "line1": lt.get("line1", ""),
                "line2": lt.get("line2", ""),
                "durationInFrames": frames(lt.get("duration_s", 3.5)),
            }
            for lt in lowers
        ],
        "captions": {
            "enabled": bool(words),
            "style": caps.get("style", "karaoke"),
            "position": caps.get("position", "bottom"),
            "words": words,
        },
        "brand": {
            "accentColor": brand.get("accent_color", "#00E5FF"),
            "logo": logo,
        },
    }


def _write_log(name: str, spec: dict, out_path: Path) -> None:
    """Append a one-line JSON record of the render to data/logs/."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "job": name,
        "platform": spec["job"].get("platform"),
        "speed": spec.get("timeline", {}).get("speed", 1.0),
        "output": str(out_path),
    }
    with (LOG_DIR / "video-studio.log").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python render.py <edit_spec.json>")
        raise SystemExit(2)
    render(Path(sys.argv[1]).resolve())
