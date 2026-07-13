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

from . import cookies as cookiejar, envfile, keyscan, profile as profiles

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
        "session_domain": "rapidapi.com",  # whose cookies mark a logged-in profile
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


def _mid_auth(url: str, recipe: dict) -> bool:
    """True while the human may be actively typing credentials somewhere —
    the agent must NOT navigate the page out from under them (incl. external
    identity providers like Google OAuth)."""
    return _is_login(url, recipe) or "accounts." in url or "/sso" in url


def doctor(provider: str = "rapidapi") -> dict:
    """Say — BEFORE launching anything — whether a session exists to borrow.

    doit inherits the operator's session; it never authenticates (Google OAuth
    refuses automation-driven browsers by design). So the only precondition that
    can block a fully autonomous run is: the operator has never signed in to the
    provider in ANY local browser profile. That is an account fact, not a bug —
    and it must be reported as one clean sentence instead of a failed browser run.
    """
    recipe = RECIPES.get(provider)
    if not recipe:
        return {"ok": False, "provider": provider, "error": f"tanınmayan provider: {provider}"}
    domain = recipe.get("session_domain", "")
    report: dict = {"ok": False, "provider": provider, "domain": domain, "profiles": []}

    for ch in ("chrome", "msedge"):
        if not profiles.user_data_root(ch):
            continue
        found = profiles.find_profile(domain, ch)
        if found:
            _root, prof, hits = found
            report["profiles"].append({"browser": ch, "profile": prof, "cookies": hits})

    if report["profiles"]:
        best = report["profiles"][0]
        report["ok"] = True
        report["message"] = (
            f"Sessiya hazırdır: {best['browser']} profili «{best['profile']}» "
            f"({best['cookies']} {domain} cookie). doit login etmədən açarı gətirə bilər."
        )
        return report

    # No provider session anywhere. Tell them the ONE human action that fixes it,
    # and whether the identity provider they'd use is already signed in.
    google = next(
        (f for ch in ("chrome", "msedge")
         if profiles.user_data_root(ch)
         for f in [profiles.find_profile("google.com", ch)] if f),
        None,
    )
    hint = (
        f"Google sessiyan artıq var ({google[1]} profilində) — rapidapi.com-da "
        "«Sign in with Google» bir kliklə keçəcək, parol soruşmayacaq."
        if google else
        "Əvvəlcə brauzerində hesab yarat/daxil ol."
    )
    report["message"] = (
        f"{domain} üçün heç bir brauzer profilində sessiya YOXDUR — yəni bu hesaba "
        "heç vaxt daxil olunmayıb. doit sessiya miras alır, özü login etmir "
        "(Google OAuth avtomatlaşdırılmış brauzeri qəbul etmir).\n"
        f"BİR DƏFƏLİK insan addımı: adi (avtomatlaşdırılmamış) brauzerində "
        f"https://{domain} aç → daxil ol. {hint}\n"
        "Sonra doit sessiyanı götürüb açarı tam avtonom gətirəcək."
    )
    return report


def _needs_login(url: str, recipe: dict) -> bool:
    """Login detection can't trust URL markers alone: RapidAPI renders its
    login screen without an /auth or /login URL. Treat 'not on the dashboard'
    (ready_marker absent) as not-logged-in too."""
    if _is_login(url, recipe):
        return True
    ready = recipe.get("ready_marker")
    return bool(ready) and ready not in url


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
    reveal_timeout: int = 300,
    borrow_session: bool = True,
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

    # THE SESSION RULE (2026-07-11): doit never authenticates. An automation-
    # driven browser is refused by Google's OAuth ("this browser or app may not
    # be secure") and CAPTCHA is a human's job by design — so logging in from
    # here can't be made to work, no matter how good the code is. Instead we
    # INHERIT the session the operator already has: find the browser profile
    # whose cookie jar carries the provider's domain, snapshot its session files
    # into a scratch dir (their live browser stays open), and drive that.
    borrowed = None
    if not user_data_dir and borrow_session:
        found = profiles.find_profile(recipe.get("session_domain", ""), channel)
        if not found:
            # Fail FAST and actionably. Opening a browser here is pointless: with
            # no session to inherit, doit would land on a login wall it is
            # designed never to pass. One clean sentence beats a failed run.
            diag = doctor(provider)
            return {"ok": False, "provider": provider, "browser": channel,
                    "env": env_path, "session": "yoxdur",
                    "needs_login": True, "error": diag["message"]}
        root, prof, hits = found
        dest = os.path.join(HERE, f".session-{channel}")
        try:
            user_data_dir = profiles.snapshot(root, prof, dest)
            borrowed = f"{prof} ({hits} cookie)"
            _log(f"sessiya götürüldü: {channel} profili «{prof}» — login lazım deyil")
        except Exception as exc:  # noqa: BLE001 — fall back to own profile
            _log(f"sessiya surəti alınmadı ({exc}); öz profilimlə davam edirəm")

    profile_dir = user_data_dir or os.path.join(HERE, f".profile-{channel}")
    os.makedirs(profile_dir, exist_ok=True)
    args = []
    if profile_directory:
        args.append(f"--profile-directory={profile_directory}")

    captures: list[str] = []
    result: dict = {"ok": False, "provider": provider, "browser": channel,
                    "env": env_path, "session": borrowed or "own profile"}

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

        # --- ensure a logged-in session (fully hands-off: no ENTER, no TTY) ---
        if _needs_login(page.url, recipe):
            if headless:
                ctx.close()
                return {**result, "error": "sessiya login deyil. --headless olmadan bir dəfə işə sal və daxil ol "
                                           "(və ya real profilini --user-data-dir ilə göstər)"}
            _log("Görünən pəncərədə RapidAPI hesabına daxil ol (Google/email + lazım gəlsə CAPTCHA). "
                 "Gözləyirəm — login bitəndə özüm davam edəcəm...")
            deadline = time.time() + login_timeout
            last_probe = 0.0
            while time.time() < deadline:
                try:
                    url = page.url
                except Exception:  # noqa: BLE001 — window closed mid-login
                    ctx.close()
                    return {**result, "error": "brauzer pəncərəsi bağlandı — yenidən işə sal"}
                if not _needs_login(url, recipe):
                    break
                # After login the site may drop the user on a marketing page, not
                # the dashboard. Periodically re-aim at the dashboard — but never
                # while the human might be typing credentials.
                if not _mid_auth(url, recipe) and time.time() - last_probe > 12:
                    last_probe = time.time()
                    try:
                        page.goto(recipe["dashboard"], wait_until="domcontentloaded", timeout=30000)
                    except Exception:  # noqa: BLE001
                        pass
                time.sleep(2)
            if _needs_login(page.url, recipe):
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

        # human-in-the-loop fallback, hands-off: keep the window open and keep
        # scanning. The moment the key becomes visible anywhere (the user opens
        # Apps / reveals it, or the account's default app finishes creating),
        # the agent picks it up — no ENTER, no terminal, works with no TTY.
        if not key and not headless:
            _log("Açar avtomatik tapılmadı. Pəncərədə açar səhifəsini aç (Apps → açar görünsün) — "
                 "mən dövri skan edirəm, görünən kimi götürəcəm.")
            deadline = time.time() + reveal_timeout
            last_cycle = 0.0
            while not key and time.time() < deadline:
                time.sleep(5)
                try:
                    key = _scan_page(page, captures)
                except Exception:  # noqa: BLE001 — window closed mid-scan
                    break
                # every ~45s also re-walk the known key pages ourselves
                if not key and time.time() - last_cycle > 45:
                    last_cycle = time.time()
                    for url in recipe["scan_urls"]:
                        try:
                            page.goto(url, wait_until="networkidle", timeout=30000)
                            page.wait_for_timeout(1200)
                            key = _scan_page(page, captures)
                        except Exception:  # noqa: BLE001
                            break
                        if key:
                            break

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


def acquire_with_session(
    provider: str = "rapidapi",
    *,
    channel: str = "chrome",
    env_path: str = DEFAULT_ENV,
    headless: bool = True,
) -> dict:
    """THE autonomous path: carry the operator's own cookies into a clean
    headless browser, read the key off their dashboard, write it to .env.

    No login, no CAPTCHA, no visible window, no human keystroke — because it
    never authenticates: the session already exists in the operator's browser
    (see doit/cookies.py for why every other route is a dead end).
    """
    recipe = RECIPES.get(provider)
    if not recipe:
        return {"ok": False, "provider": provider, "error": f"tanınmayan provider: {provider}"}
    domain = recipe.get("session_domain")
    if not domain:
        return {"ok": False, "provider": provider, "error": "recipe-də session_domain yoxdur"}

    result: dict = {"ok": False, "provider": provider, "browser": f"{channel}-session",
                    "env": env_path}
    found = profiles.find_profile(domain, channel)
    if not found:
        return {**result, "error": f"{channel} profillərində {domain} sessiyası yoxdur — "
                                   "həmin brauzerdə bir dəfə hesaba daxil ol"}
    root, prof, hits = found
    try:
        jar = cookiejar.for_domain(os.path.join(root, prof), domain, channel)
    except cookiejar.CookieError as exc:
        return {**result, "error": str(exc)}
    _log(f"sessiya götürüldü: «{prof}» profili, {len(jar)} cookie — login lazım deyil")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return {**result, "error": f"playwright yoxdur ({exc})"}

    captures: list[str] = []
    key = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context()
        ctx.add_cookies(jar)

        def _sniff(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if any(t in ct for t in ("json", "javascript", "text")):
                    captures.extend(keyscan.find_rapidapi_keys(resp.text()))
            except Exception:  # noqa: BLE001
                pass

        ctx.on("response", _sniff)
        page = ctx.new_page()
        for url in recipe["scan_urls"]:
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2500)
            except Exception:  # noqa: BLE001
                continue
            if _is_login(page.url, recipe):
                browser.close()
                return {**result, "error": "sessiya köhnəlib — brauzerdə yenidən daxil ol"}
            key = _scan_page(page, captures)
            if key:
                break
        browser.close()

    if not key:
        return {**result, "error": "açar tapılmadı — RapidAPI hesabında ən azı bir "
                                   "application olduğundan əmin ol"}
    action = envfile.upsert(env_path, recipe["env_var"], key)
    return {**result, "ok": True, "env_var": recipe["env_var"], "action": action,
            "key_preview": key[:6] + "…" + key[-4:], "key": key}


def verify_rapidapi() -> str:
    """Best-effort confirmation using the influencer-hunter probe, if reachable."""
    probe = os.path.join(REPO_ROOT, "influencer-hunter", "rapidapi_probe.py")
    if os.path.exists(probe):
        return f"təsdiq üçün:  .venv/Scripts/python {os.path.relpath(probe, REPO_ROOT)}"
    return "təsdiq üçün öz rapidapi_probe alətini işə sal"
