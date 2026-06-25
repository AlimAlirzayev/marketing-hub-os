"""Subscription Bridge — drive your *real*, logged-in Chrome via the debug port.

The whole point: use the Gemini / ChatGPT sessions you are ALREADY logged into,
instead of a fresh empty browser. The catch is how browsers work:

  • Chrome lets only ONE process use a profile at a time, and you cannot attach
    to a normally-launched Chrome. To reuse your logins, Chrome must be started
    once with a remote-debugging port; the bridge then ATTACHES to it (CDP) and
    opens a tab — your existing sessions are right there.

Two ways to get that debug Chrome (see open_chrome_debug):
  • profile="real"   → your actual Chrome profile (all logins). You must close
    your normal Chrome first (profile lock).
  • profile="bridge" → a dedicated profile that stays open alongside normal
    Chrome; you log in once and it persists.

Runs as a SEPARATE PROCESS (CLI) so Playwright's sync API never collides with
Streamlit's event loop. Best-effort: site DOMs change, so the generate selectors
may need a live tuning pass.

CLI:
    python -m atelier.web_bridge --open-chrome --profile real
    python -m atelier.web_bridge --open-chrome --profile bridge
    python -m atelier.web_bridge --generate --site gemini --prompt "..." --out img.png
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
import time

from . import config

PROFILE_ROOT = os.path.join(config.DATA_DIR, "browser_profiles")
DEBUG_PORT = int(os.getenv("ATELIER_BRIDGE_PORT", "9222"))
CDP_URL = f"http://127.0.0.1:{DEBUG_PORT}"

SITES = {
    "gemini": {
        "url": "https://gemini.google.com/app",
        "input": ['rich-textarea div[contenteditable="true"]',
                  'div[contenteditable="true"]', 'textarea'],
        "login_markers": ["accounts.google.com"],
    },
    "chatgpt": {
        "url": "https://chatgpt.com/",
        "input": ['#prompt-textarea', 'div[contenteditable="true"]', 'textarea'],
        "login_markers": ["auth.openai.com", "login"],
    },
}


# --------------------------------------------------------------------------
# Launch a debug Chrome (so we can attach to your real logins)
# --------------------------------------------------------------------------
def _chrome_path() -> str | None:
    cands = [
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     r"Google\Chrome\Application\chrome.exe"),
    ]
    return next((p for p in cands if p and os.path.isfile(p)), None)


def open_chrome_debug(profile: str = "bridge") -> int:
    chrome = _chrome_path()
    if not chrome:
        print("ERR chrome.exe tapılmadı")
        return 2
    if profile == "real":
        udd = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data")
        args = [chrome, f"--remote-debugging-port={DEBUG_PORT}",
                f"--user-data-dir={udd}", "--profile-directory=Default",
                "--restore-last-session"]
        hint = ("real profil — bütün loginlərin. (Əgər adi Chrome açıqdırsa, "
                "debug port aktiv olmaya bilər; əvvəlcə Chrome-u tam bağla.)")
    else:
        udd = os.path.join(PROFILE_ROOT, "debug-chrome")
        os.makedirs(udd, exist_ok=True)
        args = [chrome, f"--remote-debugging-port={DEBUG_PORT}",
                f"--user-data-dir={udd}"]
        hint = "ayrıca bridge profili — Gemini/ChatGPT-yə bir dəfə login ol."
    subprocess.Popen(args, close_fds=True)
    print(f"OK debug Chrome açıldı ({profile}): {hint}")
    return 0


# --------------------------------------------------------------------------
# Connect: attach to the debug Chrome (CDP) → fall back to a dedicated profile
# --------------------------------------------------------------------------
def _connect(site: str, headless: bool):
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=4000)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        return pw, browser, ctx, "cdp"
    except Exception:
        pass
    last = None
    for channel in ("chrome", "msedge", None):
        try:
            ctx = pw.chromium.launch_persistent_context(
                _profile_dir(site), headless=headless, channel=channel,
                args=["--start-maximized"], no_viewport=True)
            return pw, None, ctx, "persistent"
        except Exception as exc:  # noqa: BLE001
            last = exc
    pw.stop()
    raise RuntimeError(f"Could not attach to debug Chrome nor launch one: {last}")


def _profile_dir(site: str) -> str:
    d = os.path.join(PROFILE_ROOT, site)
    os.makedirs(d, exist_ok=True)
    return d


def _first(page, selectors: list[str]):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                return loc.first
        except Exception:  # noqa: BLE001
            continue
    return None


def _img_bytes(page, src: str) -> bytes | None:
    if src.startswith("data:image"):
        return base64.b64decode(src.split(",", 1)[1])
    try:
        data_url = page.evaluate(
            """async (src) => {
                const r = await fetch(src); const b = await r.blob();
                return await new Promise(res => {
                    const fr = new FileReader();
                    fr.onloadend = () => res(fr.result);
                    fr.readAsDataURL(b);
                });
            }""", src)
        if data_url and "," in data_url:
            return base64.b64decode(data_url.split(",", 1)[1])
    except Exception:  # noqa: BLE001
        return None
    return None


def generate(site: str, prompt: str, out_path: str, headless: bool = False,
             wait_s: int = 150) -> int:
    cfg = SITES[site]
    pw, browser, ctx, mode = _connect(site, headless)
    pg = ctx.new_page() if mode == "cdp" else (ctx.pages[0] if ctx.pages else ctx.new_page())
    try:
        pg.goto(cfg["url"], wait_until="domcontentloaded", timeout=60_000)
        pg.wait_for_timeout(2500)

        if any(m in pg.url for m in cfg["login_markers"]):
            print(f"ERR not-logged-in — debug Chrome-da {site}-yə login ol "
                  f"(mode={mode}).")
            return 3

        box = _first(pg, cfg["input"])
        if not box:
            print(f"ERR input-not-found (mode={mode}; UI dəyişib — selector kökləmə lazımdır)")
            return 4
        box.click()
        box.type(prompt, delay=3)
        pg.keyboard.press("Enter")

        deadline = time.time() + wait_s
        best = None
        while time.time() < deadline:
            pg.wait_for_timeout(2000)
            srcs = pg.eval_on_selector_all(
                "img",
                "els => els.filter(e => e.naturalWidth >= 256)"
                ".map(e => ({src: e.currentSrc || e.src, w: e.naturalWidth}))")
            srcs = [s for s in srcs if s.get("src")
                    and not s["src"].startswith("https://www.google.com/images")]
            if srcs:
                best = max(srcs, key=lambda s: s["w"])
                break
        if not best:
            print("ERR no-image (timeout — slow/blocked, or selector tuning needed)")
            return 5

        data = _img_bytes(pg, best["src"])
        if not data:
            print("ERR could-not-download-image-bytes")
            return 6
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"OK {out_path} ({len(data)} bytes, mode={mode})")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERR {type(exc).__name__}: {exc}")
        return 7
    finally:
        try:
            if mode == "cdp":
                pg.close()  # close only our tab; leave the user's browser running
            else:
                ctx.close()
        finally:
            pw.stop()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gemini/ChatGPT subscription bridge")
    ap.add_argument("--site", choices=list(SITES))
    ap.add_argument("--open-chrome", action="store_true")
    ap.add_argument("--profile", choices=["real", "bridge"], default="bridge")
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args(argv)
    if a.open_chrome:
        return open_chrome_debug(a.profile)
    if a.generate:
        if not a.site or not a.prompt or not a.out:
            print("ERR --site, --prompt, --out required")
            return 1
        return generate(a.site, a.prompt, a.out, headless=a.headless)
    print("ERR specify --open-chrome or --generate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
