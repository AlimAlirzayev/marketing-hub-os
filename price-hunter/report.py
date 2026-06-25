"""Output sinks: JSON + Markdown report on disk, optional Telegram push.

Reuses the repo-wide TELEGRAM_BOT_TOKEN so a scheduled run can DM the verdict
straight to the user - the bridge to the Xalq Insurance Digital OS autonomous layer.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import httpx

import config
from hunt import HuntResult


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")[:40]


def to_json(res: HuntResult) -> dict:
    return {
        "query": res.query,
        "generated_at": config.now_iso(),
        "spec": res.spec.to_dict(),
        "best_legit": res.best_legit.to_dict() if res.best_legit else None,
        "cheapest": res.cheapest.to_dict() if res.cheapest else None,
        "verdict": res.verdict,
        "market": res.stats or {},
        "history": res.history or {},
        "offers": [o.to_dict() for o in res.ranked],
        "source_status": [
            {"source": s, "status": st, "note": n} for s, st, n in res.source_status],
        "stats": {"total_seen": res.total_seen, "rejected": res.rejected,
                  "matched": len(res.ranked)},
    }


def to_markdown(res: HuntResult) -> str:
    s = res.spec
    L = [f"# Price Hunt — {s.canonical_name}",
         f"_Query: `{res.query}` · {config.now_iso()} · fair window "
         f"{s.fair_low:g}–{s.fair_high:g} AZN_\n"]
    if res.verdict:
        L += ["## Verdict", res.verdict, ""]
    if res.best_legit:
        b = res.best_legit
        L.append(f"**Best honest buy:** {b.price:g} AZN @ {b.source} "
                 f"(trust {int(b.trust*100)}%) — {b.title[:70]}")
    if res.cheapest and res.cheapest is not res.best_legit:
        c = res.cheapest
        L.append(f"**Absolute cheapest:** {c.price:g} AZN @ {c.source} "
                 f"(trust {int(c.trust*100)}%) {'⚠️ ' + ', '.join(c.flags) if c.flags else ''}")
    L += ["", "## Ranked offers", "",
          "| # | Price | Trust | Source | Cond | Flags | Title |",
          "|--:|------:|------:|--------|------|-------|-------|"]
    for i, o in enumerate(res.ranked[:25], 1):
        L.append(f"| {i} | {o.price:g} | {int(o.trust*100)}% | {o.source} | "
                 f"{o.condition} | {', '.join(o.flags) or '—'} | {o.title[:50]} |")
    L += ["", "## Source coverage", "",
          "| Source | Status | Note |", "|--------|--------|------|"]
    for src, st, note in res.source_status:
        L.append(f"| {src} | {st} | {note} |")
    L += ["", f"_Seen {res.total_seen} raw offers · "
          f"{len(res.ranked)} matched · {res.rejected} rejected_"]
    return "\n".join(L)


def save(res: HuntResult) -> tuple[str, str]:
    config.ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(config.REPORT_DIR, f"{_slug(res.query)}-{stamp}")
    jpath, mpath = base + ".json", base + ".md"
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(to_json(res), f, ensure_ascii=False, indent=2)
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(to_markdown(res))
    return jpath, mpath


def telegram(res: HuntResult) -> bool:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return False
    b = res.best_legit or res.cheapest
    head = f"🎧 *{res.spec.canonical_name}*\n"
    if b:
        head += (f"Ən yaxşı: *{b.price:g} AZN* @ {b.source} "
                 f"(trust {int(b.trust*100)}%)\n")
    body = (res.verdict or "")[:900]
    text = head + "\n" + body
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text,
                  "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=20)
        return r.status_code == 200
    except Exception:
        return False
