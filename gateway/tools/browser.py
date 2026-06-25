"""A Playwright-backed browser the agent can drive autonomously.

Design choices that matter:
- Returns TEXT (titles, visible text, link lists), never screenshots. The agent
  reasons over text, which is far cheaper in tokens and faster than the
  screenshot-by-screenshot loop we are replacing.
- Read/navigate is free; any IRREVERSIBLE action (buy, pay, delete, submit...)
  is blocked and reported instead of executed -- the checkpoint principle.
- Every method catches its own errors and returns a readable string, so a bad
  click makes the agent adapt instead of crashing the whole job.
"""

from __future__ import annotations

import re

from .. import security

# Visible-text keywords that mark a click as irreversible / state-changing.
# Clicking these is refused in autonomous mode; the user must approve.
_RISKY = (
    "buy", "pay", "purchase", "checkout", "order", "place order", "subscribe",
    "delete", "remove", "confirm", "submit", "send", "book now", "donate",
    "al", "öde", "ödə", "sifariş", "təsdiq", "sil", "abunə",  # AZ equivalents
)

_MAX_TEXT = 3500   # chars of page text fed back per read
_MAX_LINKS = 40
_NAV_TIMEOUT = 30_000  # ms


def _is_risky(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _RISKY)


def _collapse(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


class BrowserSession:
    """Headless Chromium session. Use as a context manager."""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._pw = None
        self._browser = None
        self.page = None

    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        ctx = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        self.page = ctx.new_page()
        self.page.set_default_timeout(_NAV_TIMEOUT)
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    # --- tool surface (each returns a short observation string) ---------------

    def open(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        decision = security.validate_url(url)
        security.audit_event("browser_open", decision, {"url": url})
        if not decision.allowed:
            return security.format_blocked_message(decision)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT)
            self.page.wait_for_timeout(800)  # let late content settle
            return f"Opened {self.page.url}\nTitle: {self.page.title()}"
        except Exception as exc:
            return f"ERROR opening {url}: {exc}"

    def read(self) -> str:
        try:
            body = self.page.inner_text("body")
            text = _collapse(body)
            clip = text[:_MAX_TEXT]
            more = "" if len(text) <= _MAX_TEXT else f"\n...[{len(text) - _MAX_TEXT} more chars truncated]"
            return f"PAGE TEXT ({self.page.url}):\n{clip}{more}"
        except Exception as exc:
            return f"ERROR reading page: {exc}"

    def links(self) -> str:
        try:
            items = self.page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => ({t: (e.innerText||'').trim(), h: e.href}))"
                ".filter(x => x.t && x.h)",
            )
            seen, out = set(), []
            for it in items:
                key = it["t"][:60]
                if key in seen:
                    continue
                seen.add(key)
                out.append(f"- {it['t'][:60]} -> {it['h']}")
                if len(out) >= _MAX_LINKS:
                    break
            return "LINKS:\n" + ("\n".join(out) if out else "(none found)")
        except Exception as exc:
            return f"ERROR listing links: {exc}"

    def click(self, text: str) -> str:
        if _is_risky(text):
            return (
                f"BLOCKED: '{text}' looks irreversible (payment/submit/delete). "
                "Autonomous mode will not perform it without explicit approval. "
                "Report this to the user as a checkpoint instead."
            )
        try:
            self.page.get_by_text(text, exact=False).first.click(timeout=_NAV_TIMEOUT)
            self.page.wait_for_timeout(800)
            return f"Clicked '{text}'. Now at {self.page.url}\nTitle: {self.page.title()}"
        except Exception as exc:
            return f"ERROR clicking '{text}': {exc}"
