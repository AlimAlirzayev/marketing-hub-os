"""Fire a real FLORA video generation from a MediaForge package.

This is the "işə sal" button made real. It is a SEPARATE, explicit step from
building the package, because it spends FLORA credits. It mirrors MediaForge's
cost gate: without --confirm it only prints the plan + cost and stops; with
--confirm it actually generates, polls the run, and downloads the video.

    python -m mediaforge.generate                 # latest package, plan only
    python -m mediaforge.generate <slug>          # a specific package, plan only
    python -m mediaforge.generate <slug> --confirm  # actually spend + generate
    python -m mediaforge.generate <slug> --model t2v-seedance-1.5-pro --confirm

The paid generation is intentionally gated: the Claude Code harness also blocks
an agent from firing it, so a human runs this command to authorize the spend.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from . import models
from .pipeline import CAMPAIGNS

# image-to-video model → its text-to-video sibling (used when the brief has no
# usable reference image, so a text-only prompt still generates).
_I2V_TO_T2V = {
    "i2v-seedance-2-0-reference-i2v-enhancor": "t2v-seedance-2.0-enhancor",
    "i2v-seedance-1.5-pro": "t2v-seedance-1.5-pro",
    "i2v-kling-2.6": "t2v-kling-2.6",
    "i2v-runway-gen-4.5": "t2v-runway-gen-4.5",
    "i2v-sora2-pro": "t2v-sora2-pro",
    "i2v-veo3": "t2v-kling-v3-pro",
    "i2v-veo-3-1-lite-i2v": "t2v-kling-2.6",
}

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


def print_plan(pkg: dict[str, Any], pl: dict[str, Any]) -> None:
    print("=" * 72)
    print(f"🎬  {pkg['concept'].get('name','')}")
    print("=" * 72)
    print(f"Paket    : {pkg['slug']}")
    print(f"Model    : {pl['label']}  ({pl['model_id']})")
    print(f"Səbəb    : {pl['reason']}")
    print(f"Xərc     : ~{pl['credits']} kredit  (FLORA workspace kreditindən — illik abunə)")
    print(f"Params   : {pl['params']}")
    print(f"\nPrompt:\n{pl['prompt']}\n")


def run(slug: str | None, *, model: str | None, confirm: bool) -> int:
    pkg = load_package(slug)
    brief = pkg["brief"]
    prompt = build_prompt(brief)
    model_id, reason = choose_model(brief, model)
    pl = plan(pkg, model_id, reason, prompt)
    print_plan(pkg, pl)

    if not confirm:
        print("⏸  COST GATE — kredit xərclənməyib. Generasiya üçün əlavə et:  --confirm")
        return 0

    from .flora_client import FloraMCP  # lazy: only needed for the real fire

    print("🔌 FLORA MCP-yə qoşulur (OAuth token cache-dən)…")
    flora = FloraMCP()
    try:
        ws = flora.default_workspace_id()
        proj = flora.ensure_project(ws, PROJECT_NAME.format(name=brief["campaign"]["name"])[:60])
        project_id = proj["project_id"]
        print(f"   workspace={ws}  project={project_id} ({'yeni' if proj.get('created') else 'mövcud'})")

        print("🎥 Generasiya işə salınır (kredit xərclənir)…")
        gen = flora.generate_video(
            workspace_id=ws, project_id=project_id, model=model_id,
            prompt=prompt, params=pl["params"],
        )
        run_id = gen.get("run_id")
        print(f"   run_id={run_id}  charged_cost=${gen.get('charged_cost')}  ~{gen.get('estimated_seconds')}s")
        if not run_id:
            print("   run_id gəlmədi:", gen)
            return 1

        out = _poll_and_download(flora, run_id, pkg, model_id)
        print(f"\n✅ Hazır: {out}" if out else "\n⚠ Generasiya bitdi, amma video URL tapılmadı — run cavabını yoxla.")
        return 0
    finally:
        flora.close()


def _poll_and_download(flora, run_id: str, pkg: dict[str, Any], model_id: str) -> str | None:
    deadline = time.time() + 900
    url = None
    while time.time() < deadline:
        run_obj = flora.get_run(run_id)
        status = (run_obj.get("status") or "").lower()
        progress = run_obj.get("progress")
        url = _find_video_url(run_obj)
        print(f"   … status={status or '?'} progress={progress}   ", end="\r")
        if url or status in {"completed", "succeeded", "done", "failed", "error"}:
            if status in {"failed", "error"}:
                print("\n   FLORA xətası:", run_obj.get("error_message") or run_obj.get("error_code"))
            break
        time.sleep(8)
    if not url:
        return None
    folder = CAMPAIGNS / pkg["slug"]
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"promo-{model_id.replace('/', '_')}.mp4"
    urllib.request.urlretrieve(url, dest)
    return str(dest)


def _find_video_url(obj: Any) -> str | None:
    """Find the videoUrl in a generations.retrieve response.

    outputs is `{output_id, type: 'videoUrl', url}` (or a list of those).
    Falls back to any http .mp4 URL anywhere in the structure.
    """
    def _from_output(o: Any) -> str | None:
        if isinstance(o, dict) and o.get("type") == "videoUrl" and o.get("url"):
            return o["url"]
        return None

    if isinstance(obj, dict):
        out = obj.get("outputs")
        if isinstance(out, dict):
            u = _from_output(out)
            if u:
                return u
        elif isinstance(out, list):
            for o in out:
                u = _from_output(o)
                if u:
                    return u
    # generic fallback: any mp4 URL in the tree
    if isinstance(obj, str):
        return obj if obj.startswith("http") and ".mp4" in obj else None
    if isinstance(obj, dict):
        for v in obj.values():
            u = _find_video_url(v)
            if u:
                return u
    if isinstance(obj, list):
        for v in obj:
            u = _find_video_url(v)
            if u:
                return u
    return None


def main(argv: list[str] | None = None) -> int:
    _fix_console()
    ap = argparse.ArgumentParser(prog="mediaforge.generate",
                                 description="Fire a real FLORA generation from a MediaForge package.")
    ap.add_argument("slug", nargs="?", default=None, help="Package slug (default: latest).")
    ap.add_argument("--model", default=None, help="Override the FLORA model id.")
    ap.add_argument("--confirm", action="store_true", help="Actually spend credits and generate.")
    args = ap.parse_args(argv)
    return run(args.slug, model=args.model, confirm=args.confirm)


if __name__ == "__main__":
    raise SystemExit(main())
