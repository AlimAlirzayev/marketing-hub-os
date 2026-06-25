"""Step 2 - fan out across Azerbaijani retail sources and bring back candidates.

Two extraction strategies, chosen per-source automatically:

  * STRUCTURED  - modern stores embed their full product list as JSON in the
                  page (Next.js `__NEXT_DATA__`, Nuxt `window.__NUXT__`, or a
                  JSON API). We harvest that JSON generically with a recursive
                  walker, so we are not tied to brittle CSS classes that change
                  every redesign. Works across bakuelectronics, tap.az, etc.
  * HTML        - aggregators (qiymetleri.az) render prices straight into HTML;
                  we hand the cleaned text to the LLM extractor (extract.py).

Each source returns a list[Offer] with at least title+price+url+source. Failures
are surfaced (never silently dropped) via the returned SourceResult.status.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT, MAX_CONCURRENCY, USER_AGENT
from models import Offer

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "az,en;q=0.9,ru;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}


@dataclass
class SourceResult:
    source: str
    status: str                       # "ok" | "blocked" | "empty" | "error:<x>"
    offers: list[Offer] = field(default_factory=list)
    needs_llm_html: str = ""          # cleaned HTML text for the LLM extractor
    note: str = ""
    # meta the LLM extractor needs (so callers don't re-look-up the registry)
    src_official: object = None
    src_condition: str = "unknown"
    src_url: str = ""


# --------------------------------------------------------------------------
# Generic embedded-JSON harvesting (the robust, layout-agnostic core)
# --------------------------------------------------------------------------
_PRICE_KEYS = ("price", "qiymet", "cost", "amount", "sale_price",
               "current_price", "final_price", "price_azn")
_NAME_KEYS = ("name", "title", "product_name", "label", "ad_title")
_URL_KEYS = ("url", "slug", "href", "link", "mobile_url", "web_url", "path")


def _to_float(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v else None
    s = str(v)
    # keep digits, dot, comma; AZ uses both "1 299,00" and "1299.00"
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        f = float(s)
        return f if f > 0 else None
    except ValueError:
        return None


def _looks_like_product(d: dict) -> bool:
    lk = {k.lower() for k in d.keys()}
    has_name = any(k in lk for k in _NAME_KEYS)
    has_price = any(any(pk in k for pk in _PRICE_KEYS) for k in lk)
    return has_name and has_price


def _pick(d: dict, keys) -> object:
    lk = {k.lower(): k for k in d.keys()}
    for want in keys:
        for k in lk:
            if k == want or want in k:
                return d[lk[k]]
    return None


def harvest_products(obj, base_url: str, found: list[dict] | None = None,
                     depth: int = 0) -> list[dict]:
    """Recursively pull product-like dicts out of arbitrary embedded JSON."""
    if found is None:
        found = []
    if depth > 10 or len(found) > 400:
        return found
    if isinstance(obj, list):
        for x in obj:
            harvest_products(x, base_url, found, depth + 1)
    elif isinstance(obj, dict):
        if _looks_like_product(obj):
            name = _pick(obj, _NAME_KEYS)
            price = _to_float(_pick(obj, _PRICE_KEYS))
            if name and price:
                raw_url = _pick(obj, _URL_KEYS)
                url = ""
                if isinstance(raw_url, str) and raw_url:
                    url = raw_url if raw_url.startswith("http") else urljoin(base_url, raw_url if raw_url.startswith("/") else "/" + raw_url)
                qty = _pick(obj, ("quantity", "stock", "in_stock", "available"))
                code = _pick(obj, ("product_code", "sku", "mpn", "code", "model"))
                found.append({
                    "title": str(name).strip(),
                    "price": price,
                    "url": url,
                    "model_code": str(code).strip() if code else "",
                    "in_stock": None if qty is None else bool(qty),
                })
        for v in obj.values():
            harvest_products(v, base_url, found, depth + 1)
    return found


def _extract_embedded_json(html: str) -> list:
    """Return parsed JSON blobs from __NEXT_DATA__ / ld+json / __NUXT__."""
    blobs = []
    soup = BeautifulSoup(html, "lxml")
    nx = soup.find("script", id="__NEXT_DATA__")
    if nx and nx.string:
        try:
            blobs.append(json.loads(nx.string))
        except Exception:
            pass
    for s in soup.find_all("script", type="application/ld+json"):
        if s.string:
            try:
                blobs.append(json.loads(s.string))
            except Exception:
                pass
    # Nuxt / generic window.__X__ = {...};
    m = re.search(r"window\.__(?:NUXT|INITIAL_STATE)__\s*=\s*(\{.*?\});?\s*</script>",
                  html, re.DOTALL)
    if m:
        try:
            blobs.append(json.loads(m.group(1)))
        except Exception:
            pass
    return blobs


_PRICE_TOKEN = re.compile(r"\d[\d\s.,]*\s*(?:₼|AZN|man\.?|manat)", re.I)


def _digest_html(html: str, limit: int = 16000, max_ctx: int = 80) -> str:
    """Price-focused digest: keep only the text around price tokens.

    Aggregator pages are 90% navigation/category chrome that drowns the LLM and
    blows the token budget before any real listing. We strip the chrome and keep
    each price line plus a little preceding context (where the product title
    sits), so the extractor sees dense title->price pairs instead of a sitemap.
    """
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg", "header", "footer",
                   "nav", "aside"]):
        t.decompose()
    lines = [re.sub(r"\s+", " ", ln).strip()
             for ln in soup.get_text("\n", strip=True).split("\n")]
    out, seen = [], set()
    for i, ln in enumerate(lines):
        if _PRICE_TOKEN.search(ln):
            ctx = " | ".join(x for x in lines[max(0, i - 2):i + 2] if x)
            if ctx not in seen and len(ctx) > 3:
                seen.add(ctx)
                out.append(ctx)
        if len(out) >= max_ctx:
            break
    digest = "\n".join(out)
    # Fallback to plain text if the page exposes prices in an odd way.
    if len(digest) < 60:
        digest = re.sub(r"\n{2,}", "\n", soup.get_text("\n", strip=True))
    return digest[:limit]


# --------------------------------------------------------------------------
# Source registry
# --------------------------------------------------------------------------
@dataclass
class Source:
    name: str                  # domain label
    build_url: object          # query -> url
    official: bool = False     # official retailer vs marketplace/classified
    default_condition: str = "unknown"
    strategy: str = "auto"     # auto | html | json_api
    headers: dict = field(default_factory=dict)
    impersonate: bool = False  # fetch via curl_cffi (browser TLS) to clear WAFs


def _q(s: str) -> str:
    return quote_plus(s)


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s


SOURCES: list[Source] = [
    # Aggregator - per-product SEO page that lists every seller's price for one
    # product (e.g. /airpods-pro-2). The site-wide ?q= search ignores the query
    # and returns junk, so we address the product page by slug directly.
    Source("qiymetleri.az",
           lambda q: f"https://qiymetleri.az/{_slug(q)}",
           official=False, strategy="html"),
    # Official store - clean __NEXT_DATA__ product list.
    Source("bakuelectronics.az",
           lambda q: f"https://bakuelectronics.az/axtaris-neticesi?name={_q(q)}",
           official=True, strategy="auto"),
    # Marketplace (Umico front) - Nuxt SSR.
    Source("birmarket.az",
           lambda q: f"https://birmarket.az/search?q={_q(q)}",
           official=True, strategy="auto"),
    # Classifieds / used market - Next.js.
    Source("tap.az",
           lambda q: f"https://tap.az/elanlar?keywords={_q(q)}",
           official=False, default_condition="used", strategy="auto"),
    Source("irshad.az",
           lambda q: f"https://irshad.az/?s={_q(q)}",
           official=True, strategy="html"),
    # Also WAF-protected; we still attempt with impersonation and surface the
    # result honestly (often stays 403 - a JS challenge curl_cffi can't solve).
    Source("optimal.az",
           lambda q: f"https://optimal.az/search?q={_q(q)}",
           official=True, strategy="auto", impersonate=True),
]

# Sources known to be flaky right now (surfaced, never silently dropped):
#   lalafo.az - JSON API ignores the `query` filter and returns an unrelated
#   feed; rather than present garbage we mark it skipped until the correct
#   search parameter is reverse-engineered.
# Known platforms we deliberately don't query directly yet, each surfaced with a
# reason so coverage is honest and the user never wonders "why isn't X here?".
# All are reachable via a future Apify/headless "deep mode" (APIFY_API_TOKEN).
DISABLED = {
    "qiymeti.net": "WordPress ajax_search renders client-side (JS XHR, nonce-gated); "
                   "TLS impersonation gets the shell but not the prices - needs headless (TODO)",
    "umico.az / ucuzu.az": "price-aggregator SPAs, prices load via JS XHR - "
                           "need API reverse-engineering or headless (TODO)",
    "maxi.az": "Cloudflare 525 (origin down/blocked) at the edge (TODO)",
    "soliton.az / trendyol.az": "search path/JS not resolved - low priority (TODO)",
}

# Lalafo (used market) has a JSON API but needs specific headers.
LALAFO_HEADERS = {
    "Accept": "application/json", "device": "pc",
    "Country-Id": "13", "Language": "az", "User-Agent": USER_AGENT,
}


try:  # optional - browser TLS impersonation to clear anti-bot WAFs (free)
    from curl_cffi import requests as _curl
except Exception:  # pragma: no cover
    _curl = None


def _curl_get(url: str, headers: dict):
    # impersonate sets a real Chrome UA + TLS fingerprint; drop our own UA so it
    # stays self-consistent (the TLS fingerprint is what beats the WAF).
    h = {k: v for k, v in (headers or {}).items() if k.lower() != "user-agent"}
    h.setdefault("Accept-Language", "az,en;q=0.9,ru;q=0.8")
    return _curl.get(url, headers=h, impersonate="chrome", timeout=HTTP_TIMEOUT)


async def _fetch(client: httpx.AsyncClient, url: str, headers: dict | None = None,
                 impersonate: bool = False):
    hdr = headers or _HEADERS
    if impersonate and _curl is not None:
        return await asyncio.to_thread(_curl_get, url, hdr)
    try:
        r = await client.get(url, headers=hdr, timeout=HTTP_TIMEOUT, follow_redirects=True)
    except httpx.TimeoutException:
        # Heavy aggregator pages (qiymetleri/irshad) sometimes need a second try.
        r = await client.get(url, headers=hdr, timeout=HTTP_TIMEOUT, follow_redirects=True)
    # Auto-recover: a WAF 403/429 to plain httpx often yields to browser TLS.
    if r.status_code in (403, 401, 429) and _curl is not None:
        try:
            return await asyncio.to_thread(_curl_get, url, hdr)
        except Exception:  # noqa: BLE001 - fall back to the original response
            return r
    return r


async def _crawl_source(client: httpx.AsyncClient, src: Source, query: str) -> SourceResult:
    url = src.build_url(query)
    try:
        r = await _fetch(client, url, {**_HEADERS, **src.headers},
                         impersonate=src.impersonate)
    except Exception as exc:  # noqa: BLE001
        return SourceResult(src.name, f"error:{type(exc).__name__}", note=str(exc)[:120])

    if r.status_code in (403, 401, 429):
        return SourceResult(src.name, "blocked",
                            note=f"HTTP {r.status_code} (anti-bot; survived TLS impersonation)")
    if r.status_code >= 400:
        return SourceResult(src.name, f"error:http{r.status_code}")

    html = r.text
    offers: list[Offer] = []

    if src.strategy != "html":
        for blob in _extract_embedded_json(html):
            for c in harvest_products(blob, str(r.url)):
                offers.append(Offer(
                    title=c["title"], price=c["price"], url=c["url"] or str(r.url),
                    source=src.name, condition=src.default_condition,
                    official=src.official or None, in_stock=c.get("in_stock"),
                    model_code=c.get("model_code", ""),
                ))

    if offers:
        # dedupe within source by (title, price)
        seen = set()
        uniq = []
        for o in offers:
            k = (o.title.lower()[:80], o.price)
            if k not in seen:
                seen.add(k)
                uniq.append(o)
        return SourceResult(src.name, "ok", offers=uniq,
                            note=f"{len(uniq)} structured offers")

    # No structured offers -> hand a price-focused digest to the LLM extractor.
    text = _digest_html(html)
    if len(text) > 40:
        return SourceResult(src.name, "ok", needs_llm_html=text,
                            note=f"html->llm extraction ({text.count(chr(10))+1} price lines)",
                            src_official=src.official, src_condition=src.default_condition,
                            src_url=url)
    return SourceResult(src.name, "empty", note="no prices found in page")


async def _crawl_lalafo(client: httpx.AsyncClient, query: str) -> SourceResult:
    # The public feed/search applies the keyword via `q=` (NOT `query=`, which is
    # ignored and returns an unrelated feed). Reverse-engineered live.
    url = (f"https://lalafo.az/api/search/v3/feed/search?q={quote_plus(query)}"
           f"&page=1&per-page=30&expand=url")
    try:
        r = await _fetch(client, url, LALAFO_HEADERS)
        if r.status_code >= 400:
            return SourceResult("lalafo.az", f"error:http{r.status_code}")
        data = r.json()
        items = data.get("items") or data.get("data") or []
        offers = []
        for it in items:
            if not isinstance(it, dict):
                continue
            price = _to_float(it.get("price"))
            title = it.get("title") or it.get("name")
            if not (price and title):
                continue
            u = it.get("url") or it.get("mobile_url") or ""
            offers.append(Offer(
                title=str(title), price=price,
                url=u if u.startswith("http") else urljoin("https://lalafo.az", u),
                source="lalafo.az", condition="used", official=False,
                currency=str(it.get("currency") or "AZN"),
            ))
        return SourceResult("lalafo.az", "ok" if offers else "empty",
                            offers=offers, note=f"{len(offers)} API offers")
    except Exception as exc:  # noqa: BLE001
        return SourceResult("lalafo.az", f"error:{type(exc).__name__}", note=str(exc)[:120])


_KONTAKT_GQL = ('{{products(search:"{q}",pageSize:24){{total_count items{{'
                'name sku url_key stock_status '
                'price_range{{minimum_price{{final_price{{value currency}}}}}}}}}}}}')


def _kontakt_fetch(query: str):
    """kontakt.az is a Magento PWA behind a WAF: SSR search is an empty JS shell,
    but its GraphQL endpoint returns real products. curl_cffi clears the WAF."""
    from urllib.parse import quote
    url = "https://kontakt.az/graphql?query=" + quote(_KONTAKT_GQL.format(q=query))
    return _curl.get(url, impersonate="chrome",
                     headers={"Accept-Language": "az,en;q=0.9", "Store": "az"},
                     timeout=HTTP_TIMEOUT)


async def _crawl_kontakt(client: httpx.AsyncClient, query: str) -> SourceResult:
    if _curl is None:
        return SourceResult("kontakt.az", "skipped", note="curl_cffi not installed")
    try:
        r = await asyncio.to_thread(_kontakt_fetch, query)
        if r.status_code >= 400:
            return SourceResult("kontakt.az", f"error:http{r.status_code}")
        items = (((r.json() or {}).get("data") or {}).get("products") or {}).get("items") or []
        offers = []
        for it in items:
            if not isinstance(it, dict):
                continue
            fp = (((it.get("price_range") or {}).get("minimum_price") or {}).get("final_price") or {})
            price = _to_float(fp.get("value"))
            name = it.get("name")
            if not (price and name):
                continue
            key = it.get("url_key") or ""
            offers.append(Offer(
                title=str(name), price=price, currency=str(fp.get("currency") or "AZN"),
                url=f"https://kontakt.az/{key}" if key else "https://kontakt.az",
                source="kontakt.az", official=True, condition="new",
                in_stock=(str(it.get("stock_status")).upper() == "IN_STOCK") if it.get("stock_status") else None,
                model_code=str(it.get("sku") or ""),
            ))
        return SourceResult("kontakt.az", "ok" if offers else "empty",
                            offers=offers, note=f"{len(offers)} GraphQL offers (official)")
    except Exception as exc:  # noqa: BLE001
        return SourceResult("kontakt.az", f"error:{type(exc).__name__}", note=str(exc)[:120])


async def _crawl_ispace(client: httpx.AsyncClient, query: str) -> SourceResult:
    """iSpace - the official Apple partner in Azerbaijan, the trust anchor for
    'what is the genuine official price'. Nuxt SPA, but its JSON search API
    (/api/v2/search/products) takes lang+query and returns clean structured
    products. Reverse-engineered from the 422 validation error + JS bundle."""
    url = ("https://ispace.az/api/v2/search/products"
           f"?lang=az&query={quote_plus(query)}")
    try:
        r = await _fetch(client, url, {**_HEADERS, "Accept": "application/json"})
        if r.status_code >= 400:
            return SourceResult("ispace.az", f"error:http{r.status_code}")
        items = (r.json() or {}).get("data") or []
        offers = []
        for it in items:
            if not isinstance(it, dict):
                continue
            price = _to_float(it.get("final_price") or it.get("price"))
            name = it.get("name")
            if not (price and name):
                continue
            slug = it.get("slug") or ""
            offers.append(Offer(
                title=str(name), price=price,
                url=f"https://ispace.az/az/product/{slug}" if slug else "https://ispace.az",
                source="ispace.az", official=True, condition="new",
                warranty="official Apple partner",
                in_stock=bool(it.get("real_stock")) if "real_stock" in it else None,
                model_code=str(it.get("sku") or ""),
            ))
        return SourceResult("ispace.az", "ok" if offers else "empty",
                            offers=offers, note=f"{len(offers)} API offers (official Apple)")
    except Exception as exc:  # noqa: BLE001
        return SourceResult("ispace.az", f"error:{type(exc).__name__}", note=str(exc)[:120])


# JS-SPA sources only reachable by rendering real Chrome (--deep). Each yields a
# digest for the LLM extractor; flaky by nature, surfaced honestly either way.
DEEP_SOURCES = [
    {"name": "qiymeti.net", "url": lambda q: "https://qiymeti.net/",
     "type_into": "input[name=s]", "official": False, "condition": "unknown"},
    {"name": "ucuzu.az", "url": lambda q: f"https://ucuzu.az/web/search?q={_q(q)}",
     "type_into": None, "official": False, "condition": "unknown"},
    {"name": "umico.az", "url": lambda q: f"https://umico.az/search?q={quote_plus(q)}",
     "type_into": None, "official": True, "condition": "unknown"},
]


async def _crawl_deep(cfg: dict, query: str) -> SourceResult:
    """Deep render: prefer Apify (managed cloud browser) when a token is set,
    else local Playwright + system Chrome."""
    import apify_deep
    import render
    url = cfg["url"](query)
    engine = ""
    html = ""
    try:
        if apify_deep.available():
            engine = "apify"
            html = await asyncio.to_thread(apify_deep.render, url)
        if not html and render.available():
            engine = "playwright"
            html = await asyncio.to_thread(
                render.render_sync, url,
                type_into=cfg.get("type_into"),
                type_text=query if cfg.get("type_into") else None)
        if not html:
            if not (apify_deep.available() or render.available()):
                return SourceResult(cfg["name"], "skipped",
                                    note="--deep needs APIFY_API_TOKEN or playwright")
            return SourceResult(cfg["name"], "blocked",
                                note=f"{engine or 'render'} returned nothing (JS-gated)")
        text = _digest_html(html)
        if len(text) > 40:
            return SourceResult(cfg["name"], "ok", needs_llm_html=text,
                                note=f"{engine} render -> llm ({text.count(chr(10))+1} price lines)",
                                src_official=cfg["official"], src_condition=cfg["condition"],
                                src_url=url)
        return SourceResult(cfg["name"], "empty", note=f"{engine} rendered but no prices in DOM (JS gated)")
    except Exception as exc:  # noqa: BLE001
        return SourceResult(cfg["name"], f"error:{type(exc).__name__}", note=str(exc)[:120])


async def crawl_all(query: str, deep: bool = False, serp_on: bool = False,
                    social_on: bool = False) -> list[SourceResult]:
    """Fan out to every source concurrently and collect results.

    deep    - headless-render the JS-SPA sources (umico/ucuzu/qiymeti.net)
    serp_on - Google SERP catch-all (covers SPAs + unreachable .az shops)
    social_on - Instagram social-commerce sellers
    The last two are Apify-gated (cost credits), so they're opt-in.
    """
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    async with httpx.AsyncClient(http2=False) as client:
        async def guarded(coro):
            async with sem:
                return await coro
        tasks = [guarded(_crawl_source(client, s, query)) for s in SOURCES]
        tasks.append(guarded(_crawl_ispace(client, query)))    # official Apple anchor
        tasks.append(guarded(_crawl_kontakt(client, query)))   # Magento GraphQL
        tasks.append(guarded(_crawl_lalafo(client, query)))    # used market (q= param)
        results = list(await asyncio.gather(*tasks))
    # Google SERP catch-all: surfaces stores we can't reach directly (SPAs +
    # smaller shops) with prices straight from the snippet. Apify-gated, opt-in.
    if serp_on:
        try:
            import serp
            if serp.available():
                offers = await asyncio.to_thread(serp.search, query)
                results.append(SourceResult(
                    "google-serp", "ok" if offers else "empty", offers=offers,
                    note=f"{len(offers)} .az offers via Google snippets"))
            else:
                results.append(SourceResult("google-serp", "skipped",
                                            note="needs APIFY_API_TOKEN"))
        except Exception as exc:  # noqa: BLE001
            results.append(SourceResult("google-serp", f"error:{type(exc).__name__}",
                                        note=str(exc)[:100]))
    # Social-commerce (Instagram sellers - no website). Apify-gated, opt-in.
    if social_on:
        try:
            import social
            if social.available():
                offers = await asyncio.to_thread(social.search, query)
                results.append(SourceResult(
                    "instagram", "ok" if offers else "empty", offers=offers,
                    note=f"{len(offers)} Instagram seller offers"))
            else:
                results.append(SourceResult("instagram", "skipped",
                                            note="needs APIFY_API_TOKEN"))
        except Exception as exc:  # noqa: BLE001
            results.append(SourceResult("instagram", f"error:{type(exc).__name__}",
                                        note=str(exc)[:100]))
    if deep:
        # Headless renders run sequentially (one Chrome at a time) to stay light.
        for cfg in DEEP_SOURCES:
            results.append(await _crawl_deep(cfg, query))
        skipped = DISABLED
    else:
        # Not in deep mode: surface the SPA sources as available-via---deep.
        skipped = {**DISABLED,
                   "qiymeti.net / ucuzu.az / umico.az": "JS-SPA - run with --deep to render (Chrome)"}
        skipped.pop("qiymeti.net", None)
        skipped.pop("umico.az / ucuzu.az", None)
    for dom, why in skipped.items():
        results.append(SourceResult(dom, "skipped", note=why))
    return results
