"""doit — Ramin-OS autonomous credential-acquisition agent.

The "force" that fetches an API key itself instead of asking you to. It drives a
real Chromium browser (Chrome or Edge — your choice) under your own logged-in
session, opens the provider dashboard, locates the key in the page / network, and
writes it straight into the repo `.env`. Then it hands off to the provider's own
probe to confirm what the key unlocks.

Honest boundaries (by design, not by limitation):
  * It uses *your* browser session — it does not forge accounts or defeat CAPTCHA.
    Two ways to give it a session:
      1. Default: doit keeps its own persistent profile (`doit/.profile-<browser>`).
         The first run opens a visible window; you log in once; every later run is
         fully autonomous.
      2. `--user-data-dir` pointing at your real Chrome/Edge profile → it uses the
         session you are already logged into (that browser must be fully closed).
  * Where a live dashboard's DOM is unpredictable, it does not pretend success —
    it pauses in a visible window for one human action, then resumes automatically.

Browser choice is real, not arbitrary: Chrome and Edge are both Chromium and both
verified to drive on this machine; default is Chrome because that is where a
RapidAPI login most commonly lives. Override with `--browser edge`.
"""

from __future__ import annotations

import os
import sys
import time

from . import envfile, keyscan

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DEFAULT_ENV = os.path.join(REPO_ROOT, ".env")

# Each provider recipe stays declarative so adding one is data, not a new code path.
RECIPES: dict[str, dict] = {
    "rapidapi": {
        "env_var": "RAPIDAPI_KEY",
        "dashboard": "https://rapidapi.com/developer/apps",
        "scan_urls": [
            "https://rapidapi.com/developer/apps",
            "https://rapidapi.com/developer/security",
        ],
        "login_markers": ("/auth", "/login", "auth.rapidapi"),
        "ready_marker": "/developer",
    },
}


def _channel(browser: str) -> str:
    b = (browser or "auto").lower()
    if b in ("chrome", "google-chrome", "gchrome"):
        return "chrome"
    if b in ("edge", "msedge"):
        return "msedge"
    # auto: prefer Chrome if present, else Edge.
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    return "chrome" if os.path.exists(chrome) else "msedge"


def _log(msg: str) -> None:
    line = f"[doit] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        # Windows cp1252 console can't encode Azerbaijani — write bytes directly.
        sys.stdout.buffer.write((line + "\n").encode("utf-8", "replace"))
        sys.stdout.flush()


def _scan_page(page, captures: list[str]) -> str:
    """Look for a RapidAPI key in everything this page exposes."""
    blobs: list[str] = list(captures)
    try:
        blobs.append(page.content())
    except Exception:  # noqa: BLE001
        pass
    for selector, js in (
        ("input,textarea", "els => els.map(e => e.value).join('\\n')"),
        ("code,pre", "els => els.map(e => e.textContent).join('\\n')"),
    ):
        try:
            blobs.append(page.eval_on_selector_all(selector, js))
        except Exception:  # noqa: BLE001
            pass
    return keyscan.first_rapidapi_key("\n".join(b for b in blobs if b))


def _is_login(url: str, recipe: dict) -> bool:
    return any(m in url for m in recipe["login_markers"])


def acquire(
    provider: str = "rapidapi",
    *,
    browser: str = "auto",
    headless: bool = False,
    env_path: str = DEFAULT_ENV,
    user_data_dir: str | None = None,
    profile_directory: str | None = None,
    subscribe_url: str | None = None,
    login_timeout: int = 240,
) -> dict:
    """Acquire a provider key and write it to env_path. Returns a status dict."""
    recipe = RECIPES.get(provider)
    if not recipe:
        return {"ok": False, "provider": provider, "error": f"tanınmayan provider: {provider}"}

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "provider": provider,
                "error": f"playwright yoxdur ({exc}); quraşdır: .venv/Scripts/python -m pip install playwright"}

    channel = _channel(browser)
    profile_dir = user_data_dir or os.path.join(HERE, f".profile-{channel}")
    os.makedirs(profile_dir, exist_ok=True)
    args = []
    if profile_directory:
        args.append(f"--profile-directory={profile_directory}")

    captures: list[str] = []
    result: dict = {"ok": False, "provider": provider, "browser": channel, "env": env_path}

    _log(f"{channel} açılır (profil: {profile_dir}) — sessiyan istifadə olunur")
    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                profile_dir, channel=channel, headless=headless, args=args, accept_downloads=False,
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "ProcessSingleton" in msg or "lock" in msg.lower() or "in use" in msg.lower():
                return {**result, "error": "brauzer profili kilidlidir — həmin brauzeri tam bağla və yenidən işə sal"}
            return {**result, "error": f"brauzer açıla bilmədi: {msg[:200]}"}

        def _sniff(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if any(t in ct for t in ("json", "javascript", "text")):
                    found = keyscan.find_rapidapi_keys(resp.text())
                    if found:
                        captures.extend(found)
            except Exception:  # noqa: BLE001
                pass

        ctx.on("response", _sniff)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        try:
            page.goto(recipe["dashboard"], wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:  # noqa: BLE001
            ctx.close()
            return {**result, "error": f"dashboard açıla bilmədi: {str(exc)[:160]}"}

        # --- ensure a logged-in session ---
        if _is_login(page.url, recipe):
            if headless:
                ctx.close()
                return {**result, "error": "sessiya login deyil. --headless olmadan bir dəfə işə sal və daxil ol "
                                           "(və ya real profilini --user-data-dir ilə göstər)"}
            _log("Görünən pəncərədə RapidAPI hesabına daxil ol (Google/email + lazım gəlsə CAPTCHA). Gözləyirəm...")
            deadline = time.time() + login_timeout
            while time.time() < deadline and _is_login(page.url, recipe):
                time.sleep(2)
            if _is_login(page.url, recipe):
                ctx.close()
                return {**result, "error": "login vaxtı bitdi — yenidən cəhd et"}
            _log("Login tamamlandı, sessiya yadda saxlanıldı.")

        # --- locate the key across the dashboard pages ---
        key = ""
        for url in recipe["scan_urls"]:
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(1500)
            except Exception as exc:  # noqa: BLE001 — incl. the window being closed
                if "closed" in str(exc).lower():
                    ctx.close()
                    return {**result, "error": "brauzer pəncərəsi bağlandı — pəncərəni "
                                               "bağlama, agent özü bağlayacaq; yenidən işə sal"}
            key = _scan_page(page, captures)
            if key:
                break

        # human-in-the-loop fallback: open visibly, let the user reveal the key, re-scan
        if not key and not headless:
            _log("Açar avtomatik tapılmadı. Görünən pəncərədə açar səhifəni aç (Apps → açar görünsün), "
                 "sonra bu terminalda ENTER bas — qalanını mən edəcəm.")
            try:
                input()
            except EOFError:
                pass
            key = _scan_page(page, captures)

        if subscribe_url:
            try:
                _log(f"Abunə səhifəsi açılır: {subscribe_url} (pulsuz planı təsdiqlə)")
                page.goto(subscribe_url, wait_until="domcontentloaded", timeout=45000)
                if not headless:
                    _log("Pulsuz 'Subscribe' düyməsini bas, sonra ENTER.")
                    try:
                        input()
                    except EOFError:
                        pass
            except Exception:  # noqa: BLE001
                pass

        ctx.close()

    if not key:
        return {**result, "error": "açar tapılmadı — hesabda ən azı bir application olduğundan əmin ol"}

    action = envfile.upsert(env_path, recipe["env_var"], key)
    result.update({"ok": True, "env_var": recipe["env_var"], "action": action,
                   "key_preview": key[:6] + "…" + key[-4:]})
    return result


def verify_rapidapi() -> str:
    """Best-effort confirmation using the influencer-hunter probe, if reachable."""
    probe = os.path.join(REPO_ROOT, "influencer-hunter", "rapidapi_probe.py")
    if os.path.exists(probe):
        return f"təsdiq üçün:  .venv/Scripts/python {os.path.relpath(probe, REPO_ROOT)}"
    return "təsdiq üçün öz rapidapi_probe alətini işə sal"
