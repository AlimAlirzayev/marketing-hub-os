"""Advisor — the foresight organ: turn the live body-state into ranked, grounded
proposals. This is the part of the north star that makes the system *proactive*:
it reads its own reality (sense.snapshot + the reflexes + event log + pending
lessons) and tells the operator the next best moves BEFORE they ask — starting
with contradictions the body must never ignore.

No fabricated data. Every finding is computed from a REAL signal:
  * sense.contradictions()  — logged claim ≠ live .env reflex
  * git state               — uncommitted / no-commits-yet risk
  * queue state             — work stuck with no worker, or failed jobs
  * env reflex              — missing credentials that gate known capabilities
  * brain pending queue     — lessons distilled but never reviewed (learning stalls)
  * llm usage log           — today's spend / model concentration
An optional LLM pass only *phrases and prioritizes* those real facts (free-first
via the unified router; disable with ADVISOR_DISABLE_LLM=1). With no LLM it
degrades to the deterministic findings verbatim — so it is honest offline too.

Glance at it:  python -m gateway.advisor          (with AI synthesis)
               python -m gateway.advisor --no-llm  (facts only)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import sense

ROOT = Path(__file__).resolve().parent.parent

_COST_WARN = float(os.getenv("ADVISOR_COST_WARN_USD", "1.0"))

# Credentials whose absence blocks a concrete, known capability. provider is the
# doit allowlist key used to acquire it.
_GATING_CREDS = {
    "RAPIDAPI_KEY": ("rapidapi", "influencer-hunter RapidAPI fallback + çoxqollu sosial mənbələr"),
}

_LEVEL_RANK = {"risk": 0, "watch": 1, "info": 2}
_LEVEL_LAMP = {"risk": "🔴", "watch": "🟡", "info": "🔵"}


@dataclass
class Finding:
    level: str            # "risk" | "watch" | "info"
    code: str
    title: str
    detail: str
    suggestion: str = ""

    def line(self) -> str:
        lamp = _LEVEL_LAMP.get(self.level, "·")
        s = f"{lamp} [{self.level}] {self.title} — {self.detail}"
        if self.suggestion:
            s += f"\n     → təklif: {self.suggestion}"
        return s

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "title": self.title,
                "detail": self.detail, "suggestion": self.suggestion}


def _pending_lessons() -> int:
    """Count distilled lessons waiting in the review queue. Never raises."""
    try:
        from brain import store
        return len(store.list_pending())
    except Exception:
        try:
            d = ROOT / "data" / "memory" / "_pending"
            return len([p for p in d.glob("*.md")]) if d.exists() else 0
        except Exception:
            return 0


def observe_state(snap: dict | None = None) -> list[Finding]:
    """Compute grounded findings from one live snapshot. Pure over ``snap`` except
    for contradictions/pending which read their own live source. Never raises."""
    snap = snap or sense.snapshot()
    findings: list[Finding] = []
    env = snap.get("env", {}) or {}

    # 1. contradictions — the body disagreeing with its own log (highest signal).
    for c in (snap.get("contradictions") or sense.contradictions(snap)):
        findings.append(Finding(
            "risk", "contradiction", f"Ziddiyyət: {c.get('key')}", c.get("detail", ""),
            "Açar həqiqətən lazımdırsa doit ilə yenidən al; yoxsa yanlış hadisəni "
            "təmizlə (test izolyasiyası)."))

    # 2. uncommitted work — the literal current risk: a large body, never committed.
    git = snap.get("git", {}) or {}
    if git.get("dirty") and str(git.get("head") or "unknown") in ("", "unknown"):
        findings.append(Finding(
            "risk", "no_commits", "Repo commit-siz",
            "master-də heç bir commit yoxdur — bütün iş yalnız işçi ağacındadır.",
            "İlk commit-i yarat (sən təsdiq edəndə) ki, bu qədər iş bir nasazlıqda itməsin."))
    elif git.get("dirty"):
        findings.append(Finding(
            "watch", "dirty_tree", "Commit edilməmiş dəyişikliklər",
            "İşçi ağac 'dirty' — dəyişikliklər saxlanmayıb.",
            "Məntiqli, fokuslanmış commit-lərə böl."))

    # 3. queue — work that cannot move, or work that broke.
    q = snap.get("queue", {}) or {}
    if int(q.get("queued", 0) or 0) > 0 and int(q.get("running", 0) or 0) == 0:
        findings.append(Finding(
            "watch", "queue_idle", f"{q['queued']} iş növbədə, işçi yox",
            "Növbədə iş var, amma running=0 — işçi/supervisor işləmir ola bilər.",
            "python -m gateway.supervisor ilə daim-açıq işçini qaldır."))
    if int(q.get("error", 0) or 0) > 0:
        findings.append(Finding(
            "watch", "queue_errors", f"{q['error']} uğursuz iş",
            "Növbədə xətalı işlər var.",
            "gateway xəta detalını saxlayır — səbəbi yoxla, sonra yenidən növbəyə sal."))

    # 4. missing credentials that gate a concrete capability.
    for key, (provider, cap) in _GATING_CREDS.items():
        if not str(env.get(key, "")).startswith("SET"):
            findings.append(Finding(
                "watch", "missing_cred", f"{key} yoxdur",
                f"Bu açar olmadan bağlıdır: {cap}.",
                f"doit ilə al: GATEWAY_ALLOW_CREDENTIALS=1, sonra "
                f"credentials.acquire('{provider}', approved=True)."))

    # 5. learning that never compounds — distilled lessons stuck unreviewed.
    pend = _pending_lessons()
    if pend > 0:
        findings.append(Finding(
            "watch", "pending_lessons", f"{pend} dərs nəzərdən keçirilməyib",
            "Reflect dərsləri _pending növbəsində qalıb — təsdiqlənməsə öyrənmə "
            "kompound olmur.",
            "python -m brain review ilə yaxşılarını təsdiqlə, qalanını at."))

    # 6. token economics — soft spend ceiling and model concentration.
    llm = snap.get("llm", {}) or {}
    cost = float(llm.get("cost_usd_today", 0) or 0)
    if cost > _COST_WARN:
        findings.append(Finding(
            "watch", "llm_spend", f"Bugünkü LLM xərci ${cost:.2f}",
            f"Yumşaq həddi (${_COST_WARN:.2f}) keçib.",
            "Router tier-lərini yoxla; mümkün işləri 'cheap' tier-ə yönəlt."))

    # 7. cold live memory — built but not yet exercised by real conversations.
    mem = snap.get("memory", {}) or {}
    if int(mem.get("turns", 0) or 0) == 0 and int(q.get("done", 0) or 0) > 0:
        findings.append(Finding(
            "info", "memory_cold", "Canlı yaddaş hələ boş",
            "İşlər bitib, amma blackboard turn tutmayıb (CLI işlərin chat thread-i yox).",
            "Telegram üzərindən real söhbət axını L1–L4 yaddaşı qızdıracaq."))

    findings.sort(key=lambda f: _LEVEL_RANK.get(f.level, 9))
    return findings


def _llm_prioritize(findings: list[Finding]) -> str | None:
    """Ask the unified router (free-first) to rank the REAL findings into the top 3
    next moves. Returns None on any failure → caller shows facts only."""
    if not findings:
        return None
    if os.getenv("ADVISOR_DISABLE_LLM", "0").lower() in {"1", "true", "yes", "on"}:
        return None
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import llm_router
    except Exception:
        return None
    facts = "\n".join(f"- [{f.level}] {f.title}: {f.detail}" for f in findings)
    prompt = (
        "Sən RAMIN OS adlı avtonom marketinq/biznes əməliyyat sisteminin baş "
        "mühəndis-məsləhətçisisən. Aşağıda sistemin CANLI vəziyyətindən çıxarılan "
        "REAL tapıntılar var (uydurma yoxdur). Onları prioritetləşdirib operatora "
        "ən yüksək təsirli 3 konkret addımı qısa Azərbaycan dilində ver. Hər addım: "
        "bir cümlə hərəkət + niyə. Yeni rəqəm uydurma, yalnız verilənlərə əsaslan.\n\n"
        f"TAPINTILAR:\n{facts}\n"
    )
    try:
        text, _model = llm_router.complete(prompt, tier="cheap", temperature=0.3)
        return (text or "").strip() or None
    except Exception:
        return None


def assess(*, use_llm: bool = True) -> dict:
    """Machine-readable assessment: snapshot-derived findings (+ optional AI ranking)."""
    snap = sense.snapshot()
    findings = observe_state(snap)
    return {
        "findings": [f.as_dict() for f in findings],
        "risk_count": sum(1 for f in findings if f.level == "risk"),
        "next_steps": _llm_prioritize(findings) if use_llm else None,
    }


def brief(*, use_llm: bool = True) -> str:
    """Human-readable proactive board — the advisor's voice. Azerbaijani."""
    snap = sense.snapshot()
    findings = observe_state(snap)
    lines = ["=== RAMIN OS — Məsləhətçi (proaktiv baxış) ==="]
    if not findings:
        lines.append("Hər şey qaydasında — kritik ziddiyyət/risk görünmür.")
    else:
        risks = sum(1 for f in findings if f.level == "risk")
        lines.append(f"{len(findings)} tapıntı ({risks} risk). Ən kritikdən başla:")
        lines.append("")
        for f in findings:
            lines.append(f.line())
    nxt = _llm_prioritize(findings) if use_llm else None
    if nxt:
        lines.append("")
        lines.append("NÖVBƏTİ ƏN YAXŞI 3 ADDIM (AI sintez):")
        lines.append(nxt)
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    use_llm = "--no-llm" not in sys.argv
    print(brief(use_llm=use_llm))
