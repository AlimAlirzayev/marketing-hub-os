"""Operations Self-Review — the system grades its own week and learns from it.

Pillar 4 of the roadmap ([[project_autonomy_money_roadmap]]): "the system reviews
its own outcomes and improves so month 6 >> month 1 with no extra operator work."
The Impact Ledger is the BUSINESS-results counterpart (monthly, leadership-facing);
this is its RELIABILITY counterpart — a weekly retrospective over the OS's OWN
operational history (the sense event log): how reliably did it run, what broke, how
often did the premium brain fall back to free, was anything rejected — then it files
the durable patterns as lessons for the brain's own review queue.

Distinct from the advisor (point-in-time "act NOW" findings) and the radar (outside
AI landscape): this LOOKS BACK over a window, TRENDS it, and LEARNS.

Design mirrors impact_ledger: pure compute (assess / lessons / weekly_due) split
from IO (collect / run_if_due), so it is unit-testable offline. No fabricated data —
every number is counted from real events; a lesson only fires on a clear threshold.
Free: pure arithmetic over the local event log, zero LLM tokens.
"""

from __future__ import annotations

import collections
import datetime as _dt
import json
import os
from pathlib import Path

from . import sense

_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / "data" / "self_review_state.json"      # machine-local, git-ignored
_USAGE_LOG = _ROOT / "data" / "logs" / "llm_usage.jsonl"
_INTERVAL_DAYS = int(os.getenv("SELF_REVIEW_INTERVAL_DAYS", "7"))
# A brain that falls back to the free floor more than this fraction of calls (over
# a meaningful sample) is a reliability signal worth a lesson, not noise.
_FALLBACK_LESSON_RATIO = float(os.getenv("SELF_REVIEW_FALLBACK_RATIO", "0.3"))
_FALLBACK_MIN_CALLS = int(os.getenv("SELF_REVIEW_FALLBACK_MIN_CALLS", "10"))
_UNSTABLE_SERVICE_HITS = int(os.getenv("SELF_REVIEW_UNSTABLE_HITS", "3"))
_ERROR_LESSON_MIN = int(os.getenv("SELF_REVIEW_ERROR_MIN", "3"))


def _summ(e: dict) -> str:
    return str(e.get("summary", "")).lower()


def assess(events: list[dict], *, now: float, window_days: int = 7,
           cost_usd: float | None = None) -> dict:
    """Pure: turn a window of sense events into an operational scorecard. Counts
    only — nothing is invented; an absent signal is simply zero/None."""
    by_kind = collections.Counter(e.get("kind") for e in events)

    jobs = [e for e in events if e.get("kind") == "job"]
    job_done = sum(1 for e in jobs if "done" in _summ(e))
    job_err = sum(1 for e in jobs if "error" in _summ(e) or "fail" in _summ(e))
    total_jobs = job_done + job_err
    reliability = round(job_done / total_jobs * 100, 1) if total_jobs else None

    wd = [e for e in events if e.get("kind") == "watchdog"]
    wd_down = [e for e in wd if "down" in _summ(e)]
    wd_gaveup = sum(1 for e in wd if "gave" in _summ(e) or "təslim" in _summ(e)
                    or "teslim" in _summ(e))
    wd_recovered = sum(1 for e in wd if "recover" in _summ(e) or "ayaq" in _summ(e)
                       or "restart" in _summ(e))
    svc_downs: collections.Counter = collections.Counter()
    for e in wd_down:
        toks = _summ(e).split()
        if toks:
            svc_downs[toks[0]] += 1

    llm = [e for e in events if e.get("kind") == "llm"]
    llm_fallback = sum(1 for e in llm if "fell back" in _summ(e)
                       or "fallback" in _summ(e) or "failed on all" in _summ(e))
    fallback_ratio = round(llm_fallback / len(llm), 2) if llm else None

    sec_rejects = int(by_kind.get("security", 0))
    skills = int(by_kind.get("skill", 0))
    syncs = int(by_kind.get("sync", 0))

    # qualitative status — honest, threshold-based, never a fake precise score.
    concerns = []
    if reliability is not None and reliability < 90:
        concerns.append("reliability")
    if wd_gaveup > 0:
        concerns.append("service_gaveup")
    if fallback_ratio is not None and fallback_ratio > _FALLBACK_LESSON_RATIO and len(llm) >= _FALLBACK_MIN_CALLS:
        concerns.append("brain_fallback")
    status = "Problemli" if len(concerns) >= 2 else ("Diqqət" if concerns else "Sağlam")

    return {
        "window_days": window_days,
        "generated_ts": now,
        "events_total": len(events),
        "jobs": {"done": job_done, "error": job_err, "reliability_pct": reliability},
        "incidents": {"down_events": len(wd_down), "recovered": wd_recovered,
                      "gave_up": wd_gaveup, "by_service": dict(svc_downs)},
        "brain": {"llm_calls": len(llm), "free_fallbacks": llm_fallback,
                  "fallback_ratio": fallback_ratio},
        "security": {"rejected": sec_rejects},
        "activity": {"skills": skills, "syncs": syncs,
                     "by_kind": {k: int(v) for k, v in by_kind.items()}},
        "cost_usd": cost_usd,
        "status": status,
        "concerns": concerns,
    }


def lessons(a: dict) -> list[dict]:
    """Pure: the durable patterns worth remembering, only on a clear threshold.
    Each -> {title, body, tags}. Empty when the week was unremarkable (no noise)."""
    out: list[dict] = []
    brain = a.get("brain", {})
    if (brain.get("fallback_ratio") is not None
            and brain["fallback_ratio"] > _FALLBACK_LESSON_RATIO
            and brain.get("llm_calls", 0) >= _FALLBACK_MIN_CALLS):
        out.append({
            "title": "Premium brain tez-tez pulsuz-a düşür",
            "body": (f"Son {a['window_days']} gündə {brain['llm_calls']} LLM çağırışının "
                     f"{brain['free_fallbacks']}-i ({int(brain['fallback_ratio']*100)}%) "
                     "pulsuz floor-a düşdü — Claude subscription yolu (cap/rotasiya) "
                     "araşdırılmalıdır, keyfiyyət səssizcə enir."),
            "tags": ["reliability", "llm", "self-review"]})
    for svc, hits in (a.get("incidents", {}).get("by_service") or {}).items():
        if hits >= _UNSTABLE_SERVICE_HITS:
            out.append({
                "title": f"'{svc}' servisi həftədə {hits} dəfə dayandı",
                "body": (f"Son {a['window_days']} gündə '{svc}' {hits} dəfə dayanma "
                         "hadisəsi verdi — sabitlik/loglar araşdırılmalıdır."),
                "tags": ["reliability", "watchdog", "self-review"]})
    jobs = a.get("jobs", {})
    if jobs.get("error", 0) >= _ERROR_LESSON_MIN:
        out.append({
            "title": f"{jobs['error']} iş xəta ilə bitdi",
            "body": (f"Son {a['window_days']} gündə {jobs['error']} iş xəta ilə bitdi "
                     f"(reliability {jobs.get('reliability_pct')}%) — təkrarlanan "
                     "səbəblər araşdırılmalıdır."),
            "tags": ["reliability", "self-review"]})
    return out


def weekly_due(now_ts: float, last_ts: float | None, interval_days: int = 7) -> bool:
    """Pure: due if never run, or a full interval has passed since the last run."""
    if last_ts is None:
        return True
    return (now_ts - last_ts) >= interval_days * 86400


# --- IO ------------------------------------------------------------------------
def _cost_in_window(start_ts: float) -> float | None:
    """Sum LLM cost from the usage ledger since start_ts. Best-effort; None if the
    log is absent or unreadable (cost is then simply omitted, never invented)."""
    if not _USAGE_LOG.exists():
        return None
    total, seen = 0.0, False
    try:
        for line in _USAGE_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if float(rec.get("ts", 0) or 0) < start_ts:
                continue
            for key in ("cost_usd", "cost", "usd"):
                if rec.get(key) is not None:
                    total += float(rec[key]); seen = True
                    break
    except Exception:
        return total if seen else None
    return round(total, 4) if seen else None


def collect(window_days: int = 7, now: float | None = None) -> dict:
    now = now or _dt.datetime.now().timestamp()
    start = now - window_days * 86400
    events = sense.since(start)
    return assess(events, now=now, window_days=window_days,
                  cost_usd=_cost_in_window(start))


def _fmt_pct(v) -> str:
    return "—" if v is None else f"{v:g}%"


def _format(a: dict) -> str:
    j, inc, br = a["jobs"], a["incidents"], a["brain"]
    lamp = {"Sağlam": "🟢", "Diqqət": "🟡", "Problemli": "🔴"}.get(a["status"], "·")
    lines = [f"🩺 ƏMƏLİYYAT ÖZÜ-QİYMƏTLƏNDİRMƏSİ — son {a['window_days']} gün",
             "=" * 34, f"Ümumi vəziyyət: {lamp} {a['status']}", ""]
    lines.append(f"• Etibarlılıq: {j['done']} iş bitdi, {j['error']} xəta "
                 f"(uğur {_fmt_pct(j['reliability_pct'])})")
    if inc["down_events"] or inc["gave_up"]:
        extra = f", {inc['gave_up']} təslim" if inc["gave_up"] else ""
        lines.append(f"• İnsidentlər: {inc['down_events']} servis-dayanma, "
                     f"{inc['recovered']} bərpa{extra}")
        if inc["by_service"]:
            worst = ", ".join(f"{s}×{n}" for s, n in sorted(
                inc["by_service"].items(), key=lambda kv: -kv[1])[:4])
            lines.append(f"    ən problemli: {worst}")
    else:
        lines.append("• İnsidentlər: yoxdur — servislər sabit qaldı")
    if br["llm_calls"]:
        fr = f" ({int((br['fallback_ratio'] or 0)*100)}%)" if br["fallback_ratio"] else ""
        lines.append(f"• Beyin: {br['llm_calls']} LLM çağırışı, "
                     f"{br['free_fallbacks']} pulsuz-a düşmə{fr}")
    if a.get("cost_usd") is not None:
        lines.append(f"• LLM xərci (həftəlik): ~${a['cost_usd']:g}")
    if a["security"]["rejected"]:
        lines.append(f"• Təhlükəsizlik: {a['security']['rejected']} icazəsiz cəhd rədd edildi ✅")

    ls = lessons(a)
    if ls:
        lines += ["", "ÖYRƏNİLƏN (beyin növbəsinə yazıldı):"]
        lines += [f"  • {x['title']}" for x in ls]
    else:
        lines += ["", "Bu həftə xüsusi öyrənilən nümunə yoxdur — göstəricilər normal."]
    return "\n".join(lines)


def report(window_days: int = 7) -> str:
    return _format(collect(window_days))


def _file_lessons(a: dict) -> int:
    """Write distilled lessons to the brain's REVIEW QUEUE (add_pending) — auto
    reflection must not pollute the trusted store; the daily curator promotes the
    good ones. Best-effort; returns how many were filed. Never raises."""
    ls = lessons(a)
    if not ls:
        return 0
    filed = 0
    try:
        from brain import store
        from brain.store import Entry
        today = _dt.date.today().isoformat()
        for x in ls:
            try:
                eid = store.slugify(f"lesson-{x['title']}")
                store.add_pending(Entry(
                    id=eid, type="lesson", title=x["title"], body=x["body"],
                    tags=sorted(x["tags"]), source="self-review", confidence="low",
                    created=today, updated=today, related=[]))
                filed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[self_review] lesson file skipped: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[self_review] brain unavailable: {exc}")
    return filed


def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def run_if_due(now: float | None = None) -> dict:
    """Once a week: build the review, file its lessons, record the run. Returns
    {"skipped": True} when not due, else {"skipped": False, "text", "lessons"}.
    Never raises — it rides the always-on supervisor."""
    try:
        now = now or _dt.datetime.now().timestamp()
        state = _load_state()
        if not weekly_due(now, state.get("last_ts"), _INTERVAL_DAYS):
            return {"skipped": True}
        a = collect(_INTERVAL_DAYS, now=now)
        text = _format(a)
        filed = _file_lessons(a)
        state["last_ts"] = now
        _save_state(state)
        return {"skipped": False, "text": text, "lessons": filed, "status": a["status"]}
    except Exception as exc:  # noqa: BLE001
        print(f"[self_review] run_if_due error: {exc}")
        return {"skipped": True}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    print(report(days))
