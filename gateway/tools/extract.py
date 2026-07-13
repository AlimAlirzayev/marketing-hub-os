"""Unified extraction — one door for pulling clean text out of the messy web.

The professional scraping stack from Alim's course, folded into ONE capability
the whole OS can call (executor, agent, studios) instead of each place hand-rolling
requests+BeautifulSoup:

  * fetch()      — requests FIRST (fast, cheap); escalate to Playwright only when
                   the page is JS-rendered or the datacenter IP is blocked. The
                   right tool per page, not a browser for everything.
  * clean_text() — BeautifulSoup main-content extraction (strip nav/script/chrome).
  * read_pdf()   — pypdf: a PDF becomes text.
  * ocr()        — pytesseract (aze+eng): an image/screenshot becomes text.
  * scrape()     — the orchestration: url -> {title, text, method}.

Residential proxy (BrightData & co.) is env-configured and OFF by default — a
blocked site can be retried through SCRAPER_PROXY without touching call sites.

Security: outbound reads only; never posts/logs credentials. Honors the same
trust model as the rest of the gateway.
"""

from __future__ import annotations

import io
import os
import re

import requests

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
_DROP_TAGS = ("script", "style", "noscript", "template", "svg", "nav",
              "footer", "header", "aside", "form", "iframe")


def _proxy() -> str | None:
    """A residential/rotating proxy URL, if the operator configured one."""
    return (os.getenv("SCRAPER_PROXY") or os.getenv("BRIGHTDATA_PROXY") or "").strip() or None


def _soup(html: str):
    """Parse with lxml when available, else the stdlib parser. Without this a
    host missing lxml raised FeatureNotFound inside fetch(), which the escalation
    try/except swallowed — so EVERY page silently took the slow browser path
    instead of the fast one. Degrade, don't misroute."""
    from bs4 import BeautifulSoup
    try:
        return BeautifulSoup(html or "", "lxml")
    except Exception:  # noqa: BLE001 — lxml absent/broken on this host
        return BeautifulSoup(html or "", "html.parser")


def _looks_thin(html: str) -> bool:
    """Did the fast path return too little real text to trust? A scraper's job is
    to GET the content, so we escalate to a real browser whenever the visible
    text (script/style stripped, so a SPA's inline JS isn't miscounted) is thin.
    The only cost is one browser launch on a genuinely tiny page — cheap next to
    silently missing a JS-rendered page's content."""
    if not html:
        return True
    soup = _soup(html)
    for tag in soup(("script", "style", "noscript", "template")):
        tag.decompose()
    return len(re.sub(r"\s+", " ", soup.get_text(" ", strip=True))) < 300


def fetch(url: str, *, render: bool | None = None, proxy: str | None = None,
          timeout: int = 25) -> tuple[str, str]:
    """Return (html, method). method ∈ {'requests','browser'}.

    render=False forces the fast path, True forces the browser, None (default)
    auto-escalates: try requests, fall back to a real browser if blocked/thin.
    """
    proxy = proxy or _proxy()
    if not render:
        try:
            proxies = {"http": proxy, "https": proxy} if proxy else None
            r = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout,
                             proxies=proxies, allow_redirects=True)
            if r.status_code < 400 and not _looks_thin(r.text):
                return r.text, "requests"
            if render is False:  # caller forbade escalation
                return (r.text or ""), "requests"
        except Exception:
            if render is False:
                raise
    # browser path: run the page's JS (reuses the installed Playwright chromium)
    return _fetch_browser(url, proxy=proxy, timeout=timeout), "browser"


def _fetch_browser(url: str, *, proxy: str | None, timeout: int) -> str:
    from playwright.sync_api import sync_playwright
    launch: dict = {"headless": True}
    if proxy:
        launch["proxy"] = {"server": proxy}
    with sync_playwright() as p:
        b = p.chromium.launch(**launch)
        pg = b.new_context(user_agent=_UA).new_page()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            pg.wait_for_timeout(2000)
            html = pg.content()
        finally:
            b.close()
    return html


def clean_text(html: str) -> str:
    """Main-content plain text: drop chrome/scripts, prefer <article>/<main>."""
    soup = _soup(html)
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    text = root.get_text("\n", strip=True) if root else ""
    # collapse runs of blank lines that survive stripping
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def page_title(html: str) -> str:
    soup = _soup(html)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def read_pdf(src) -> str:
    """Extract text from a PDF given a path, raw bytes, or a URL."""
    from pypdf import PdfReader
    if isinstance(src, str) and src.lower().startswith(("http://", "https://")):
        src = requests.get(src, headers={"User-Agent": _UA}, timeout=40).content
    stream = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src
    reader = PdfReader(stream)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return re.sub(r"\n{3,}", "\n\n", "\n".join(parts)).strip()


def ocr(src, *, lang: str = "aze+eng") -> str:
    """Read text off an image (path, bytes, or URL) via tesseract. Returns a
    clear message rather than raising if OCR isn't available on this host."""
    try:
        import pytesseract
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        return f"[ocr unavailable: {exc}]"
    if isinstance(src, str) and src.lower().startswith(("http://", "https://")):
        src = requests.get(src, headers={"User-Agent": _UA}, timeout=40).content
    img = Image.open(io.BytesIO(src)) if isinstance(src, (bytes, bytearray)) else Image.open(src)
    try:
        return pytesseract.image_to_string(img, lang=lang).strip()
    except Exception:
        return pytesseract.image_to_string(img).strip()  # fall back to default lang


def scrape(url: str, *, render: bool | None = None, proxy: str | None = None,
           max_chars: int = 20000) -> dict:
    """Pull clean text from a URL (HTML or PDF). The single high-level entry
    point for the agent/executor. Returns a compact dict, never raises."""
    try:
        if url.lower().split("?")[0].endswith(".pdf"):
            text = read_pdf(url)
            return {"ok": True, "url": url, "title": "", "method": "pdf",
                    "chars": len(text), "text": text[:max_chars]}
        html, method = fetch(url, render=render, proxy=proxy)
        text = clean_text(html)
        return {"ok": True, "url": url, "title": page_title(html), "method": method,
                "chars": len(text), "text": text[:max_chars]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": url, "error": f"{exc.__class__.__name__}: {exc}"[:200]}
