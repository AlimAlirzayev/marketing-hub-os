"""Optional headless-render engine (Playwright + system Chrome).

The SSR/API tier (httpx + curl_cffi) covers most sources. A handful of AZ
platforms render prices only after JS runs (qiymeti.net's live-search dropdown,
ucuzu/umico SPAs). `--deep` drives a real Chrome to render those, then the
normal digest+LLM extractor takes over.

Kept fully optional: if Playwright or a Chrome channel isn't available the agent
runs without it and the deep sources are surfaced as skipped. We use the
*system* Chrome channel (no 130MB browser download — corporate-friendly).
"""

from __future__ import annotations

from config import HTTP_TIMEOUT

_CHANNELS = ("chrome", "msedge", "chromium")


def available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def render_sync(url: str, *, type_into: str | None = None,
                type_text: str | None = None, wait_selector: str | None = None,
                wait_ms: int = 2600) -> str:
    """Render `url` in headless Chrome and return the final HTML.

    Optional interaction: type `type_text` into the `type_into` selector first
    (e.g. qiymeti.net's search box that only then fires its ajax dropdown).
    Returns "" on any failure so callers degrade gracefully.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""
    last = ""
    with sync_playwright() as p:
        browser = None
        for ch in _CHANNELS:
            try:
                browser = p.chromium.launch(channel=None if ch == "chromium" else ch,
                                            headless=True)
                break
            except Exception as exc:  # noqa: BLE001 - try the next channel
                last = str(exc)[:80]
        if browser is None:
            return ""
        try:
            ctx = browser.new_context(locale="az-AZ",
                                      viewport={"width": 1366, "height": 900})
            pg = ctx.new_page()
            pg.goto(url, wait_until="domcontentloaded",
                    timeout=int(HTTP_TIMEOUT * 1000) + 20000)
            if type_into and type_text:
                el = pg.query_selector(type_into)
                if el:
                    el.click()
                    el.type(type_text, delay=110)
            if wait_selector:
                try:
                    pg.wait_for_selector(wait_selector, timeout=9000)
                except Exception:
                    pass
            else:
                try:
                    pg.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass
            pg.wait_for_timeout(wait_ms)
            # nudge lazy lists
            for _ in range(2):
                pg.mouse.wheel(0, 4000)
                pg.wait_for_timeout(500)
            return pg.content()
        except Exception:
            return ""
        finally:
            browser.close()
