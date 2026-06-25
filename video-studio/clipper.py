"""Xalq Insurance Digital OS Video Studio - viral clipper.

The free, local answer to a paid "personal clipper": it mines a long video for
its most viral moments and cuts them into platform-ready vertical shorts.
The LLM finds and scores the moments; FFmpeg cuts them. Same split as the rest
of Video Studio - the brain plans, the muscle executes deterministically.

    source (local .mp4  OR  YouTube URL)
        │
        ├─ transcript with timestamps        YouTube caption API (instant) or
        │                                     Whisper on the audio (local file)
        ▼
    LLM scores candidate windows             free cascade: Groq → Gemini
        │  → top-N moments, 0-100 viral score, one-line reason
        ▼
    FFmpeg cuts each to 9:16                  ffmpeg_ops.cut_clip
        ▼
    output/clips/<slug>/  +  clips.json

The default path costs nothing and burns no Higgsfield/Blotato credits. If the
media can't be fetched (e.g. a URL with no yt-dlp), the ranked *plan* is still
returned so nothing is silently dropped - you can cut from a local file later.

CLI:
    python video-studio/clipper.py <source> [--n 5] [--aspect 9:16] [--lang en]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import ffmpeg_ops as f
from paths import STUDIO_DIR, subprocess_env

# Free LLM cascade for scoring (mirrors capabilities.md → llm).
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"   # 128k context, free, no native dep
GEMINI_MODEL_DEFAULT = "gemini-2.5-flash"  # 2.0-flash has 0 free quota on this key

ASPECTS = f.ASPECT_RESOLUTION
TRANSCRIPT_CHAR_BUDGET = 48_000          # keep the scoring prompt sane


def _load_env() -> None:
    """Load the repo-root .env into os.environ without overriding real vars.

    Lets `python clipper.py ...` pick up GROQ_API_KEY / GEMINI_API_KEY straight
    from .env, the same keys the rest of Xalq Insurance Digital OS uses.
    """
    env = STUDIO_DIR.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


class ClipperError(RuntimeError):
    """A recoverable clipper failure with a human-actionable message."""


# --------------------------------------------------------------------------- #
# Source handling
# --------------------------------------------------------------------------- #

_YT_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{11})")


def _youtube_id(source: str) -> str | None:
    m = _YT_RE.search(source)
    return m.group(1) if m else None


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "clip-job"


def fetch_transcript(source: str, *, lang: str = "en") -> list[dict]:
    """Return timestamped segments [{"text","start","end"}] for the source.

    YouTube URL → caption API (instant, free, no download). Local file →
    Whisper on the extracted audio (reuses transcribe.py + the free Groq path).
    """
    vid = _youtube_id(source)
    if vid:
        return _transcript_youtube(vid, lang)
    path = Path(source)
    if not path.is_file():
        raise ClipperError(f"source is neither a YouTube URL nor an existing file: {source}")
    return _transcript_whisper(path, lang)


def _transcript_youtube(video_id: str, lang: str) -> list[dict]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise ClipperError(
            "youtube-transcript-api not installed. "
            "pip install -r video-studio/requirements.txt"
        ) from exc

    api = YouTubeTranscriptApi()
    listing = api.list(video_id)
    chosen = None
    for code in (lang, "en", "tr", "az"):
        try:
            chosen = listing.find_transcript([code])
            break
        except Exception:
            continue
    if chosen is None:
        for tr in listing:                       # any available track
            chosen = tr
            break
    if chosen is None:
        raise ClipperError(f"no transcript available for video {video_id}")

    segments: list[dict] = []
    for entry in chosen.fetch():
        text = getattr(entry, "text", None) or (entry.get("text") if isinstance(entry, dict) else "")
        start = float(getattr(entry, "start", None) if not isinstance(entry, dict) else entry["start"])
        dur = float(getattr(entry, "duration", 0.0) if not isinstance(entry, dict) else entry.get("duration", 0.0))
        text = str(text).strip()
        if text:
            segments.append({"text": text, "start": round(start, 2), "end": round(start + dur, 2)})
    return segments


def _transcript_whisper(video: Path, lang: str) -> list[dict]:
    import transcribe

    work = STUDIO_DIR / "jobs" / "_clipper_tmp"
    work.mkdir(parents=True, exist_ok=True)
    wav = work / "audio.wav"
    f.extract_audio(video, wav)
    result = transcribe.transcribe(wav, work / "words.json", language=lang)
    return _words_to_segments(result["words"])


def _words_to_segments(words: list[dict], *, window: float = 12.0) -> list[dict]:
    """Group word-level Whisper output into ~window-second caption lines."""
    segments: list[dict] = []
    buf: list[str] = []
    seg_start = None
    for w in words:
        if seg_start is None:
            seg_start = w["start"]
        buf.append(w["text"])
        if w["end"] - seg_start >= window:
            segments.append({"text": " ".join(buf), "start": round(seg_start, 2), "end": round(w["end"], 2)})
            buf, seg_start = [], None
    if buf and seg_start is not None:
        segments.append({"text": " ".join(buf), "start": round(seg_start, 2), "end": round(words[-1]["end"], 2)})
    return segments


def ensure_media(source: str, *, work_dir: Path) -> Path | None:
    """Return a local video file for cutting, or None if it can't be fetched.

    Local path → itself. YouTube URL → yt-dlp download (if available). Missing
    yt-dlp is NOT fatal: returns None so the caller still emits the ranked plan.
    """
    if _youtube_id(source) is None:
        return Path(source)

    import shutil

    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        try:
            import yt_dlp  # noqa: F401  (module present even if no CLI shim)
            ytdlp = sys.executable
            base_cmd = [ytdlp, "-m", "yt_dlp"]
        except ImportError:
            return None
    else:
        base_cmd = [ytdlp]

    work_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(work_dir / "source.%(ext)s")
    cmd = base_cmd + [
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", out_tmpl, source,
    ]
    proc = subprocess.run(cmd, env=subprocess_env(), capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        raise ClipperError(f"yt-dlp failed:\n{proc.stderr.strip()[-1500:]}")
    downloaded = next((p for p in work_dir.glob("source.*") if p.suffix.lower() in {".mp4", ".mkv", ".webm"}), None)
    if downloaded is None:
        raise ClipperError("yt-dlp reported success but produced no file")
    return downloaded


# --------------------------------------------------------------------------- #
# Scoring (the LLM "brain")
# --------------------------------------------------------------------------- #

def _compact_transcript(segments: list[dict]) -> str:
    """One `[mm:ss] text` line per segment, capped to the char budget."""
    lines: list[str] = []
    total = 0
    for s in segments:
        ts = f"[{int(s['start'] // 60):02d}:{int(s['start'] % 60):02d}]"
        line = f"{ts} {s['text']}"
        total += len(line) + 1
        if total > TRANSCRIPT_CHAR_BUDGET:
            lines.append("...[transcript truncated for length]...")
            break
        lines.append(line)
    return "\n".join(lines)


def _score_prompt(transcript: str, *, num_clips: int, min_len: int, max_len: int) -> str:
    return (
        "You are a short-form video producer. Below is a timestamped transcript "
        "of a long video. Find the moments most likely to go viral as vertical "
        "shorts (TikTok / Reels / Shorts).\n\n"
        "Return ONLY JSON of the shape: {\"clips\": [ {\"start\": <sec float>, "
        "\"end\": <sec float>, \"title\": \"<=60 char hook\", \"score\": <0-100 "
        "int viral potential>, \"reason\": \"<one sentence>\"} ]}.\n\n"
        f"Rules:\n"
        f"- Return at most {num_clips} clips, ranked by score descending.\n"
        f"- Each clip must be {min_len}-{max_len} seconds long.\n"
        "- start/end must come from the transcript timestamps; do not overlap clips.\n"
        "- Prefer self-contained moments: a hook, a payoff, a bold claim, emotion, "
        "or a surprising line. Be honest with low scores when nothing pops.\n\n"
        "TRANSCRIPT:\n" + transcript
    )


def _llm_json(prompt: str) -> dict:
    """Run the scoring prompt through the free LLM cascade; return parsed JSON.

    Primary path is the unified router (llm_router.py: free-first 20/80 cascade
    with automatic fallback). If it (or litellm) is unavailable, fall back to the
    self-contained Groq/Gemini calls so the clipper never hard-stops.
    """
    try:
        sys.path.insert(0, str(STUDIO_DIR.parent))
        from llm_router import complete_json
        data, _ = complete_json(prompt, tier="cheap")
        return data
    except Exception:
        pass
    if os.getenv("GROQ_API_KEY"):
        return _llm_json_groq(prompt)
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return _llm_json_gemini(prompt)
    raise ClipperError(
        "No free LLM configured for scoring. Set GROQ_API_KEY (free, "
        "https://console.groq.com/keys) or GOOGLE_API_KEY (free Gemini)."
    )


def _llm_json_groq(prompt: str) -> dict:
    import requests

    resp = requests.post(
        GROQ_CHAT_URL,
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.4,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def _llm_json_gemini(prompt: str) -> dict:
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
    model = os.getenv("MODEL_FREE_BULK") or GEMINI_MODEL_DEFAULT
    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4),
    )
    return json.loads(resp.text)


def score_segments(
    segments: list[dict],
    *,
    num_clips: int,
    min_len: int,
    max_len: int,
    duration: float | None = None,
) -> list[dict]:
    """Ask the LLM for the top viral windows; validate and clamp them."""
    if not segments:
        raise ClipperError("empty transcript - nothing to score")

    data = _llm_json(_score_prompt(_compact_transcript(segments), num_clips=num_clips,
                                   min_len=min_len, max_len=max_len))
    raw = data.get("clips", data if isinstance(data, list) else [])
    bound = duration if duration else segments[-1]["end"]

    clips: list[dict] = []
    for c in raw:
        try:
            start = max(0.0, float(c["start"]))
            end = float(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        end = min(end, bound)
        if end - start < min_len:
            end = min(start + min_len, bound)
        if end - start > max_len:
            end = start + max_len
        if end - start < 1.0:
            continue
        clips.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "title": str(c.get("title", "")).strip()[:80] or "Untitled clip",
            "score": int(max(0, min(100, c.get("score", 0)))),
            "reason": str(c.get("reason", "")).strip(),
        })
    clips.sort(key=lambda x: x["score"], reverse=True)
    return clips[:num_clips]


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def find_clips(
    source: str,
    *,
    num_clips: int = 5,
    aspect: str = "9:16",
    lang: str = "en",
    min_len: int = 15,
    max_len: int = 60,
    cut: bool = True,
    fit: str = "cover",
    out_dir: Path | None = None,
) -> dict:
    """Full pipeline: transcript → score → cut. Returns a manifest dict.

    ``fit``: "cover" crops to fill the frame (best for a talking head);
    "contain" scales the whole frame onto a blurred backdrop (best for
    screen-share / slides, where cropping would lose content).
    """
    _load_env()
    if aspect not in ASPECTS:
        raise ClipperError(f"unknown aspect {aspect!r}; choose from {list(ASPECTS)}")
    if fit not in ("cover", "contain"):
        raise ClipperError(f"unknown fit {fit!r}; choose 'cover' or 'contain'")

    slug = _slugify(_youtube_id(source) or Path(source).stem)
    out_dir = out_dir or (STUDIO_DIR / "output" / "clips" / slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = STUDIO_DIR / "jobs" / "_clipper_tmp" / slug

    segments = fetch_transcript(source, lang=lang)
    media = ensure_media(source, work_dir=work) if cut else None
    duration = None
    has_audio = True
    if media and media.is_file():
        pr = f.probe(media)
        duration, has_audio = pr.duration, pr.has_audio

    clips = score_segments(segments, num_clips=num_clips, min_len=min_len,
                           max_len=max_len, duration=duration)

    width, height = ASPECTS[aspect]
    cut_count = 0
    for i, clip in enumerate(clips, 1):
        clip["file"] = None
        if media and media.is_file():
            dst = out_dir / f"clip{i}_score{clip['score']}.mp4"
            f.cut_clip(media, dst, start=clip["start"], end=clip["end"],
                       width=width, height=height, fit=fit, has_audio=has_audio)
            clip["file"] = str(dst)
            cut_count += 1

    manifest = {
        "source": source,
        "slug": slug,
        "aspect": aspect,
        "media_cut": media is not None and media.is_file(),
        "clips_cut": cut_count,
        "clips": clips,
    }
    (out_dir / "clips.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def _main(argv: list[str]) -> int:
    # Windows consoles default to cp1252; transcripts are often non-Latin
    # (the reference video is Turkish). Force UTF-8 so reporting never crashes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    if not argv:
        print("usage: python clipper.py <source> [--n 5] [--aspect 9:16] "
              "[--lang en] [--fit cover|contain] [--no-cut]")
        return 2
    source = argv[0]
    opts = argv[1:]

    def _opt(name: str, default: str) -> str:
        return opts[opts.index(name) + 1] if name in opts else default

    try:
        manifest = find_clips(
            source,
            num_clips=int(_opt("--n", "5")),
            aspect=_opt("--aspect", "9:16"),
            lang=_opt("--lang", "en"),
            fit=_opt("--fit", "cover"),
            cut="--no-cut" not in opts,
        )
    except ClipperError as exc:
        print(f"clipper: {exc}")
        return 1

    print(f"\n{len(manifest['clips'])} clips ranked"
          f" ({'cut ' + str(manifest['clips_cut']) if manifest['media_cut'] else 'plan only - media not fetched'}):\n")
    for i, c in enumerate(manifest["clips"], 1):
        print(f"  {i}. [{c['score']:>3}] {c['start']:.0f}-{c['end']:.0f}s  {c['title']}")
        print(f"      {c['reason']}")
        if c["file"]:
            print(f"      → {c['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
