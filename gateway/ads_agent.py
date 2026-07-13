"""Meta ads in plain Azerbaijani — the owner talks, the system acts (after approval).

Alim does not want to speak CLI ("/approve 3", campaign ids). He wants to say
"Awareness kampaniyasını dayandır" in Telegram and have it happen. This lane turns
that sentence into a checked, reversible action on the LIVE ad account.

Flow:
  1. cheap keyword gate (wants_ads) so normal chat is never hijacked;
  2. the free LLM (llm_router) extracts intent -> {action, campaign, amount};
     if it decides the sentence is not really about the ad account, we return None
     and the message falls through to the normal conversational brain;
  3. READS answer immediately (campaign list, spend);
  4. WRITES resolve the campaign BY NAME (never an id), build a plan via
     meta_write.propose() (which reads the CURRENT live state), save the plan, and
     return needs_approval -> the worker parks the job. Nothing is executed.
  5. On the approved re-run the SAVED plan is re-verified against live state and
     only then executed. The owner approves what he was actually shown.

Safety: every write goes through ads-studio/connectors/meta_write.py, which allows
only reversible ops (pause/resume/set_daily_budget), bounds budgets, and refuses to
run without approved=True. This module never sets that flag on its own — it is set
only when the queue reports the OWNER approved the job.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ADS_DIR = ROOT / "ads-studio"
PLANS_DIR = ROOT / "data" / "ads_plans"          # private (data/ is git-ignored)

# Domain nouns — without one of these the sentence is not about the ad account.
_DOMAIN = ("kampaniya", "kampani", "reklam hesab", "adset", "ad account",
           "campaign", "reklamlar", "reklamları", "reklamı")
# Operational cues — asking about or acting on the account (not writing ad copy).
_OPS = ("dayandır", "dayandir", "durdur", "söndür", "sondur", "pauza", "pause",
        "işə sal", "ise sal", "aktiv", "başlat", "baslat", "resume", "yandır",
        "büdcə", "budce", "budcə", "budget", "xərc", "xerc", "spend",
        "göstər", "goster", "siyahı", "siyahi", "list", "nə var", "ne var",
        "neçə", "nece", "vəziyyət", "veziyyet", "status", "hansı", "hansi")
# Content-creation verbs: "reklam mətni yaz" belongs to the content lane, not here.
_CONTENT_VERBS = ("mətn", "metn", "yaz", "hazırla", "hazirla", "düzəlt", "duzelt",
                  "şəkil", "sekil", "post", "video", "ssenari", "kreativ")


def wants_ads(task: str) -> bool:
    """Cheap gate: an ad-account noun + an operational cue, and not a content ask."""
    low = (task or "").lower()
    if not any(d in low for d in _DOMAIN):
        return False
    if any(v in low for v in _CONTENT_VERBS) and not any(
            o in low for o in ("dayandır", "dayandir", "büdcə", "budce", "xərc", "xerc")):
        return False
    return any(o in low for o in _OPS)


# ---------- the ad-account calls (import late: ads-studio has its own config) ----------
def _meta():
    if str(ADS_DIR) not in sys.path:
        sys.path.insert(0, str(ADS_DIR))
    from connectors import meta_write  # noqa: PLC0415
    return meta_write


def _account_summary() -> dict[str, Any]:
    mw = _meta()
    from connectors.meta import _acc  # noqa: PLC0415
    from config import META_ACCESS_TOKEN, META_API_VERSION  # noqa: PLC0415
    import urllib.parse
    import urllib.request
    acc = _acc(None)
    url = (f"https://graph.facebook.com/{META_API_VERSION}/{acc}?" + urllib.parse.urlencode(
        {"fields": "name,currency,amount_spent,account_status",
         "access_token": META_ACCESS_TOKEN}))
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


# ---------- intent ----------
_SCHEMA = (
    'Return ONLY JSON: {"action": "list"|"spend"|"pause"|"resume"|"budget"|"none", '
    '"campaign": "<the campaign NAME the user means, or empty>", '
    '"amount": <new daily budget in major currency units, or null>}\n'
    'action="none" if the sentence is not actually about operating the ad account '
    '(e.g. it asks to WRITE ad copy or is small talk).'
)


def _intent(task: str) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from llm_router import complete_json  # noqa: PLC0415
    prompt = (
        "You read an Azerbaijani/English message from the owner of a Meta ad account "
        "and extract what he wants done.\n\n"
        f"Message: {task}\n\n" + _SCHEMA
    )
    data, _model = complete_json(prompt)
    if not isinstance(data, dict):
        return {"action": "none"}
    return data


def _resolve(name_query: str) -> tuple[dict | None, list[dict]]:
    """Find the campaign the owner meant, BY NAME. Returns (match, candidates)."""
    mw = _meta()
    campaigns = mw.list_campaigns(limit=100)
    if not name_query:
        return None, campaigns
    q = name_query.lower().strip()
    exact = [c for c in campaigns if q == (c.get("name") or "").lower()]
    if exact:
        return exact[0], campaigns
    subs = [c for c in campaigns if q in (c.get("name") or "").lower()]
    if len(subs) == 1:
        return subs[0], campaigns
    if len(subs) > 1:
        return None, subs                      # ambiguous — ask which one
    names = {(c.get("name") or ""): c for c in campaigns}
    close = difflib.get_close_matches(name_query, list(names), n=3, cutoff=0.6)
    if len(close) == 1:
        return names[close[0]], campaigns
    return None, [names[c] for c in close] if close else campaigns


def _fmt_campaigns(campaigns: list[dict], limit: int = 12) -> str:
    icon = {"ACTIVE": "🟢", "PAUSED": "⏸"}
    lines = []
    for c in campaigns[:limit]:
        st = c.get("effective_status") or c.get("status") or "?"
        b = c.get("daily_budget")
        budget = f" · gündəlik {int(b) / 100:.2f}" if b else ""
        lines.append(f"{icon.get(st, '•')} {c.get('name', '?')}{budget}")
    if len(campaigns) > limit:
        lines.append(f"…və daha {len(campaigns) - limit} kampaniya")
    return "\n".join(lines)


# ---------- plan storage (so the owner approves what he was SHOWN) ----------
def _plan_path(job_id: int) -> Path:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    return PLANS_DIR / f"job-{job_id}.json"


def _save_plan(job_id: int, plan: dict) -> None:
    _plan_path(job_id).write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")


def _load_plan(job_id: int) -> dict | None:
    p = _plan_path(job_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


_AZ_OP = {"pause": "DAYANDIRILACAQ", "resume": "İŞƏ SALINACAQ",
          "set_daily_budget": "BÜDCƏSİ DƏYİŞƏCƏK"}


def _preview(plan: dict, currency: str = "") -> str:
    op = _AZ_OP.get(plan["op"], plan["op"])
    lines = [f"⏸ **Təsdiq gözləyir** — canlı reklam hesabına toxunur.", "",
             f"Kampaniya: **{plan['name']}**",
             f"İndiki vəziyyət: {plan['current_status']}",
             f"Ediləcək: **{op}**"]
    if plan["op"] == "set_daily_budget":
        was = plan.get("current_daily_budget")
        was_s = f"{int(was) / 100:.2f}" if was else "təyin olunmayıb"
        now_s = f"{plan['change']['daily_budget'] / 100:.2f}"
        lines.append(f"Gündəlik büdcə: {was_s} → **{now_s}** {currency}")
    lines += ["", "Təsdiq üçün: **hə**   ·   Ləğv üçün: **yox**"]
    return "\n".join(lines)


# ---------- the lane ----------
def handle(job) -> dict[str, Any] | None:
    """Returns an executor result dict, or None to fall through to normal chat."""
    mw = _meta()

    # --- the approved re-run: execute the plan the owner actually saw ---
    if getattr(job, "approved", 0):
        plan = _load_plan(job.id)
        if plan:
            fresh = mw.propose(plan["op"], plan["node_id"],
                               daily_budget=(plan.get("change") or {}).get("daily_budget"))
            # The owner approved a specific state. If the account drifted since, stop.
            if fresh["current_status"] != plan["current_status"]:
                return {"result": (
                    f"⚠️ Təsdiqdən sonra kampaniyanın vəziyyəti dəyişib "
                    f"({plan['current_status']} → {fresh['current_status']}). "
                    f"Təhlükəsizlik üçün icra etmədim — yenidən soruş."), "artifacts": []}
            mw.execute(plan, approved=True)
            _plan_path(job.id).unlink(missing_ok=True)
            done = {"pause": "dayandırıldı", "resume": "işə salındı",
                    "set_daily_budget": "büdcəsi yeniləndi"}[plan["op"]]
            return {"result": f"✅ **{plan['name']}** kampaniyası {done}.", "artifacts": []}

    intent = _intent(job.task)
    action = (intent.get("action") or "none").lower()
    if action == "none":
        return None                                   # not really an ads ask

    if action == "list":
        return {"result": "📋 Reklam kampaniyaları:\n\n" + _fmt_campaigns(mw.list_campaigns(limit=100)),
                "artifacts": []}

    if action == "spend":
        a = _account_summary()
        spent = int(a.get("amount_spent", 0)) / 100
        return {"result": (f"💰 **{a.get('name','Hesab')}**\n"
                           f"Ümumi xərc: {spent:,.2f} {a.get('currency','')}"), "artifacts": []}

    # --- write intents: resolve BY NAME, plan, park ---
    match, candidates = _resolve(intent.get("campaign") or "")
    if match is None:
        if candidates:
            return {"result": ("Hansı kampaniyanı nəzərdə tutursan?\n\n"
                               + _fmt_campaigns(candidates, limit=10)), "artifacts": []}
        return {"result": "Bu adda kampaniya tapmadım.", "artifacts": []}

    op = {"pause": "pause", "resume": "resume", "budget": "set_daily_budget"}[action]
    kwargs: dict[str, Any] = {}
    if op == "set_daily_budget":
        amount = intent.get("amount")
        if amount is None:
            return {"result": "Yeni gündəlik büdcəni de (məsələn: “büdcəsi 20 olsun”).",
                    "artifacts": []}
        kwargs["daily_budget"] = int(round(float(amount) * 100))

    try:
        plan = mw.propose(op, match["id"], **kwargs)
    except ValueError as exc:                          # e.g. budget outside bounds
        return {"result": f"⚠️ Bunu edə bilmərəm: {exc}", "artifacts": []}

    _save_plan(job.id, plan)
    currency = ""
    try:
        currency = _account_summary().get("currency", "")
    except Exception:  # noqa: BLE001
        pass
    return {"result": _preview(plan, currency), "artifacts": [], "needs_approval": True}
