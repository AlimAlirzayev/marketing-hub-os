#!/usr/bin/env python3
"""
prep_dataset.py — turn ONE long voice recording into a clean finetune dataset.

This prepares the corpus for Phase 2/3 of audio-studio/VOICE_ROADMAP.md: a personal
Azerbaijani voice via XTTS-v2 finetune. You record 30-60 min of the target speaker
(see audio-studio/voices/RECORDING_GUIDE.md); this splits it on silence into short
single-utterance clips, transcribes each (free Gemini ASR), and writes the metadata
files XTTS finetuning expects.

No GPU / native ML — just ffmpeg (bundled) + Gemini ASR. Output is ready to upload to
a free Colab/Kaggle T4 for the actual finetune.

Usage:
    python audio-studio/prep_dataset.py voices/raminin_sesi.wav --speaker ramin
    python audio-studio/prep_dataset.py voices/long.m4a --speaker ramin --min 3 --max 14

Output (under audio-studio/dataset/<speaker>/):
    wavs/0001.wav, 0002.wav, ...        (22.05kHz mono, one utterance each)
    metadata.csv                        (XTTS: wav|text|speaker, '|' separated)
    metadata_ljspeech.csv               (LJSpeech: id|text|text)
    report.json                         (durations, total minutes, CER-flagged clips)

After this: upload audio-studio/dataset/<speaker>/ to the Colab notebook in
VOICE_ROADMAP.md (Phase 3) and finetune. Review report.json — drop clips whose ASR
looks wrong before training.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDIO = Path(__file__).resolve().parent
sys.path.insert(0, str(STUDIO))
import audio_studio as aud  # reuse env loading, ffmpeg locate, Gemini ASR


def _ffmpeg() -> str:
    ff = aud._ffmpeg_exe()
    if not ff:
        sys.exit("ffmpeg not found (expected the bundled video-studio build).")
    return ff


def split_on_silence(src: Path, out_dir: Path, min_s: float, max_s: float,
                     silence_db: int = -34, silence_dur: float = 0.4) -> list[Path]:
    """Use ffmpeg silencedetect to find pauses, then cut utterance clips between them."""
    ff = _ffmpeg()
    # 1) detect silence boundaries
    probe = subprocess.run(
        [ff, "-i", str(src), "-af",
         f"silencedetect=noise={silence_db}dB:d={silence_dur}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    log = probe.stderr
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", log)]
    # total duration
    dprobe = subprocess.run(
        [ff.replace("ffmpeg.exe", "ffprobe.exe"), "-v", "error",
         "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(src)],
        capture_output=True, text=True,
    )
    try:
        total = float(dprobe.stdout.strip())
    except ValueError:
        total = ends[-1] if ends else 0.0

    # 2) speech segments = gaps between silences
    segments: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in zip(starts, ends + [total]):
        if s > cursor + 0.05:
            segments.append((cursor, s))
        cursor = e
    if cursor < total - 0.05:
        segments.append((cursor, total))

    # 3) merge/trim into min..max windows
    clips: list[tuple[float, float]] = []
    for a, b in segments:
        dur = b - a
        if dur < min_s:
            continue
        if dur <= max_s:
            clips.append((a, b))
        else:  # long monologue → chop into <=max windows
            t = a
            while t < b:
                clips.append((t, min(t + max_s, b)))
                t += max_s

    # 4) cut the wavs (22.05kHz mono — XTTS training rate)
    wavs_dir = out_dir / "wavs"
    wavs_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, (a, b) in enumerate(clips, 1):
        dst = wavs_dir / f"{i:04d}.wav"
        subprocess.run(
            [ff, "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
             "-ar", "22050", "-ac", "1", str(dst)],
            capture_output=True,
        )
        if dst.is_file() and dst.stat().st_size > 0:
            paths.append(dst)
    return paths


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio", help="the long recording (wav/m4a/mp3) of ONE speaker")
    p.add_argument("--speaker", default="speaker", help="speaker id (folder + metadata column)")
    p.add_argument("--lang", default="az")
    p.add_argument("--min", type=float, default=2.0, help="min clip seconds")
    p.add_argument("--max", type=float, default=14.0, help="max clip seconds")
    p.add_argument("--silence-db", type=int, default=-34)
    p.add_argument("--no-asr", action="store_true", help="skip transcription (fill text later)")
    args = p.parse_args(argv)

    src = Path(args.audio)
    if not src.is_absolute():
        src = (STUDIO / src) if (STUDIO / src).exists() else (ROOT / src)
    if not src.is_file():
        sys.exit(f"audio not found: {args.audio}")

    out_dir = STUDIO / "dataset" / args.speaker
    print(f"==> splitting {src.name} on silence ...", file=sys.stderr)
    clips = split_on_silence(src, out_dir, args.min, args.max, args.silence_db)
    if not clips:
        sys.exit("no clips produced — try a lower --silence-db (e.g. -40) or check the audio.")
    print(f"==> {len(clips)} clips cut into {out_dir/'wavs'}", file=sys.stderr)

    rows = []
    total_s = 0.0
    ffprobe = _ffmpeg().replace("ffmpeg.exe", "ffprobe.exe")
    for i, clip in enumerate(clips, 1):
        d = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", str(clip)], capture_output=True, text=True)
        dur = float(d.stdout.strip() or 0)
        total_s += dur
        text = ""
        if not args.no_asr:
            text = aud._asr_text(str(clip), args.lang) or ""
            print(f"   {clip.name} [{dur:.1f}s]: {text[:70]}", file=sys.stderr)
        rows.append({"file": f"wavs/{clip.name}", "id": clip.stem, "text": text, "dur": round(dur, 2)})

    # XTTS expects '|'-separated: audio_file|text|speaker_name
    (out_dir / "metadata.csv").write_text(
        "\n".join(f"{r['file']}|{r['text']}|{args.speaker}" for r in rows) + "\n",
        encoding="utf-8")
    # LJSpeech style: id|text|text
    (out_dir / "metadata_ljspeech.csv").write_text(
        "\n".join(f"{r['id']}|{r['text']}|{r['text']}" for r in rows) + "\n",
        encoding="utf-8")
    report = {
        "speaker": args.speaker, "lang": args.lang, "clips": len(rows),
        "total_minutes": round(total_s / 60, 1),
        "short_clips": [r["id"] for r in rows if r["dur"] < args.min + 0.5],
        "empty_text": [r["id"] for r in rows if not r["text"].strip()],
        "rows": rows,
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                         encoding="utf-8")

    print(f"\nOK  {len(rows)} clips · {report['total_minutes']} min · -> {out_dir}", file=sys.stderr)
    print("    review report.json (drop clips with wrong ASR), then finetune on Colab/Kaggle.",
          file=sys.stderr)
    if report["total_minutes"] < 20:
        print(f"    NOTE: {report['total_minutes']} min is light for from-scratch; fine for "
              "single-speaker adaptation. More (30-60 min) = better AZ stress.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
