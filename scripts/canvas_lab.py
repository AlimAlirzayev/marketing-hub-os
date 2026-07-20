# -*- coding: utf-8 -*-
"""Canvas Hub QA Lab — autonomous end-to-end test of the standalone SMM hub.

Drives the Downloads canvas app (v14+) in headless Edge via Playwright, using the
real GEMINI_API_KEY from .env instead of the canvas managed proxy. The app itself
is untouched for canvas users: the ``?key=`` / ``?lab=1`` boot params only exist
outside canvas, and ``window.LAB`` exposes the same functions the UI buttons call.

What one run does:
  1. open the hub with key+lab params
  2. (optional) set topic/context
  3. LAB.generate()  — full copy chain: radar -> 2 concepts -> editor -> winner
  4. LAB.render()    — full visual chain: board -> art director -> render -> jury -> layers
  5. save winner JSON, kitchen log, jury badge, every gallery image (PNG) and a
     full-page screenshot into output/canvas-lab/run_<ts>/

Usage:
  python scripts/canvas_lab.py                     # default topic, full run
  python scripts/canvas_lab.py --topic kasko       # value of socialTopicSelect
  python scripts/canvas_lab.py --skip-visual       # copy chain only (cheaper)
  python scripts/canvas_lab.py --file <path.html>  # different build
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP = Path(r"C:\Users\a.alirzayev\Downloads\ai_seo_copywriter_smm_hub_v12_canvas_ultra.html")


def env_get(name: str) -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(rf"\s*{name}\s*=\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return ""


def save_data_uri(uri: str, dest: Path) -> Path | None:
    m = re.match(r"data:image/(\w+);base64,(.+)", uri, re.S)
    if not m:
        return None
    ext = {"jpeg": "jpg"}.get(m.group(1), m.group(1))
    p = dest.with_suffix("." + ext)
    p.write_bytes(base64.b64decode(m.group(2)))
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT_APP))
    ap.add_argument("--topic", default="", help="socialTopicSelect value (default: app default)")
    ap.add_argument("--context", default="", help="campaign context text")
    ap.add_argument("--skip-visual", action="store_true")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    args = ap.parse_args()

    key = env_get("GEMINI_API_KEY")
    if not key:
        print("FATAL: GEMINI_API_KEY .env-de tapilmadi")
        return 1
    app = Path(args.file)
    if not app.exists():
        print(f"FATAL: app tapilmadi: {app}")
        return 1

    run_dir = ROOT / "output" / "canvas-lab" / time.strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    console_log = (run_dir / "console.log").open("w", encoding="utf-8")
    report: dict = {"app": str(app), "started": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": []}

    from playwright.sync_api import sync_playwright

    url = app.as_uri() + f"?key={key}&lab=1"
    # Persistent profile: localStorage-based anti-template memory survives across
    # runs, matching how a real user's browser behaves (fresh profile would let
    # the app "forget" used palettes/scenes and mask repetition bugs).
    profile_dir = ROOT / "data" / "canvas-lab-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            str(profile_dir), channel="msedge", headless=not args.headed,
            viewport={"width": 1440, "height": 2100})
        page = browser.new_page()
        page.on("console", lambda msg: console_log.write(f"[{msg.type}] {msg.text}\n"))
        page.on("pageerror", lambda err: console_log.write(f"[pageerror] {err}\n"))

        print("1) app acilir...")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function("() => !!window.LAB", timeout=30000)
        report["lab_version"] = page.evaluate("LAB.version")

        if args.topic:
            print(f"   movzu: {page.evaluate('v => LAB.setTopic(v)', args.topic)}")
        if args.context:
            page.evaluate("t => LAB.setContext(t)", args.context)

        print("2) LAB.generate() — yazi zenciri (radar -> 2 konsept -> redaktor -> qalib)...")
        t0 = time.time()
        page.evaluate("() => LAB.generate()")
        state = page.evaluate("LAB.state()")
        report["steps"].append({"step": "generate", "seconds": round(time.time() - t0, 1)})
        report["winner"] = (state.get("variants") or [None])[0]
        report["critiques"] = state.get("critiques")
        print(f"   qalib konsept: {(report['winner'] or {}).get('konsept', '?')} ({report['steps'][-1]['seconds']}s)")

        if not report["winner"]:
            # Yazı zənciri boş qayıtdı (adətən model 429/quota) — render mənasızdır,
            # amma hesabat + console log yenə yazılır ki, səbəb görünsün.
            report["error"] = "generate variant qaytarmadı — model çağırışı uğursuz (console.log-a bax)"
            args.skip_visual = True
            print("   XƏTA: variant yoxdur — vizual mərhələ ötürülür")

        if not args.skip_visual:
            print("3) LAB.render() — vizual zencir (board -> art-direktor -> render -> jury -> qatlar)...")
            t0 = time.time()
            try:
                page.evaluate("() => LAB.render()")
            except Exception as e:
                report["render_error"] = str(e)[:400]
                print(f"   RENDER XƏTASI: {str(e)[:160]}")
            report["steps"].append({"step": "render", "seconds": round(time.time() - t0, 1)})
            report["jury"] = page.evaluate("LAB.juryBadge()")
            report["kitchen"] = page.evaluate("LAB.kitchen()")
            report["loader"] = page.evaluate("LAB.loaderText ? LAB.loaderText() : ''")
            if report["loader"]:
                print(f"   loader/xeta: {report['loader'][:160]}")
            uris = page.evaluate("LAB.gallery()")
            saved = []
            for i, u in enumerate(uris):
                p = save_data_uri(u, run_dir / f"visual_{i:02d}")
                if p:
                    saved.append(p.name)
            report["visuals"] = saved
            print(f"   jury: {report['jury']} | shekil: {len(saved)} ({report['steps'][-1]['seconds']}s)")

        report["used_creative"] = page.evaluate("LAB.usedCreative()")
        page.screenshot(path=str(run_dir / "page.png"), full_page=True)
        browser.close()

    console_log.close()
    (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK -> {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
