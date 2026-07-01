"""The 2026 SEO checklist, codified as scored checks (Azerbaijani output).

This is the machine version of the brief review we did with the operator: every
'must' becomes a check, every 'no longer needed / needs update' note is baked
into the pass/fail logic (e.g. image weight is judged by Core Web Vitals + modern
signals, not a hard 150 kb rule; headings are judged as a semantic hierarchy,
not a font size).

Each check receives an AuditContext and returns a Finding. Weights:
    3 = kritik, 2 = vacib, 1 = kiçik.  info-level checks are not scored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

# ---- Finding model --------------------------------------------------------- #

STATUS_FACTOR = {"pass": 1.0, "warn": 0.5, "fail": 0.0}  # info/na excluded


@dataclass
class Finding:
    id: str
    category: str
    title: str            # AZ, short
    status: str           # pass | warn | fail | info | na
    weight: int
    detail: str = ""      # AZ — what we measured
    fix: str = ""         # AZ — how to fix (only when not pass)

    @property
    def icon(self) -> str:
        return {"pass": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️", "na": "➖"}[self.status]


@dataclass
class AuditContext:
    url: str
    fetched: object          # http.Fetched
    page: object             # htmlparse.PageData
    robots: object           # connectors.robots.RobotsInfo
    sitemap_ok: bool
    sitemap_url: str
    vitals: object           # connectors.pagespeed.Vitals


_INDEX = "İndeksləmə & Crawl"
_ONPAGE = "On-page"
_STRUCT = "Struktur & Naviqasiya"
_PERF = "Performans & Mobil"
_TRUST = "Etibar & AI (E-E-A-T / GEO)"


# ---- individual checks ----------------------------------------------------- #

def _https(ctx) -> Finding:
    is_https = urlparse(ctx.fetched.url).scheme == "https"
    if is_https:
        return Finding("https", _INDEX, "HTTPS / SSL", "pass", 3,
                       "Sayt təhlükəsiz https üzərindədir.")
    return Finding("https", _INDEX, "HTTPS / SSL", "fail", 3,
                   "Sayt http üzərindədir — brauzer 'təhlükəsiz deyil' göstərir.",
                   "SSL sertifikatı quraşdır və bütün http→https 301 yönləndir.")


def _status(ctx) -> Finding:
    s = ctx.fetched.status
    if s == 200:
        return Finding("status", _INDEX, "HTTP status", "pass", 3, f"Səhifə 200 OK qaytarır ({ctx.fetched.elapsed_ms} ms).")
    return Finding("status", _INDEX, "HTTP status", "fail", 3,
                   f"Səhifə {s or 'xəta'} qaytarır.",
                   "2xx status təmin et; qırıq/yönləndirmə zəncirlərini düzəlt.")


def _indexable(ctx) -> Finding:
    mr = ctx.page.meta_robots
    if "noindex" in mr:
        return Finding("indexable", _INDEX, "İndekslənə bilən", "fail", 3,
                       "Səhifədə meta robots=noindex var — Google indeksləmir.",
                       "Bu səhifə axtarışda görünməlidirsə, noindex-i çıxart.")
    if ctx.robots.disallow_all:
        return Finding("indexable", _INDEX, "İndekslənə bilən", "fail", 3,
                       "robots.txt bütün saytı botlara bağlayır (Disallow: /).",
                       "robots.txt-də '*' üçün Disallow: / qaydasını yumşalt.")
    return Finding("indexable", _INDEX, "İndekslənə bilən", "pass", 3, "İndeksləməyə mane olan qayda yoxdur.")


def _title(ctx) -> Finding:
    t = ctx.page.title.strip()
    n = len(t)
    if not t:
        return Finding("title", _ONPAGE, "Meta title", "fail", 3, "Title yoxdur.",
                       "Hər səhifəyə unikal, açar-sözlü title yaz (~50-60 simvol).")
    if 15 <= n <= 65:
        return Finding("title", _ONPAGE, "Meta title", "pass", 3, f"Title var ({n} simvol): “{t[:70]}”.")
    return Finding("title", _ONPAGE, "Meta title", "warn", 3,
                   f"Title uzunluğu ideal deyil ({n} simvol): “{t[:70]}”.",
                   "Title-ı ~50-60 simvola gətir; qısa isə açar söz + brend əlavə et.")


def _description(ctx) -> Finding:
    d = ctx.page.meta_description.strip()
    n = len(d)
    if not d:
        return Finding("description", _ONPAGE, "Meta description", "fail", 2, "Meta description yoxdur.",
                       "50-160 simvol cəlbedici təsvir yaz. (Qeyd: Google bəzən öz yenidən yazır, yenə də lazımdır.)")
    if 50 <= n <= 165:
        return Finding("description", _ONPAGE, "Meta description", "pass", 2, f"Description var ({n} simvol).")
    return Finding("description", _ONPAGE, "Meta description", "warn", 2,
                   f"Description uzunluğu ideal deyil ({n} simvol).",
                   "~50-160 simvola gətir.")


def _h1(ctx) -> Finding:
    h1s = ctx.page.h1
    if len(h1s) == 1:
        return Finding("h1", _ONPAGE, "H1 başlıq", "pass", 2, f"Tək H1 var: “{h1s[0][:70]}”.")
    if len(h1s) == 0:
        return Finding("h1", _ONPAGE, "H1 başlıq", "fail", 2, "H1 yoxdur.",
                       "Səhifənin əsas mövzusunu göstərən 1 ədəd H1 əlavə et.")
    return Finding("h1", _ONPAGE, "H1 başlıq", "warn", 2, f"{len(h1s)} ədəd H1 var (bir dənə olmalıdır).",
                   "Yalnız 1 H1 saxla; qalanlarını H2/H3 et.")


def _headings(ctx) -> Finding:
    hs = ctx.page.headings
    if not hs:
        return Finding("headings", _STRUCT, "Başlıq iyerarxiyası", "warn", 1, "Heç bir H1-H6 tapılmadı.",
                       "Məzmunu semantik başlıqlarla (H1→H2→H3) strukturlaşdır — AI axtarış da bunu oxuyur.")
    levels = [lvl for lvl, _ in hs]
    jumps = any(b - a > 1 for a, b in zip(levels, levels[1:]))
    if levels[0] == 1 and not jumps:
        return Finding("headings", _STRUCT, "Başlıq iyerarxiyası", "pass", 1,
                       f"Səliqəli iyerarxiya ({len(hs)} başlıq).")
    return Finding("headings", _STRUCT, "Başlıq iyerarxiyası", "warn", 1,
                   "Başlıq ardıcıllığında sıçrayış var (məs. H1→H3).",
                   "Səviyyələri ardıcıl saxla: H1→H2→H3, addım atlamadan.")


def _canonical(ctx) -> Finding:
    if ctx.page.canonical:
        return Finding("canonical", _INDEX, "Canonical tag", "pass", 2, f"Canonical var: {ctx.page.canonical[:80]}")
    return Finding("canonical", _INDEX, "Canonical tag", "warn", 2, "Canonical tag yoxdur.",
                   "Dublikat məzmun riskinə qarşı hər səhifəyə rel=canonical əlavə et.")


def _viewport(ctx) -> Finding:
    if ctx.page.viewport:
        return Finding("viewport", _PERF, "Mobil viewport", "pass", 3, "Responsive viewport meta var.")
    return Finding("viewport", _PERF, "Mobil viewport", "fail", 3, "viewport meta yoxdur — mobil versiya problemli.",
                   "<meta name=viewport content='width=device-width, initial-scale=1'> əlavə et. Google mobile-first indeksləyir.")


def _html_lang(ctx) -> Finding:
    if ctx.page.html_lang:
        return Finding("lang", _ONPAGE, "Dil (html lang)", "pass", 1, f"lang=\"{ctx.page.html_lang}\".")
    return Finding("lang", _ONPAGE, "Dil (html lang)", "warn", 1, "<html lang> təyin edilməyib.",
                   "<html lang=\"az\"> təyin et (çoxdilli saytda hər versiyaya uyğun).")


def _img_alt(ctx) -> Finding:
    total, miss = ctx.page.img_total, ctx.page.img_missing_alt
    if total == 0:
        return Finding("img_alt", _ONPAGE, "Şəkil alt-mətnləri", "na", 1, "Səhifədə şəkil yoxdur.")
    ratio = miss / total
    if miss == 0:
        return Finding("img_alt", _ONPAGE, "Şəkil alt-mətnləri", "pass", 2, f"Bütün {total} şəkildə alt var.")
    st = "warn" if ratio <= 0.2 else "fail"
    return Finding("img_alt", _ONPAGE, "Şəkil alt-mətnləri", st, 2,
                   f"{total} şəkildən {miss}-ində alt yoxdur.",
                   "Hər məzmun şəklinə təsviredici alt-mətn yaz (SEO + əlçatanlıq).")


def _structured_data(ctx) -> Finding:
    types = ctx.page.jsonld_types
    if types:
        return Finding("schema", _TRUST, "Strukturlaşdırılmış data (Schema.org)", "pass", 2,
                       "JSON-LD var: " + ", ".join(types[:8]))
    return Finding("schema", _TRUST, "Strukturlaşdırılmış data (Schema.org)", "fail", 2,
                   "JSON-LD strukturlaşdırılmış data tapılmadı.",
                   "Organization, WebSite, Article, BreadcrumbList, FAQ schema (JSON-LD) əlavə et — rich result + AI Overviews üçün 2026-nın ən vacib boşluğu.")


def _robots_txt(ctx) -> Finding:
    if ctx.robots.exists:
        return Finding("robots_txt", _INDEX, "robots.txt", "pass", 2,
                       f"robots.txt var ({len(ctx.robots.sitemaps)} sitemap bildirilib).")
    return Finding("robots_txt", _INDEX, "robots.txt", "warn", 2, "robots.txt tapılmadı.",
                   "/robots.txt əlavə et və içində Sitemap: sətri göstər.")


def _sitemap(ctx) -> Finding:
    if ctx.sitemap_ok:
        return Finding("sitemap", _INDEX, "XML sitemap", "pass", 2, f"Sitemap əlçatandır: {ctx.sitemap_url[:80]}")
    return Finding("sitemap", _INDEX, "XML sitemap", "fail", 2, "XML sitemap tapılmadı.",
                   "XML sitemap yarat, robots.txt-də göstər və Search Console-a təqdim et.")


def _url_clean(ctx) -> Finding:
    p = urlparse(ctx.fetched.url)
    path = p.path
    issues = []
    if any(c.isupper() for c in path):
        issues.append("böyük hərf")
    if "_" in path:
        issues.append("alt-xətt (_)")
    if " " in path or "%20" in path:
        issues.append("boşluq")
    if p.query.count("&") >= 3:
        issues.append("çox parametr")
    if not issues:
        return Finding("url", _STRUCT, "Təmiz URL strukturu", "pass", 1, f"Təmiz URL: {path or '/'}")
    return Finding("url", _STRUCT, "Təmiz URL strukturu", "warn", 1,
                   "URL-də problem: " + ", ".join(issues),
                   "Kiçik hərf, defis (-) ilə söz ayırıcı, qısa təsviredici URL istifadə et.")


def _core_web_vitals(ctx) -> Finding:
    v = ctx.vitals
    if not v.available:
        return Finding("cwv", _PERF, "Core Web Vitals", "na", 3,
                       "PageSpeed məlumatı əlçatmaz oldu (ƏLÇATMAZ).")
    verdict = v.verdict()
    parts = []
    if v.lcp_ms is not None:
        parts.append(f"LCP {v.lcp_ms/1000:.1f}s")
    if v.inp_ms is not None:
        parts.append(f"INP {int(v.inp_ms)}ms")
    if v.cls is not None:
        parts.append(f"CLS {v.cls}")
    if v.performance is not None:
        parts.append(f"score {v.performance}/100")
    detail = f"{'field (real user)' if v.field_data else 'lab'}: " + ", ".join(parts)
    if verdict == "good":
        return Finding("cwv", _PERF, "Core Web Vitals", "pass", 3, detail)
    return Finding("cwv", _PERF, "Core Web Vitals", "fail", 3,
                   detail + f" — zəif: {verdict.split(':')[-1]}",
                   "LCP<2.5s, INP<200ms, CLS<0.1 hədəflə: şəkilləri WebP/AVIF-ə keç, lazy-load, JS/serveri optimallaşdır.")


def _favicon(ctx) -> Finding:
    if ctx.page.favicon:
        return Finding("favicon", _STRUCT, "Favicon", "pass", 1, "Favicon var.")
    return Finding("favicon", _STRUCT, "Favicon", "warn", 1, "Favicon link tapılmadı.",
                   "Favicon əlavə et — axtarış nəticəsində brend tanınması üçün.")


def _content_depth(ctx) -> Finding:
    w = ctx.page.text_words
    if w >= 300:
        return Finding("content", _ONPAGE, "Məzmun dərinliyi", "pass", 1, f"~{w} söz.")
    return Finding("content", _ONPAGE, "Məzmun dərinliyi", "warn", 1,
                   f"Az məzmun (~{w} söz) — 'thin content' riski.",
                   "Əsas səhifələrdə istifadəçi niyyətini tam ödəyən dərin məzmun yaz.")


def _og(ctx) -> Finding:
    og = ctx.page.og
    has_title = any(k in og for k in ("og:title", "twitter:title"))
    has_img = any(k in og for k in ("og:image", "twitter:image"))
    if has_title and has_img:
        return Finding("og", _STRUCT, "Sosial paylaşım (Open Graph)", "pass", 1, "og:title + og:image var.")
    return Finding("og", _STRUCT, "Sosial paylaşım (Open Graph)", "warn", 1,
                   "Open Graph tam deyil (og:title/og:image).",
                   "og:title, og:description, og:image əlavə et — sosial paylaşımda düzgün önizləmə üçün.")


def _ai_governance(ctx) -> Finding:
    bots = ctx.robots.ai_bots_mentioned
    if bots:
        return Finding("ai_bots", _TRUST, "AI bot idarəsi (GEO)", "info", 0,
                       "robots.txt AI botlarını idarə edir: " + ", ".join(bots))
    return Finding("ai_bots", _TRUST, "AI bot idarəsi (GEO)", "info", 0,
                   "robots.txt AI/LLM botları (GPTBot, ClaudeBot, PerplexityBot...) barədə qayda saxlamır.",
                   "2026-da qərar ver: AI botlarına icazə (görünürlük) yoxsa qadağa (məzmun qorunması).")


def _hreflang(ctx) -> Finding:
    if ctx.page.hreflang:
        return Finding("hreflang", _STRUCT, "hreflang (çoxdilli)", "info", 0,
                       "hreflang var: " + ", ".join(sorted(set(ctx.page.hreflang))[:8]))
    return Finding("hreflang", _STRUCT, "hreflang (çoxdilli)", "info", 0,
                   "hreflang tapılmadı.",
                   "Sayt çoxdillidirsə (AZ/RU/EN), hər dil versiyası üçün hreflang əlavə et.")


# ---- registry (order = report order) --------------------------------------- #

CHECKS: list[Callable[[AuditContext], Finding]] = [
    _https, _status, _indexable,
    _title, _description, _h1, _headings, _html_lang, _content_depth, _img_alt,
    _canonical, _robots_txt, _sitemap, _url_clean,
    _viewport, _core_web_vitals,
    _structured_data, _og, _favicon, _hreflang, _ai_governance,
]


def run_all(ctx: AuditContext) -> list[Finding]:
    out: list[Finding] = []
    for chk in CHECKS:
        try:
            out.append(chk(ctx))
        except Exception as e:  # noqa: BLE001 — one bad check never sinks the audit
            out.append(Finding(chk.__name__.strip("_"), _INDEX, chk.__name__, "na", 0,
                               f"yoxlama xətası: {str(e)[:80]}"))
    return out


def score(findings: list[Finding]) -> tuple[int, str]:
    """Weighted 0-100 score + letter grade. info/na excluded."""
    num = den = 0.0
    for f in findings:
        if f.status in STATUS_FACTOR and f.weight > 0:
            den += f.weight
            num += f.weight * STATUS_FACTOR[f.status]
    pct = round(100 * num / den) if den else 0
    grade = ("A" if pct >= 90 else "B" if pct >= 80 else "C" if pct >= 70
             else "D" if pct >= 55 else "F")
    return pct, grade
