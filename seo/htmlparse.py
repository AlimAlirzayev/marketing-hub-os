"""Dependency-light HTML extraction (stdlib only — no bs4 / lxml).

Runs on the locked-down machine where native/heavy parsers are unwelcome. Pulls
exactly the on-page SEO signals the auditor scores: title, meta, canonical,
robots directives, heading tree, images/alt, links, viewport, lang/hreflang,
Open Graph/Twitter, and JSON-LD structured data.

It is deliberately forgiving: malformed markup yields partial data, never an
exception. Good enough for auditing 99% of real-world pages.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class PageData:
    title: str = ""
    meta_description: str = ""
    meta_robots: str = ""
    canonical: str = ""
    viewport: str = ""
    charset: str = ""
    html_lang: str = ""
    favicon: bool = False
    headings: list[tuple[int, str]] = field(default_factory=list)   # (level, text)
    img_total: int = 0
    img_missing_alt: int = 0
    link_total: int = 0
    link_internal: int = 0
    link_external: int = 0
    og: dict = field(default_factory=dict)          # og:* / twitter:*
    hreflang: list[str] = field(default_factory=list)
    jsonld: list = field(default_factory=list)       # parsed JSON-LD objects
    jsonld_types: list[str] = field(default_factory=list)
    text_words: int = 0

    @property
    def h1(self) -> list[str]:
        return [t for lvl, t in self.headings if lvl == 1]


_WS = re.compile(r"\s+")
_TEXT_TAGS_SKIP = {"script", "style", "noscript", "template", "svg"}


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.d = PageData()
        self._cur_heading: int | None = None
        self._heading_buf: list[str] = []
        self._in_title = False
        self._title_buf: list[str] = []
        self._in_jsonld = False
        self._jsonld_buf: list[str] = []
        self._skip_depth = 0
        self._text_len = 0

    # --- helpers ---
    @staticmethod
    def _attrs(attrs):
        return {k.lower(): (v or "") for k, v in attrs}

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = self._attrs(attrs)

        if tag in _TEXT_TAGS_SKIP:
            self._skip_depth += 1

        if tag == "html" and "lang" in a and not self.d.html_lang:
            self.d.html_lang = a["lang"].strip()

        elif tag == "title":
            self._in_title = True
            self._title_buf = []

        elif tag == "meta":
            name = a.get("name", "").lower()
            prop = a.get("property", "").lower()
            content = a.get("content", "").strip()
            if a.get("charset"):
                self.d.charset = a["charset"].strip()
            if name == "description" and not self.d.meta_description:
                self.d.meta_description = content
            elif name == "robots":
                self.d.meta_robots = content.lower()
            elif name == "viewport":
                self.d.viewport = content
            elif name == "charset":
                self.d.charset = content
            if prop.startswith("og:") or name.startswith("twitter:"):
                self.d.og[prop or name] = content

        elif tag == "link":
            rel = a.get("rel", "").lower()
            href = a.get("href", "").strip()
            if "canonical" in rel and not self.d.canonical:
                self.d.canonical = href
            if "icon" in rel:
                self.d.favicon = True
            if rel == "alternate" and a.get("hreflang"):
                self.d.hreflang.append(a["hreflang"].strip())

        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._cur_heading = int(tag[1])
            self._heading_buf = []

        elif tag == "img":
            self.d.img_total += 1
            alt = a.get("alt", None)
            # missing OR empty (and not explicitly decorative role) counts as gap
            if alt is None or not alt.strip():
                self.d.img_missing_alt += 1

        elif tag == "a":
            href = a.get("href", "").strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                self.d.link_total += 1
                if href.startswith(("http://", "https://")):
                    self.d.link_external += 1  # refined against host later by caller
                else:
                    self.d.link_internal += 1

        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_buf = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _TEXT_TAGS_SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
            self.d.title = _WS.sub(" ", "".join(self._title_buf)).strip()
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._cur_heading:
            text = _WS.sub(" ", "".join(self._heading_buf)).strip()
            self.d.headings.append((self._cur_heading, text))
            self._cur_heading = None
        elif tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self._ingest_jsonld("".join(self._jsonld_buf))

    def handle_data(self, data):
        if self._in_title:
            self._title_buf.append(data)
        if self._cur_heading:
            self._heading_buf.append(data)
        if self._in_jsonld:
            self._jsonld_buf.append(data)
        if not self._skip_depth and not self._in_jsonld:
            s = data.strip()
            if s:
                self._text_len += len(s.split())

    def _ingest_jsonld(self, raw: str):
        raw = raw.strip()
        if not raw:
            return
        try:
            obj = json.loads(raw)
        except ValueError:
            return
        items = obj if isinstance(obj, list) else [obj]
        for it in items:
            if not isinstance(it, dict):
                continue
            self.d.jsonld.append(it)
            t = it.get("@type")
            if isinstance(t, list):
                self.d.jsonld_types.extend(str(x) for x in t)
            elif t:
                self.d.jsonld_types.append(str(t))
            # @graph nesting (very common)
            for g in it.get("@graph", []) if isinstance(it.get("@graph"), list) else []:
                if isinstance(g, dict):
                    self.d.jsonld.append(g)
                    gt = g.get("@type")
                    if isinstance(gt, list):
                        self.d.jsonld_types.extend(str(x) for x in gt)
                    elif gt:
                        self.d.jsonld_types.append(str(gt))


def parse(html: str) -> PageData:
    p = _Parser()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 — never let a broken page crash the audit
        pass
    p.d.text_words = p._text_len
    # de-dup schema types, preserve order
    seen: set[str] = set()
    p.d.jsonld_types = [t for t in p.d.jsonld_types if not (t in seen or seen.add(t))]
    return p.d
