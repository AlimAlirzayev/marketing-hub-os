"""Fire real FLORA work from a Media Studio package — the staged "işə sal" button.

v2 is the professional keyframes-first pipeline. Every stage that spends money
sits behind --confirm; everything else is free and local:

    python -m media_studio.generate <slug>                     # PLAN: all stages + costs
    python -m media_studio.generate <slug> --frames --confirm  # 1) keyframes (~cents)
    python -m media_studio.generate <slug> --pick 1=2,3=1      # 2) choose variants (free)
    python -m media_studio.generate <slug> --animatic          # 3) FREE Ken Burns animatic
    python -m media_studio.generate <slug> --beats --confirm   # 4) beat videos + stitch (paid)
    python -m media_studio.generate <slug> --oner --confirm    # single-shot t2v (v1 mode)
    python -m media_studio.generate <slug> --finish            # 5) FREE branded finishing
    python -m media_studio.generate <slug> --pro --confirm     # 1→3→4→5 hands-free

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
from . import finish as finmod
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
FILM_MODEL = "t2v-kling-v3-standard"  # 588 cr — one multi-shot run, native continuity
USD_PER_CREDIT = 0.0009           # observed: $1.059 for 1176 cr

# Display name only — with FLORA_PROJECT pinning active, all runs land in the
# single pinned project and this fallback label is never used.
PROJECT_NAME = "Media Studio — {name}"


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
        raise SystemExit("Paket tapılmadı. Əvvəlcə: python -m media_studio \"<cümlə>\"")
    return json.loads(path.read_text(encoding="utf-8"))


def build_prompt(brief: dict[str, Any], category: str | None = None) -> str:
    """The single-shot ('oner') prompt in the Seedance 2.0 official 6-step
    formula: subject, action, environment, ONE camera instruction, style
    (lighting-led, rhythm words, no lens jargon), avoid-list. ~60-100 words."""
    from . import knowledge

    beats = brief["storyboard"]
    cat = category or knowledge.category_for(brief["campaign"].get("source_brief", ""))
    sb = knowledge.style_bible_for(cat)
    dur = brief["format"]["duration_s"]

    links = ["First", "Then", "Next", "Finally"]
    action = " ".join(
        f"{links[min(i, 3)]}, {b['visual']}." for i, b in enumerate(beats) if b.get("visual")
    )
    return (
        f"{knowledge.hero_anchor(cat)} in one continuous {dur}-second "
        f"vertical 9:16 commercial scene. {action} "
        f"Camera: one slow, smooth, gradual push-in, ending locked and stable on the final moment. "
        f"Style: {sb['look_video']}; {sb['palette']}. "
        f"Avoid: {knowledge.VIDEO_AVOID}."
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
             "cmd": f"python -m media_studio.generate {pkg['slug']} --frames --confirm"},
            {"stage": "pick", "what": "kadr seçimi (contact-sheet.html)", "credits": 0, "usd": 0,
             "cmd": f"python -m media_studio.generate {pkg['slug']} --pick 1=1,2=2,..."},
            {"stage": "animatic", "what": "PULSUZ Ken Burns animatic (lokal ffmpeg)",
             "credits": 0, "usd": 0,
             "cmd": f"python -m media_studio.generate {pkg['slug']} --animatic"},
            {"stage": "film (tövsiyə)", "what": f"TƏK multi-shot run × {FILM_MODEL} — native davamlılıq, stitch yox",
             "credits": models.CATALOG[FILM_MODEL].credits,
             "usd": round(models.CATALOG[FILM_MODEL].credits * USD_PER_CREDIT, 2),
             "cmd": f"python -m media_studio.generate {pkg['slug']} --film --confirm"},
            {"stage": "beats", "what": f"{n_beats} beat × {BEAT_MODEL} + stitch (beat-level redo üçün)",
             "credits": n_beats * beat_cr,
             "usd": round(n_beats * beat_cr * USD_PER_CREDIT, 2),
             "cmd": f"python -m media_studio.generate {pkg['slug']} --beats --confirm"},
            {"stage": "oner (alternativ)", "what": f"tək fasiləsiz plan ({oner_model}; {oner_reason})",
             "credits": oner_cr, "usd": round(oner_cr * USD_PER_CREDIT, 2),
             "cmd": f"python -m media_studio.generate {pkg['slug']} --oner --confirm"},
            {"stage": "finish", "what": "PULSUZ finishing: AZ overlay + logo + CTA end-card + 1080p (lokal ffmpeg)",
             "credits": 0, "usd": 0,
             "cmd": f"python -m media_studio.generate {pkg['slug']} --finish"},
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


def stage_film(pkg: dict[str, Any], folder: Path, *, confirm: bool, model: str | None) -> int:
    """ONE multi-shot generation (Kling 3.0 dialect): the whole storyboard in a
    single run with native cross-shot continuity. Cheaper than 4 separate beats
    and the hero/world/grade stay consistent without stitching."""
    from . import knowledge
    from .flora_client import FloraMCP

    brief = pkg["brief"]
    category = pkg["request"]["category"]
    model_id = model or FILM_MODEL
    m = models.CATALOG.get(model_id)
    dur = int(brief["format"]["duration_s"])
    prompt = knowledge.compose_film_prompt(category, brief["storyboard"], duration_s=dur)
    print(f"🎞  Film (multi-shot, tək run): {model_id} · ~{m.credits if m else '?'}cr "
          f"(≈${round((m.credits if m else 0) * USD_PER_CREDIT, 2)})")
    print(f"Prompt:\n{prompt}\n")
    if not confirm:
        print("⏸  COST GATE — generasiya üçün əlavə et: --confirm")
        return 0

    flora = FloraMCP()
    try:
        ws = flora.default_workspace_id()
        proj = flora.ensure_project(ws, PROJECT_NAME.format(name=brief["campaign"]["name"])[:60])
        gen = flora.generate_media(
            media_type="video", workspace_id=ws, project_id=proj["project_id"],
            model=model_id, prompt=prompt,
            params={"duration": str(dur), "aspect_ratio": brief["format"]["aspect"]})
        run_id = gen.get("run_id")
        print(f"   run={run_id}  ${gen.get('charged_cost')}  ~{gen.get('estimated_seconds')}s")
        if not run_id:
            return 1
        url = framod._wait_for_output(flora, run_id, want_type="videoUrl", timeout_s=900)
        if not url:
            print("⚠ Video URL gəlmədi.")
            return 1
        dest = folder / "promo-film-master.mp4"
        urllib.request.urlretrieve(url, dest)
        print(f"✅ Hazır: {dest}")
        return 0
    finally:
        flora.close()


def stage_finish(pkg: dict[str, Any], folder: Path, *, master: str | None = None,
                 aspect: str | None = None, no_logo: bool = False) -> int:
    """FREE deterministic finishing: raw AI master -> publish-ready branded promo.

    Burns the director's exact AZ overlay copy, adds the brand logo bug and a
    guaranteed CTA end-card, upscales to the delivery canvas. Local ffmpeg only.
    """
    brief = pkg["brief"]
    src = (folder / master) if master else finmod.pick_master(folder)
    if not src or not src.exists():
        print("⚠ Bitmiş master tapılmadı — əvvəlcə --film / --beats / --oner işə sal.")
        return 1
    out = folder / "promo-final.mp4"
    res = finmod.finish_master(src, brief, out, canvas=aspect, with_logo=not no_logo)
    if not res.get("ok"):
        print(f"⚠ Finishing xətası: {res.get('error')}")
        return 1
    print(f"✨ Final hazır ({res['canvas']}, {res['duration_s']}s, "
          f"{res['overlays']} overlay, logo={'var' if res['logo'] else 'yox'}, {res['cost']}):")
    print(f"   {res['path']}")
    return 0


def stage_oner(pkg: dict[str, Any], folder: Path, *, confirm: bool, model: str | None) -> int:
    brief = pkg["brief"]
    prompt = build_prompt(brief, category=pkg.get("request", {}).get("category"))
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
        prog="media_studio.generate",
        description="Staged FLORA production from a Media Studio package (cost-gated).")
    ap.add_argument("slug", nargs="?", default=None)
    ap.add_argument("--frames", action="store_true", help="Stage 1: generate keyframes (paid, cents).")
    ap.add_argument("--variants", type=int, default=2, help="Keyframe variants per beat (default 2).")
    ap.add_argument("--pick", default=None, help="Select variants: '1=2,3=1' (1-based beat=variant).")
    ap.add_argument("--animatic", action="store_true", help="FREE local Ken Burns animatic.")
    ap.add_argument("--beats", action="store_true", help="Stage 3: per-beat videos + stitch (paid).")
    ap.add_argument("--film", action="store_true",
                    help="ONE multi-shot run (Kling 3.0 dialect) — native continuity, no stitch (paid).")
    ap.add_argument("--oner", action="store_true", help="Single-shot t2v film (paid, v1 mode).")
    ap.add_argument("--finish", action="store_true",
                    help="FREE finishing: AZ overlays + logo + CTA end-card + upscale (local ffmpeg).")
    ap.add_argument("--master", default=None,
                    help="Finish a specific file in the package folder (default: best master).")
    ap.add_argument("--aspect", default=None,
                    help="Finishing canvas override: 9:16 | 4:5 | 1:1 | 16:9.")
    ap.add_argument("--no-logo", action="store_true", help="Finish without the logo bug/lockup.")
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
            if rc == 0:
                rc = stage_finish(pkg, folder)
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
        if args.film and rc == 0:
            ran_stage = True
            rc = stage_film(pkg, folder, confirm=args.confirm, model=args.model)
        if args.oner and rc == 0:
            ran_stage = True
            rc = stage_oner(pkg, folder, confirm=args.confirm, model=args.model)
        if args.finish and rc == 0:
            ran_stage = True
            rc = stage_finish(pkg, folder, master=args.master,
                              aspect=args.aspect, no_logo=args.no_logo)

    if not ran_stage and not args.pick:
        # legacy compatibility: bare --confirm behaves like v1 (oner)
        if args.confirm:
            rc = stage_oner(pkg, folder, confirm=True, model=args.model)
        else:
            print_stage_plan(pkg, plan_stages(pkg, variants=args.variants))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
