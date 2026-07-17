"""Brand Dossier — weekly brand + competitor intelligence for Xalq Sigorta.

Follows the gateway/radar.py pattern: free/keyless mechanical collection first,
LLM judgement only where synthesis is needed, every unreachable source surfaced
honestly (no silent drops), Azerbaijani user-facing output.

Pipeline (live run):
  1. Public page signals  — plain HTTPS GET of insurer sites (no login walls,
     no Instagram scraping). Failures land in the ƏLÇATMAZ list, never hidden.
  2. Grounded research    — direct REST call to Gemini generateContent with
     tools:[{"google_search":{}}] (llm_router has no tool/grounding support).
     The key comes from env (GEMINI_API_KEY / GOOGLE_API_KEY), is sent only in
     the x-goog-api-key header and is never printed or logged.
  3. Opportunity angles   — synthesis is a judgement task, so it runs on the
     smart tier of llm_router (Claude-subscription-first, free floor after),
     exactly like radar.digest().

Hard rule (standing project rule "no fabricated data"): nothing is invented.
Every fact carries a source + date; anything not found is marked ƏLÇATMAZ.
Dry-run output is labeled DEMO throughout, never CANLI.

Outputs (output/brand-dossier/):
  dossier_YYYY-MM-DD.md   — full Azerbaijani dossier (primary, human)
  dossier_latest.json     — structured export with a STABLE schema (primary,
                            machine): brand_position, competitor_moves[],
                            market_news[], opportunity_angles[], generated_at,
                            sources[]. Contract documented in
                            docs/BRAND_DOSSIER.md — future consumers (e.g. a
                            FastAPI brand-intelligence panel) read this file.
  canvas_paste.txt        — secondary compact summary block (<= 2500 chars),
                            handy wherever a short paste is needed

Usage:
    python scripts/brand_dossier.py --run        # live (Gemini grounding + web)
    python scripts/brand_dossier.py --dry-run    # offline demo fixtures, no network

This is a weekly JOB, not a service: no port, no services.json entry, no
schedule. Governance entry: config/agent_permissions.json -> brand_dossier.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html as _html
import json
import os
import re as _re
import sys
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_OUT_DIR = _ROOT / "output" / "brand-dossier"
_UA = {"User-Agent": "Mozilla/5.0 (ramin-os-brand-dossier/1.0)"}
_SITE_TIMEOUT = 15
_GEMINI_TIMEOUT = 90  # grounded search calls are slower than plain completions
_GEMINI_MODEL = os.getenv("BRAND_DOSSIER_GEMINI_MODEL") or "gemini-2.5-flash"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
_CANVAS_LIMIT = 2500

BRAND = "Xalq Sığorta"
COMPETITORS = ["Paşa Sığorta", "Atəşgah Sığorta", "Meqa Sığorta", "A-Qroup Sığorta"]

# Optional secondary signals: public insurer pages, fetched with a plain GET.
# Login-walled sources are out of scope by design (see agent_permissions.json).
_PUBLIC_PAGES = [
    # (section key, source name, url)
    ("brand", "xalqsigorta.az", "https://www.xalqsigorta.az/"),
    ("competitors", "pashainsurance.az", "https://www.pashainsurance.az/"),
    ("competitors", "atesgah.com", "https://www.atesgah.com/"),
    ("competitors", "mega.az", "https://mega.az/"),
    ("competitors", "a-group.az", "https://a-group.az/"),
]

# Shared anti-fabrication contract for every grounded query. The tests assert
# this text keeps forbidding invention and keeps the ƏLÇATMAZ escape hatch.
_GROUND_RULES = (
    "QAYDALAR (mütləq):\n"
    "- Yalnız axtarışda REAL tapdığın məlumatdan yaz; fakt, rəqəm, ad, tarix UYDURMA.\n"
    "- Hər bullet '- ' ilə başlasın və sonunda mənbə + tarix daşısın: "
    "(mənbə: <sayt/qurum>, <YYYY-MM-DD və ya 'tarix göstərilməyib'>).\n"
    "- Tapılmayan və ya təsdiqlənməyən məlumatı açıq şəkildə 'ƏLÇATMAZ' yaz — "
    "boşluğu təxminlə doldurma.\n"
    "- Maksimum 6 bullet, hər biri 1-2 cümlə. Dil: Azərbaycan dili."
)

_SECTION_SPECS = [
    {
        "key": "brand",
        "title": "BREND MÖVQEYİ",
        "query": (
            "Xalq Sığorta (xalqsigorta.az, Azərbaycan sığorta şirkəti) haqqında son "
            "30-45 günün GÖRÜNƏN mənzərəsi: xəbərlər, kampaniyalar, yeni məhsullar, "
            "rəqəmsal xidmətlər, sosial media / PR aktivliyi, reytinq və bazar payı "
            "açıqlamaları."
        ),
    },
    {
        "key": "competitors",
        "title": "RƏQİB HƏRƏKƏTLƏRİ",
        "query": (
            "Azərbaycan sığorta bazarında rəqiblərin son 30-45 gündəki hərəkətləri: "
            "Paşa Sığorta, Atəşgah Sığorta, Meqa Sığorta, A-Qroup Sığorta və digər "
            "AZ sığortaçılar. Yeni kampaniya, məhsul, tərəfdaşlıq, rəqəmsal xidmət, "
            "qiymət aksiyası."
        ),
    },
    {
        "key": "market",
        "title": "BAZAR YENİLİKLƏRİ",
        "query": (
            "Azərbaycan sığorta bazarı və tənzimləmə xəbərləri (son 30-45 gün): "
            "Mərkəzi Bank (AMB) qərarları və statistikası, İcbari Sığorta Bürosu, "
            "qanunvericilik dəyişiklikləri, bazar həcmi və seqment dinamikası."
        ),
    },
]

_OPPORTUNITY_TITLE = "FÜRSƏT BUCAQLARI"

_OPPORTUNITY_SYSTEM = (
    "Sən Xalq Sığortanın brend strateqisən. Aşağıda bu həftənin brend, rəqib və "
    "bazar siqnalları var. İşin: 3-5 FÜRSƏT BUCAĞI çıxar — rəqiblərin danışmadığı, "
    "Xalq Sığortanın sahiblənə biləcəyi bucaqlar. Hər bucaq üçün '- ' bullet yaz: "
    "bucağın adı + 1 cümlə əsaslandırma + hansı siqnala söykəndiyi (mötərizədə "
    "bölmə adı). QAYDALAR: yalnız verilən siqnallara əsaslan, fakt və rəqəm uydurma; "
    "siqnal azdırsa daha az bucaq yaz və bunu açıq de. Dil: Azərbaycan dili, "
    "konkret və sakit ton."
)

# ---------------------------------------------------------------------------
# Dry-run fixtures. Clearly synthetic: every line is tagged [DEMO] (or marked
# ƏLÇATMAZ) and the whole section carries status DEMO — never CANLI.
# ---------------------------------------------------------------------------

_DEMO_SECTIONS = {
    "brand": {
        "body": (
            "- [DEMO] Xalq Sığorta KASKO Bayram kampaniyasını saytında elan edib "
            "(mənbə: xalqsigorta.az, 2026-07-08)\n"
            "- [DEMO] İcbari sığorta üzrə onlayn ödəniş axını yenilənib "
            "(mənbə: xalqsigorta.az, 2026-07-05)\n"
            "- ƏLÇATMAZ: Instagram izləyici dinamikası (login tələb edir, skan edilmir)"
        ),
        "sources": [
            {"title": "xalqsigorta.az — DEMO fixture", "url": "https://www.xalqsigorta.az/", "date": "2026-07-08"},
        ],
    },
    "competitors": {
        "body": (
            "- [DEMO] Paşa Sığorta yay səyahət sığortası kampaniyası aparır "
            "(mənbə: pashainsurance.az, 2026-07-06)\n"
            "- [DEMO] Atəşgah Sığorta mobil tətbiqinə KASKO kalkulyatoru əlavə edib "
            "(mənbə: atesgah.com, 2026-07-03)\n"
            "- [DEMO] Meqa Sığorta korporativ tibbi sığorta paketini yeniləyib "
            "(mənbə: mega.az, 2026-07-01)\n"
            "- ƏLÇATMAZ: A-Qroup Sığortanın son kampaniya məlumatı tapılmadı"
        ),
        "sources": [
            {"title": "pashainsurance.az — DEMO fixture", "url": "https://www.pashainsurance.az/", "date": "2026-07-06"},
            {"title": "atesgah.com — DEMO fixture", "url": "https://www.atesgah.com/", "date": "2026-07-03"},
        ],
    },
    "market": {
        "body": (
            "- [DEMO] Mərkəzi Bank sığorta sektorunun yarımillik statistikasını açıqlayıb "
            "(mənbə: cbar.az, 2026-07-04)\n"
            "- [DEMO] İcbari Sığorta Bürosu yaşıl kart tarifləri üzrə yenilik dərc edib "
            "(mənbə: isb.az, 2026-06-28)"
        ),
        "sources": [
            {"title": "cbar.az — DEMO fixture", "url": "https://www.cbar.az/", "date": "2026-07-04"},
        ],
    },
    "opportunities": {
        "body": (
            "- [DEMO] Sadə dildə sığorta: rəqiblər şərtləri texniki dildə verir — "
            "'izahlı sığorta' seriyası boş bucaqdır (siqnal: RƏQİB HƏRƏKƏTLƏRİ)\n"
            "- [DEMO] Onlayn ödəniş rahatlığı: yenilənən axını real müştəri "
            "hekayələri ilə göstərmək (siqnal: BREND MÖVQEYİ)\n"
            "- [DEMO] Statistika günü: AMB rəqəmlərini müştəri dilində infoqrafikaya "
            "çevirmək (siqnal: BAZAR YENİLİKLƏRİ)"
        ),
        "sources": [],
    },
}


# ---------------------------------------------------------------------------
# Collection helpers (mechanical — no LLM spend here except the grounded call
# itself, which IS the research organ).
# ---------------------------------------------------------------------------

def _fetch_site(name: str, url: str) -> dict:
    """Fetch a public page and return a plain-text excerpt. Raises on failure."""
    r = requests.get(url, headers=_UA, timeout=_SITE_TIMEOUT)
    r.raise_for_status()
    text = _re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text)
    text = _re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(_re.sub(r"\s+", " ", text)).strip()
    return {"name": name, "url": url, "excerpt": text[:600]}


def _collect_site_signals() -> tuple[dict, list[str]]:
    """Best-effort public page sweep. Returns ({section: [signal]}, failures)."""
    signals: dict[str, list[dict]] = {}
    failures: list[str] = []
    for section_key, name, url in _PUBLIC_PAGES:
        try:
            signals.setdefault(section_key, []).append(_fetch_site(name, url))
        except Exception as exc:  # noqa: BLE001 — one dead site never stops the dossier
            failures.append("%s: %s" % (name, str(exc)[:80]))
    return signals, failures


def _gemini_grounded(prompt: str) -> tuple[str, list[dict]]:
    """Direct generateContent call with google_search grounding.

    Returns (text, sources). The API key travels only in the x-goog-api-key
    header — never in the URL, never printed, never logged.
    """
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY not set")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        # gemini-2.5 spends "thinking" tokens from the SAME output budget — with
        # 1024 the visible answer was truncated mid-sentence. Thinking is disabled
        # (this is extraction, not reasoning) and the budget is raised.
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    r = requests.post(
        _GEMINI_URL % _GEMINI_MODEL,
        json=body,
        headers={**_UA, "Content-Type": "application/json", "x-goog-api-key": key},
        timeout=_GEMINI_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    cand = (data.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
    if not text:
        raise RuntimeError("empty grounded response")
    # A truncated section must NOT be published as fact — better an honest
    # ƏLÇATMAZ than a sentence cut mid-air that poisons the synthesis step.
    if cand.get("finishReason") == "MAX_TOKENS":
        raise RuntimeError("grounded response truncated (MAX_TOKENS)")
    sources = []
    for chunk in (cand.get("groundingMetadata") or {}).get("groundingChunks") or []:
        web = chunk.get("web") or {}
        if web.get("uri"):
            sources.append({"title": web.get("title") or web["uri"], "url": web["uri"]})
    return text, sources


def _build_prompt(spec: dict, site_notes: list[dict], today: str) -> str:
    prompt = "Bu günün tarixi: %s.\n\n%s" % (today, spec["query"])
    if site_notes:
        notes = "\n".join("— %s: %s" % (s["name"], s["excerpt"]) for s in site_notes)
        prompt += "\n\nƏlavə kontekst — rəsmi saytlardan bu gün çəkilmiş çıxarışlar:\n" + notes
    return prompt + "\n\n" + _GROUND_RULES


def _synthesize_opportunities(sections: list[dict]) -> tuple[str, str]:
    """Opportunity angles are a judgement call -> smart tier (radar pattern)."""
    import llm_router

    payload = "\n\n".join(
        "## %s [%s]\n%s" % (s["title"], s["status"], s["body"]) for s in sections
    )
    text, model = llm_router.complete(
        payload, system=_OPPORTUNITY_SYSTEM, tier="smart",
        temperature=0.3, max_tokens=600,
    )
    return text.strip(), model


# ---------------------------------------------------------------------------
# Collect (live and demo)
# ---------------------------------------------------------------------------

def collect() -> tuple[list[dict], list[str], str]:
    """Live collection. Returns (sections, failures, digest_model)."""
    today = _dt.date.today().isoformat()
    site_signals, failures = _collect_site_signals()

    sections: list[dict] = []
    for spec in _SECTION_SPECS:
        notes = site_signals.get(spec["key"]) or []
        try:
            body, sources = _gemini_grounded(_build_prompt(spec, notes, today))
            status = "CANLI"
        except Exception as exc:  # noqa: BLE001 — a dead section is reported, not hidden
            failures.append("%s (grounded axtarış): %s" % (spec["key"], str(exc)[:80]))
            body = "- ƏLÇATMAZ: bu bölmə üçün canlı mənbə sorğusu alınmadı."
            sources, status = [], "ƏLÇATMAZ"
        for src in sources:
            src.setdefault("date", today)
        for s in notes:
            sources.append({"title": "%s (rəsmi sayt)" % s["name"], "url": s["url"], "date": today})
        sections.append({"key": spec["key"], "title": spec["title"],
                         "status": status, "body": body, "sources": sources})

    try:
        opp_body, digest_model = _synthesize_opportunities(sections)
        opp_status = "CANLI"
    except Exception as exc:  # noqa: BLE001
        failures.append("opportunities (sintez): %s" % str(exc)[:80])
        opp_body = "- ƏLÇATMAZ: sintez modeli əlçatmaz oldu, fürsət bucaqları çıxarılmadı."
        digest_model, opp_status = "", "ƏLÇATMAZ"
    sections.append({"key": "opportunities", "title": _OPPORTUNITY_TITLE,
                     "status": opp_status, "body": opp_body, "sources": []})
    return sections, failures, digest_model


def collect_demo() -> tuple[list[dict], list[str], str]:
    """Offline collection from bundled fixtures. No network, labeled DEMO."""
    sections = []
    for spec in _SECTION_SPECS + [{"key": "opportunities", "title": _OPPORTUNITY_TITLE}]:
        fix = _DEMO_SECTIONS[spec["key"]]
        sections.append({"key": spec["key"], "title": spec["title"], "status": "DEMO",
                         "body": fix["body"], "sources": list(fix["sources"])})
    return sections, [], "demo-fixtures"


# ---------------------------------------------------------------------------
# Renderers (pure functions — this is what the offline tests exercise)
# ---------------------------------------------------------------------------

_MODE_LABEL = {"live": "CANLI (Gemini google_search grounding)",
               "dry-run": "DEMO (oflayn fixture, şəbəkə istifadə olunmayıb)"}


def build_markdown(dossier: dict) -> str:
    lines = [
        "# Brend Dosyesi — %s" % dossier["brand"],
        "",
        "**Tarix:** %s · **Rejim:** %s" % (dossier["generated"], _MODE_LABEL[dossier["mode"]]),
        "**Rəqib radarı:** %s" % ", ".join(dossier["competitors"]),
        "**Həzm modeli:** %s" % (dossier.get("digest_model") or "ƏLÇATMAZ"),
        "",
        "> Qayda: heç bir fakt uydurulmur. Hər fakt mənbə + tarix daşıyır;",
        "> tapılmayan məlumat ƏLÇATMAZ kimi işarələnir.",
    ]
    for i, sec in enumerate(dossier["sections"], 1):
        lines += ["", "## %d. %s — [%s]" % (i, sec["title"], sec["status"]), "", sec["body"].strip()]
        if sec["sources"]:
            lines += ["", "**Mənbələr (baxılıb: %s):**" % dossier["generated"]]
            lines += ["- %s — %s (%s)" % (s["title"], s["url"], s.get("date", "tarix göstərilməyib"))
                      for s in sec["sources"]]
    if dossier["failures"]:
        lines += ["", "## ƏLÇATMAZ mənbələr", ""]
        lines += ["- %s" % f for f in dossier["failures"]]
    lines += ["", "---", "",
              "_Yaradıldı: scripts/brand_dossier.py · Kompakt versiya: canvas_paste.txt_"]
    return "\n".join(lines) + "\n"


def _compact_body(body: str, max_lines: int = 5, max_line: int = 230) -> str:
    """Keep the first bullets of a section, each trimmed to a sane length."""
    kept = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) > max_line:
            line = line[: max_line - 1].rstrip() + "…"
        kept.append(line)
        if len(kept) >= max_lines:
            break
    return "\n".join(kept)


def build_canvas_paste(dossier: dict, limit: int = _CANVAS_LIMIT) -> str:
    """Compact Azerbaijani block for the Canvas app field. ALWAYS <= limit chars."""
    mode_tag = "CANLI" if dossier["mode"] == "live" else "DEMO"
    header = "BREND DOSYESİ — %s · %s · rejim: %s" % (
        dossier["brand"], dossier["generated"], mode_tag)
    blocks = [("== %s == [%s]" % (sec["title"], sec["status"]), _compact_body(sec["body"]))
              for sec in dossier["sections"]]

    def render(bodies: list[str]) -> str:
        parts = [header]
        for (title, _), body in zip(blocks, bodies):
            parts.append("")
            parts.append(title)
            if body:
                parts.append(body)
        return "\n".join(parts)

    bodies = [b for _, b in blocks]
    text = render(bodies)
    while len(text) > limit:
        i = max(range(len(bodies)), key=lambda j: len(bodies[j]))
        if len(bodies[i]) <= 40:  # nothing meaningful left to shave
            break
        cut = min(int(len(bodies[i]) * 0.85), len(bodies[i]) - 20)
        bodies[i] = bodies[i][:cut].rstrip() + "…"
        text = render(bodies)
    return text[:limit]  # hard guarantee, whatever the input looked like


# ---------------------------------------------------------------------------
# Structured export — the stable machine contract (docs/BRAND_DOSSIER.md).
# Internal pipeline stays section-based; this maps it to consumer field names.
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

# internal section key -> exported field name
_EXPORT_FIELDS = {
    "brand": "brand_position",
    "competitors": "competitor_moves",
    "market": "market_news",
    "opportunities": "opportunity_angles",
}

_SOURCE_RE = _re.compile(r"\(mənbə:\s*([^,)]+?)\s*,\s*([^)]+?)\s*\)")
_DATE_RE = _re.compile(r"\d{4}-\d{2}-\d{2}")


def _parse_items(body: str, label: str) -> list[dict]:
    """Split a section body into fact items, extracting per-fact source + date
    from the '(mənbə: <name>, <date>)' convention the prompts enforce."""
    items = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        text = line[2:].strip()
        m = _SOURCE_RE.search(text)
        source = m.group(1).strip() if m else None
        date = None
        if m:
            d = _DATE_RE.search(m.group(2))
            date = d.group(0) if d else m.group(2).strip()
        items.append({"text": text, "source": source, "date": date, "label": label})
    return items


def build_export(dossier: dict) -> dict:
    """Map the internal dossier to the stable consumer schema (v1)."""
    export: dict = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dossier["generated_at"],
        "mode": dossier["mode"],
        "brand": dossier["brand"],
        "competitors": dossier["competitors"],
        "models": {"grounded": dossier["grounded_model"],
                   "digest": dossier["digest_model"]},
        "section_status": {},
        "sources": [],
        "failures": dossier["failures"],
    }
    seen_urls: set[str] = set()
    for sec in dossier["sections"]:
        field = _EXPORT_FIELDS[sec["key"]]
        items = _parse_items(sec["body"], sec["status"])
        export["section_status"][field] = sec["status"]
        if field == "brand_position":
            export[field] = {"status": sec["status"], "items": items,
                             "summary": sec["body"].strip()}
        else:
            export[field] = items
        for src in sec["sources"]:
            if src["url"] not in seen_urls:
                seen_urls.add(src["url"])
                export["sources"].append({**src, "section": field})
    return export


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _bootstrap_env() -> None:
    try:
        from gateway._bootstrap import load_env
        load_env()
    except Exception:  # noqa: BLE001 — env may already be set by the shell
        pass


def run(dry_run: bool = False, out_dir: Path | None = None) -> dict:
    """Build the dossier and write all three outputs. Returns a summary dict."""
    if dry_run:
        sections, failures, digest_model = collect_demo()
        mode = "dry-run"
    else:
        _bootstrap_env()
        sections, failures, digest_model = collect()
        mode = "live"

    now = _dt.datetime.now(_dt.timezone.utc)
    dossier = {
        "generated": now.date().isoformat(),
        "generated_at": now.isoformat(timespec="seconds"),
        "mode": mode,
        "brand": BRAND,
        "competitors": COMPETITORS,
        "grounded_model": _GEMINI_MODEL if mode == "live" else "demo-fixtures",
        "digest_model": digest_model,
        "sections": sections,
        "failures": failures,
    }

    out = Path(out_dir) if out_dir else _OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    canvas = build_canvas_paste(dossier)
    md_path = out / ("dossier_%s.md" % dossier["generated"])
    md_path.write_text(build_markdown(dossier), encoding="utf-8")
    json_path = out / "dossier_latest.json"
    json_path.write_text(
        json.dumps(build_export(dossier), ensure_ascii=False, indent=2), encoding="utf-8")
    canvas_path = out / "canvas_paste.txt"
    canvas_path.write_text(canvas, encoding="utf-8")

    return {
        "generated": dossier["generated"],
        "mode": mode,
        "paths": {"markdown": str(md_path), "json": str(json_path), "canvas": str(canvas_path)},
        "canvas_chars": len(canvas),
        "sections": [(s["title"], s["status"]) for s in sections],
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(
        description="Brand Dossier — weekly Xalq Sigorta brand + competitor intelligence.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true",
                       help="live run: Gemini google_search grounding + public pages")
    group.add_argument("--dry-run", action="store_true",
                       help="offline run on bundled DEMO fixtures (no network)")
    ap.add_argument("--out", default=None,
                    help="override output directory (default: output/brand-dossier)")
    args = ap.parse_args(argv)

    summary = run(dry_run=args.dry_run, out_dir=Path(args.out) if args.out else None)

    print("Brend Dosyesi hazırdır (%s · rejim: %s)" % (summary["generated"], summary["mode"]))
    for title, status in summary["sections"]:
        print("  %-20s [%s]" % (title, status))
    if summary["failures"]:
        print("ƏLÇATMAZ mənbələr:")
        for f in summary["failures"]:
            print("  - %s" % f)
    print("Fayllar:")
    for kind, path in summary["paths"].items():
        print("  %-9s %s" % (kind, path))
    print("Canvas bloku: %d simvol (limit %d)" % (summary["canvas_chars"], _CANVAS_LIMIT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
