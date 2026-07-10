"""The finishing / delivery layer — raw AI master -> publish-ready branded promo.

A real media agency never ships the raw model output. Generation gives a
textless *motion plate*; finishing is where it becomes a campaign asset: the
exact Azerbaijani copy is burned in as crisp deterministic overlays (never
AI-rendered — that was the whole point of the text policy), the brand logo bug
and a guaranteed CTA end-card are added, the plate is upscaled to a clean
delivery resolution, and platform-specific crops are exported.

Everything here is FREE and deterministic — pure local ffmpeg, no credits, no
network, no AI. It consumes exactly the fields the director already produced:
    storyboard[].overlay   -> timed on-screen lines (director-curated)
    offer.cta / headline    -> guaranteed CTA end-card
    brand.palette[0]        -> brand accent (#E31E24)
    format.aspect           -> delivery canvas
so the copy on screen is always the human-approved copy, letter-for-letter.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from . import animatic

ROOT = Path(__file__).resolve().parent.parent
FPS = 30

# Delivery canvases per aspect (w, h). 9:16 is the paid-social default.
CANVAS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

BRAND_RED = "0xE31E24"           # Xalq Sigorta accent (brand.palette[0])
BRAND_INK = "0x141417"

# Fonts: the brand wants Inter Tight / Manrope, which aren't installed on the
# corporate box; Segoe UI (Semibold/Bold) is the cleanest premium substitute
# that ships with Windows. Ordered by preference; first existing wins.
_FONT_CANDIDATES = {
    "headline": [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
    "body": [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"],
    "black": [r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\segoeuib.ttf"],
}

LOGO_WHITE = ROOT / "social-studio" / "brand_kit" / "logo-white.png"

_TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def find_ffmpeg() -> str | None:
    return animatic.find_ffmpeg()


def find_font(kind: str = "headline") -> str | None:
    for cand in _FONT_CANDIDATES.get(kind, _FONT_CANDIDATES["headline"]):
        if Path(cand).exists():
            return cand
    return None


def _ff_path(p: str | Path) -> str:
    """A filesystem path safe to embed inside an ffmpeg filter value.

    ffmpeg parses ':' as an option separator, so a Windows drive colon must be
    escaped and backslashes normalised to forward slashes.
    """
    s = str(p).replace("\\", "/")
    return s.replace(":", r"\:")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def parse_time_window(beat_time: str, fallback: tuple[float, float]) -> tuple[float, float]:
    m = _TIME_RE.search(str(beat_time or ""))
    if m:
        return float(m.group(1)), float(m.group(2))
    return fallback


def target_canvas(brief: dict[str, Any], override: str | None = None) -> tuple[int, int]:
    aspect = override or brief.get("format", {}).get("aspect", "9:16")
    return CANVAS.get(aspect, CANVAS["9:16"])


# --------------------------------------------------------------------------- #
# Overlay planning — director copy -> timed on-screen events
# --------------------------------------------------------------------------- #
def plan_overlays(brief: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    """Turn the director's curated copy into timed overlay events.

    We respect the brief: a beat only shows text if the director wrote an
    `overlay` for it (pros don't plaster text on every second). The final beat's
    line is promoted to the CTA lockup, and we ALWAYS guarantee a strong close
    even when the brief's last line is weak.
    """
    beats = brief.get("storyboard", [])
    n = len(beats)
    events: list[dict[str, Any]] = []
    cta_seen = False

    for i, beat in enumerate(beats):
        text = (beat.get("overlay") or "").strip()
        if not text:
            continue
        default = (duration * i / max(1, n), duration * (i + 1) / max(1, n))
        start, end = parse_time_window(beat.get("time", ""), default)
        end = min(end, duration)
        is_last = i == n - 1
        events.append({
            "text": text,
            "start": max(0.0, start),
            "end": max(start + 0.6, end),
            "role": "cta" if is_last else "line",
        })
        if is_last:
            cta_seen = True

    # Guaranteed CTA end-card: brand-red pill + logo, held on the last ~1.8s.
    offer = brief.get("offer", {})
    cta_text = (offer.get("cta") or "Ətraflı bax").strip()
    card_start = max(0.0, duration - 1.8)
    if cta_seen and events and events[-1]["role"] == "cta":
        # Reuse the director's closing line as the pill, but ensure it holds to the end.
        events[-1]["end"] = duration
        events[-1]["start"] = min(events[-1]["start"], card_start)
    else:
        events.append({
            "text": cta_text, "start": card_start, "end": duration, "role": "cta",
        })
    return events


# --------------------------------------------------------------------------- #
# Filtergraph construction
# --------------------------------------------------------------------------- #
def _alpha_expr(start: float, end: float, fade: float = 0.35) -> str:
    """A trapezoid alpha: fade in over `fade`s, hold, fade out over `fade`s."""
    s, e = f"{start:.3f}", f"{end:.3f}"
    fin = f"{start + fade:.3f}"
    fout = f"{end - fade:.3f}"
    return (
        f"'if(lt(t,{s}),0,"
        f"if(lt(t,{fin}),(t-{s})/{fade:.3f},"
        f"if(lt(t,{fout}),1,"
        f"if(lt(t,{e}),({e}-t)/{fade:.3f},0))))'"
    )


def _drawtext(event: dict[str, Any], work: Path, idx: int, W: int, H: int,
              fonts: dict[str, str | None]) -> str:
    """Build ONE drawtext filter, writing the (AZ) text to a sidecar file so no
    character ever has to survive filter/shell escaping."""
    role = event["role"]
    if role == "cta":
        line_w, size, font_kind = 26, int(W * 0.052), "headline"
        y = f"h*0.80"
        box = f":box=1:boxcolor={BRAND_RED}@0.92:boxborderw={int(W*0.030)}"
        fontcolor = "white"
    else:
        line_w, size, font_kind = 24, int(W * 0.046), "headline"
        y = f"h*0.70"
        box = ":shadowcolor=black@0.55:shadowx=2:shadowy=3"
        fontcolor = "white"

    text = "\n".join(_wrap(event["text"], line_w))
    tf = work / f"ov_{idx}.txt"
    # newline="\n": Windows text mode would write \r\n and drawtext renders the
    # \r as an extra blank line (double spacing).
    tf.write_text(text, encoding="utf-8", newline="\n")

    font = fonts.get(font_kind) or fonts.get("headline")
    fontfile = f":fontfile='{_ff_path(font)}'" if font else ""
    alpha = _alpha_expr(event["start"], event["end"])
    return (
        f"drawtext=textfile='{_ff_path(tf)}'{fontfile}"
        f":fontcolor={fontcolor}:fontsize={size}:line_spacing={int(size*0.28)}"
        f":x=(w-text_w)/2:y={y}"
        f"{box}:enable='between(t,{event['start']:.3f},{event['end']:.3f})'"
        f":alpha={alpha}"
    )


def build_filtergraph(brief: dict[str, Any], events: list[dict[str, Any]],
                      work: Path, W: int, H: int, *, with_logo: bool,
                      duration: float) -> tuple[str, list[str]]:
    """Assemble the full -filter_complex string and any extra input args.

    Returns (filter_complex, extra_inputs). Input 0 is always the master video;
    input 1 (if with_logo) is the brand logo PNG.
    """
    fonts = {k: find_font(k) for k in _FONT_CANDIDATES}

    # 1) normalise + upscale the plate to the delivery canvas (lanczos).
    base = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={W}:{H},fps={FPS},format=yuv420p"
    )
    # 2) burn the director's copy.
    draws = [_drawtext(ev, work, i, W, H, fonts) for i, ev in enumerate(events)]
    chain = ",".join([base, *draws]) if draws else base
    chain += "[plate]"

    extra_inputs: list[str] = []
    if with_logo and LOGO_WHITE.exists():
        extra_inputs += ["-i", str(LOGO_WHITE)]
        bug_w = int(W * 0.20)
        card_w = int(W * 0.42)
        card_start = max(0.0, duration - 1.8)
        graph = (
            f"{chain};"
            f"[1:v]split=2[lg1][lg2];"
            f"[lg1]scale={bug_w}:-1:flags=lanczos,format=rgba,colorchannelmixer=aa=0.55[bug];"
            f"[lg2]scale={card_w}:-1:flags=lanczos[card];"
            # bug hides when the end-card takes over (no double logo on screen)
            f"[plate][bug]overlay=x={int(W*0.045)}:y={int(H*0.035)}"
            f":enable='lt(t,{card_start:.3f})'[withbug];"
            # overlay vars: W/H = main canvas, w/h = the overlaid logo itself
            f"[withbug][card]overlay=x=(W-w)/2:y={int(H*0.62)}"
            f":enable='between(t,{card_start:.3f},{duration:.3f})'[vout]"
        )
    else:
        graph = f"{chain};[plate]null[vout]"
    return graph, extra_inputs


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def probe_duration(ffmpeg: str, master: Path) -> float:
    """Best-effort duration via ffprobe next to ffmpeg (fallback 10.0)."""
    ffprobe = str(Path(ffmpeg).with_name("ffprobe.exe"))
    if not Path(ffprobe).exists():
        ffprobe = "ffprobe"
    try:
        res = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration:stream=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(master)],
            capture_output=True, text=True)
        for tok in res.stdout.split():
            try:
                v = float(tok)
                if v > 0:
                    return v
            except ValueError:
                continue
    except Exception:  # noqa: BLE001
        pass
    return 10.0


def finish_master(master: Path, brief: dict[str, Any], out_path: Path, *,
                  canvas: str | None = None, with_logo: bool = True,
                  music: Path | None = None) -> dict[str, Any]:
    """Render the finished, branded, publish-ready promo. Never raises."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg tapılmadı (video-studio/tools və PATH yoxlandı)"}
    if not master.exists():
        return {"ok": False, "error": f"master tapılmadı: {master}"}

    W, H = target_canvas(brief, canvas)
    duration = probe_duration(ffmpeg, master)
    events = plan_overlays(brief, duration)

    work = out_path.parent / "_finish_work"
    work.mkdir(parents=True, exist_ok=True)
    graph, extra_inputs = build_filtergraph(
        brief, events, work, W, H, with_logo=with_logo, duration=duration)

    cmd = [ffmpeg, "-y", "-v", "error", "-i", str(master), *extra_inputs]
    audio_args: list[str]
    if music and music.exists():
        cmd += ["-i", str(music)]
        # Duck the bed under any diegetic audio; keep it subtle.
        graph += f";[{2 + (1 if extra_inputs else 0)}:a]volume=0.28,afade=t=out:st={max(0.0,duration-1.2):.3f}:d=1.2[bed]"
        audio_args = ["-map", "[bed]", "-shortest", "-c:a", "aac", "-b:a", "160k"]
    else:
        audio_args = ["-an"]

    cmd += ["-filter_complex", graph, "-map", "[vout]", *audio_args,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-t", f"{duration:.3f}", str(out_path)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return {"ok": False, "error": f"ffmpeg xətası: {res.stderr[-500:]}",
                "cmd": " ".join(cmd)}
    return {
        "ok": True,
        "path": str(out_path),
        "canvas": f"{W}x{H}",
        "duration_s": round(duration, 2),
        "overlays": len(events),
        "logo": with_logo and LOGO_WHITE.exists(),
        "music": bool(music and music.exists()),
        "cost": "0 kredit (lokal ffmpeg)",
    }


def export_variant(master: Path, brief: dict[str, Any], out_path: Path,
                   aspect: str, *, with_logo: bool = True) -> dict[str, Any]:
    """A platform crop of the finished promo (e.g. 1:1 feed, 4:5). Center-safe."""
    return finish_master(master, brief, out_path, canvas=aspect, with_logo=with_logo)


def pick_master(folder: Path) -> Path | None:
    """The best available generated master to finish, newest/most-directed first."""
    for name in ("promo-film-master.mp4", "promo-beats-master.mp4"):
        p = folder / name
        if p.exists():
            return p
    cands = sorted(folder.glob("promo-*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None
