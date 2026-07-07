"""Fire real FLORA work from a MediaForge package — the staged "işə sal" button.

v2 is the professional keyframes-first pipeline. Every stage that spends money
sits behind --confirm; everything else is free and local:

    python -m mediaforge.generate <slug>                     # PLAN: all stages + costs
    python -m mediaforge.generate <slug> --frames --confirm  # 1) keyframes (~cents)
    python -m mediaforge.generate <slug> --pick 1=2,3=1      # 2) choose variants (free)
    python -m mediaforge.generate <slug> --animatic          # 3) FREE Ken Burns animatic
    python -m mediaforge.generate <slug> --beats --confirm   # 4) beat videos + stitch (paid)
    python -m mediaforge.generate <slug> --oner --confirm    # single-shot t2v (v1 mode)
    python -m mediaforge.generate <slug> --pro --confirm     # 1→3→4 hands-free

Stage flags combine with --confirm as the explicit spend authorization; the
Claude Code harness additionally requires a human-authored permission rule, so
paid stages are always human-fired by design.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from . import animatic as animod
from . import frames as framod
from . import models
from .pipeline import CAMPAIGNS

# image-to-video model → its text-to-video sibling. FLORA's raw /generate is
# prompt-only (image inputs exist only in Techniques), so beat/oner generation
# runs text-to-video with a hard style-bible lock instead.
_I2V_TO_T2V = {
    "i2v-seedance-2-0-reference-i2v-enhancor": "t2v-seedance-2.0-enhancor",
    "i2v-seedance-1.5-pro": "t2v-seedance-1.5-pro",
    "i2v-kling-2.6": "t2v-kling-2.6",
    "i2v-runway-gen-4.5": "t2v-runway-gen-4.5",
    "i2v-sora2-pro": "t2v-sora2-pro",
    "i2v-veo3": "t2v-kling-v3-pro",
    "i2v-veo-3-1-lite-i2v": "t2v-kling-2.6",
}

BEAT_MODEL = "t2v-kling-2.6"      # 327 cr, 5s/10s — cheap polished beats
BEAT_CLIP_SECONDS = "5"           # shoot long, trim short at stitch
USD_PER_CREDIT = 0.0009           # observed: $1.059 for 1176 cr

PROJECT_NAME = "MediaForge — {name}"


def _fix_console() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def latest_package() -> Path | None:
    if not CAMPAIGNS.exists():
        return None
    pkgs = sorted(CAMPAIGNS.glob("*/package.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pkgs[0] if pkgs else None


def load_package(slug: str | None) -> dict[str, Any]:
    path = (CAMPAIGNS / slug / "package.json") if slug else latest_package()
    if not path or not path.exists():
        raise SystemExit("Paket tapılmadı. Əvvəlcə: python -m mediaforge \"<cümlə>\"")
    return json.loads(path.read_text(encoding="utf-8"))


def build_prompt(brief: dict[str, Any]) -> str:
    """The single-shot ('oner') prompt: whole storyboard as one continuous film."""
    beats = brief["storyboard"]
    scene = " ".join(f"{b['visual']}. {b['motion']}." for b in beats if b.get("visual"))
    tone = ", ".join(brief["brand"]["tone"])
    dur = brief["format"]["duration_s"]
    aspect = brief["format"]["aspect"]
    return (
        f"Cinematic {dur}-second vertical {aspect} promo film, {tone}. {scene} "
        "No on-screen text, no captions, no logos, no watermark. Shot on a cinema "
        "camera, shallow depth of field, natural warm color grade, smooth "
        "stabilized motion, premium and emotionally resonant."
    )


def _has_reference_image(brief: dict[str, Any]) -> bool:
    for a in brief.get("assets", []):
        role = a.get("role", "")
        p = str(a.get("path_or_url", ""))
        if role in {"campaign_key_visual", "product_reference", "motion_reference"} and (
            p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) or p.startswith("http")
        ):
            return True
    return False


def choose_model(brief: dict[str, Any], override: str | None) -> tuple[str, str]:
    if override:
        return override, "override"
    recommended = brief["model_strategy"]["recommended"][0]
    if not _has_reference_image(brief) and recommended in _I2V_TO_T2V:
        return _I2V_TO_T2V[recommended], "no reference image → text-to-video sibling"
    return recommended, "brief recommendation"


def plan(pkg: dict[str, Any], model_id: str, reason: str, prompt: str) -> dict[str, Any]:
    fmt = pkg["brief"]["format"]
    m = models.CATALOG.get(model_id)
    credits = m.credits if m else "?"
    label = m.label if m else model_id
    duration = str(models._nearest_duration(m, fmt["duration_s"], [])) if m else str(fmt["duration_s"])
    return {
        "model_id": model_id,
        "label": label,
        "reason": reason,
        "credits": credits,
        "params": {"aspect_ratio": fmt["aspect"], "duration": duration, "resolution": "1080p"},
        "prompt": prompt,
    }


def plan_stages(pkg: dict[str, Any], *, variants: int = 2) -> dict[str, Any]:
    """The full professional pipeline plan with per-stage costs."""
    brief = pkg["brief"]
    n_beats = len(brief["storyboard"])
    fplan = framod.plan_frames(pkg, variants=variants)
    beat_cr = models.CATALOG[BEAT_MODEL].credits
    oner_model, oner_reason = choose_model(brief, None)
    oner_cr = models.CATALOG.get(oner_model).credits if oner_model in models.CATALOG else 0
    return {
        "slug": pkg["slug"],
        "style_bible": fplan["style_bible"],
        "character": fplan["character"],
        "stages": [
            {"stage": "frames", "what": f"{fplan['total_images']} keyframe ({fplan['model']})",
             "credits": fplan["estimated_credits"],
             "usd": round(fplan["estimated_credits"] * USD_PER_CREDIT, 2),
             "cmd": f"python -m mediaforge.generate {pkg['slug']} --frames --confirm"},
            {"stage": "pick", "what": "kadr seçimi (contact-sheet.html)", "credits": 0, "usd": 0,
             "cmd": f"python -m mediaforge.generate {pkg['slug']} --pick 1=1,2=2,..."},
            {"stage": "animatic", "what": "PULSUZ Ken Burns animatic (lokal ffmpeg)",
             "credits": 0, "usd": 0,
             "cmd": f"python -m mediaforge.generate {pkg['slug']} --animatic"},
            {"stage": "beats", "what": f"{n_beats} beat × {BEAT_MODEL} + stitch",
             "credits": n_beats * beat_cr,
             "usd": round(n_beats * beat_cr * USD_PER_CREDIT, 2),
             "cmd": f"python -m mediaforge.generate {pkg['slug']} --beats --confirm"},
            {"stage": "oner (alternativ)", "what": f"tək fasiləsiz plan ({oner_model}; {oner_reason})",
             "credits": oner_cr, "usd": round(oner_cr * USD_PER_CREDIT, 2),
             "cmd": f"python -m mediaforge.generate {pkg['slug']} --oner --confirm"},
        ],
    }


def print_stage_plan(pkg: dict[str, Any], sp: dict[str, Any]) -> None:
    print("=" * 76)
    print(f"🎬  {pkg['concept'].get('name', '')} — PEŞƏKAR PIPELINE PLANI")
    print("=" * 76)
    print(f"Style bible : {sp['style_bible']}")
    print(f"Qəhrəman    : {sp['character'][:90]}…")
    print()
    for st in sp["stages"]:
        cost = "pulsuz" if not st["credits"] else f"~{st['credits']}cr (≈${st['usd']})"
        print(f"  [{st['stage']:<18}] {st['what']:<52} {cost}")
        print(f"      → {st['cmd']}")
    print()
    print("⏸  COST GATE — heç nə xərclənməyib. Hər ödənişli mərhələ --confirm istəyir.")


# --------------------------------------------------------------------------- #
# Stages
# --------------------------------------------------------------------------- #
def stage_frames(pkg: dict[str, Any], folder: Path, *, variants: int, confirm: bool) -> int:
    fplan = framod.plan_frames(pkg, variants=variants)
    usd = round(fplan["estimated_credits"] * USD_PER_CREDIT, 2)
    print(f"📸 Keyframes: {fplan['total_images']} şəkil × {fplan['model']} "
          f"= ~{fplan['estimated_credits']}cr (≈${usd})")
    if not confirm:
        print("⏸  COST GATE — generasiya üçün əlavə et: --confirm")
        return 0
    out = framod.generate_frames(pkg, folder, variants=variants)
    ok = sum(1 for r in out["runs"] if r.get("ok"))
    print(f"✅ {ok}/{len(out['runs'])} keyframe hazır · real xərc: ${out['charged_cost_usd']}")
    print(f"   Seçim üçün aç: {folder / 'frames' / 'contact-sheet.html'}")
    return 0 if ok else 1


def stage_animatic(pkg: dict[str, Any], folder: Path) -> int:
    brief = pkg["brief"]
    durations = framod.parse_beat_seconds(brief["storyboard"])
    frame_paths = framod.selected_frame_paths(folder, len(brief["storyboard"]))
    res = animod.build_animatic(frame_paths, durations, folder / "animatic.mp4")
    if not res.get("ok"):
        print(f"⚠ Animatic alınmadı: {res.get('error')}")
        return 1
    print(f"🎞  Animatic hazır ({res['duration_s']}s, {res['beats']} beat, {res['cost']}): {res['path']}")
    return 0


def stage_beats(pkg: dict[str, Any], folder: Path, *, confirm: bool, model: str) -> int:
    from . import knowledge
    from .flora_client import FloraMCP

    brief = pkg["brief"]
    category = pkg["request"]["category"]
    beats = brief["storyboard"]
    durations = framod.parse_beat_seconds(beats)
    m = models.CATALOG.get(model)
    credits = (m.credits if m else 0) * len(beats)
    print(f"🎥 Beats: {len(beats)} × {model} = ~{credits}cr (≈${round(credits * USD_PER_CREDIT, 2)})")
    if not confirm:
        print("⏸  COST GATE — generasiya üçün əlavə et: --confirm")
        return 0

    beats_dir = folder / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    flora = FloraMCP()
    total_cost = 0.0
    try:
        ws = flora.default_workspace_id()
        proj = flora.ensure_project(ws, PROJECT_NAME.format(name=brief["campaign"]["name"])[:60])
        project_id = proj["project_id"]

        runs = []
        prev_visual = ""
        for i, beat in enumerate(beats):
            prompt = knowledge.compose_beat_video_prompt(
                category, beat, beat_index=i, total_beats=len(beats), prev_visual=prev_visual)
            gen = flora.generate_media(
                media_type="video", workspace_id=ws, project_id=project_id,
                model=model, prompt=prompt,
                params={"duration": BEAT_CLIP_SECONDS},
            )
            total_cost += float(gen.get("charged_cost") or 0)
            print(f"   beat{i}: run={gen.get('run_id')}  ${gen.get('charged_cost')}")
            runs.append((i, gen.get("run_id")))
            prev_visual = beat["visual"]

        clip_paths: list[Path] = []
        for i, run_id in runs:
            url = framod._wait_for_output(flora, run_id, want_type="videoUrl", timeout_s=900)
            if not url:
                print(f"   ⚠ beat{i} video URL gəlmədi (run {run_id})")
                return 1
            dest = beats_dir / f"beat{i}.mp4"
            urllib.request.urlretrieve(url, dest)
            clip_paths.append(dest)
    finally:
        flora.close()

    print(f"   real xərc: ${round(total_cost, 3)} · stitch başlayır…")
    res = animod.stitch_beats(clip_paths, durations, folder / "promo-beats-master.mp4")
    if not res.get("ok"):
        print(f"⚠ Stitch xətası: {res.get('error')}")
        return 1
    print(f"✅ Master hazır ({res['duration_s']}s, {res['beats']} beat): {res['path']}")
    return 0


def stage_oner(pkg: dict[str, Any], folder: Path, *, confirm: bool, model: str | None) -> int:
    brief = pkg["brief"]
    prompt = build_prompt(brief)
    model_id, reason = choose_model(brief, model)
    pl = plan(pkg, model_id, reason, prompt)
    print(f"🎬 Oner: {pl['label']} ({pl['model_id']}) · ~{pl['credits']}cr · {pl['params']}")
    if not confirm:
        print("⏸  COST GATE — generasiya üçün əlavə et: --confirm")
        return 0

    from .flora_client import FloraMCP
    flora = FloraMCP()
    try:
        ws = flora.default_workspace_id()
        proj = flora.ensure_project(ws, PROJECT_NAME.format(name=brief["campaign"]["name"])[:60])
        gen = flora.generate_video(
            workspace_id=ws, project_id=proj["project_id"], model=model_id,
            prompt=prompt, params=pl["params"])
        run_id = gen.get("run_id")
        print(f"   run={run_id}  ${gen.get('charged_cost')}  ~{gen.get('estimated_seconds')}s")
        if not run_id:
            return 1
        url = framod._wait_for_output(flora, run_id, want_type="videoUrl", timeout_s=900)
        if not url:
            print("⚠ Video URL gəlmədi.")
            return 1
        dest = folder / f"promo-{model_id.replace('/', '_')}.mp4"
        urllib.request.urlretrieve(url, dest)
        print(f"✅ Hazır: {dest}")
        return 0
    finally:
        flora.close()


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    _fix_console()
    ap = argparse.ArgumentParser(
        prog="mediaforge.generate",
        description="Staged FLORA production from a MediaForge package (cost-gated).")
    ap.add_argument("slug", nargs="?", default=None)
    ap.add_argument("--frames", action="store_true", help="Stage 1: generate keyframes (paid, cents).")
    ap.add_argument("--variants", type=int, default=2, help="Keyframe variants per beat (default 2).")
    ap.add_argument("--pick", default=None, help="Select variants: '1=2,3=1' (1-based beat=variant).")
    ap.add_argument("--animatic", action="store_true", help="FREE local Ken Burns animatic.")
    ap.add_argument("--beats", action="store_true", help="Stage 3: per-beat videos + stitch (paid).")
    ap.add_argument("--oner", action="store_true", help="Single-shot t2v film (paid, v1 mode).")
    ap.add_argument("--pro", action="store_true", help="frames → animatic → beats, hands-free.")
    ap.add_argument("--model", default=None, help="Model override (oner) / beat model (beats).")
    ap.add_argument("--confirm", action="store_true", help="Authorize the spend.")
    args = ap.parse_args(argv)

    pkg = load_package(args.slug)
    folder = CAMPAIGNS / pkg["slug"]
    rc = 0

    if args.pick:
        sel = framod.apply_picks(folder, args.pick)
        print(f"✔ Seçim yeniləndi: { {k + 1: v for k, v in sorted(sel.items())} }")

    ran_stage = False
    if args.pro:
        ran_stage = True
        rc = stage_frames(pkg, folder, variants=args.variants, confirm=args.confirm)
        if rc == 0 and args.confirm:
            rc = stage_animatic(pkg, folder) or 0
            rc = stage_beats(pkg, folder, confirm=args.confirm,
                             model=args.model or BEAT_MODEL)
    else:
        if args.frames:
            ran_stage = True
            rc = stage_frames(pkg, folder, variants=args.variants, confirm=args.confirm)
        if args.animatic and rc == 0:
            ran_stage = True
            rc = stage_animatic(pkg, folder)
        if args.beats and rc == 0:
            ran_stage = True
            rc = stage_beats(pkg, folder, confirm=args.confirm,
                             model=args.model or BEAT_MODEL)
        if args.oner and rc == 0:
            ran_stage = True
            rc = stage_oner(pkg, folder, confirm=args.confirm, model=args.model)

    if not ran_stage and not args.pick:
        # legacy compatibility: bare --confirm behaves like v1 (oner)
        if args.confirm:
            rc = stage_oner(pkg, folder, confirm=True, model=args.model)
        else:
            print_stage_plan(pkg, plan_stages(pkg, variants=args.variants))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
