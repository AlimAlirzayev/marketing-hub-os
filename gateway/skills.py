"""Hermes-style learning loop — the system gets better at the jobs it repeats.

Adapted from the Hermes Agent (NousResearch) pattern Alim asked to weave in:
after a task SUCCEEDS, distill the reusable know-how into a small Markdown skill
card; when a similar task arrives later, inject the matching cards so the agent
starts from what already worked instead of from scratch.

Two halves:
  * learn_from_job(task, result) — on a substantial, successful WORK job, ask the
    free model to extract {title, triggers, steps} and save it as a skill card.
  * relevant(task) — retrieve the top cards whose triggers overlap the new task,
    as text to prepend to the work-lane system prompt.

Self-improvement (Karpathy layer 4, added 2026-07-20): every card carries an
outcome record. relevant() logs which cards it injected for a task; when that
task later finishes, learn_from_job() credits those cards — a clean delivery is
a WIN, a soft-failure result (❌ / icra xətası...) is a LOSS. Proven cards
outrank unproven ones on equal trigger overlap, pruning drops the weakest cards
first (not merely the oldest), and a card that only ever loses is retired
automatically. So the library converges on what demonstrably works instead of
what was merely written down. Stats live in a sidecar (data/skills/_stats.json)
so the card format — and everything that parses it — stays untouched.

Scope + safety: learns ONLY from successful work-lane jobs (not chat, not
errors/checkpoints); cards are capped and deduped; stored LOCALLY per machine
(data/skills/, git-ignored) so this can never jam the cross-twin sync. Every
step is guarded — learning must never delay or break a delivery.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import sense

ROOT = Path(__file__).resolve().parent.parent
_DIR = ROOT / "data" / "skills"
_MAX_SKILLS = 80
_MIN_TASK_WORDS = 4
# result tags whose mode is real WORK worth learning from (see executor labels)
_WORK_MODES = ("agentic-tools", "browser", "google-search", "web-search",
               "fanout", "content", "council")
_STOP = {"the", "and", "for", "with", "bir", "üçün", "və", "the", "that", "bu",
         "mən", "sən", "sistem", "zəhmət", "olmasa", "please", "make", "yaz"}
# markers in a delivered result that mean the job soft-failed (see learn gate)
_FAIL_MARKS = ("icra xətası", "❌", "⏸", "alınmadı", "failed")
# outcome bookkeeping: sidecar next to the cards, injections awaiting a verdict
# expire after a day, and a card that only ever loses is retired at this count.
_STATS_NAME = "_stats.json"
_PENDING_TTL = 24 * 3600
_PENDING_CAP = 40
_RETIRE_LOSSES = 3


def _mode_of(result: str) -> str | None:
    m = re.match(r"^_\[([^\]\n]*)\]_", result or "")
    return m.group(1).split(":")[0] if m else None


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[\wğışçöüəĞİŞÇÖÜƏ]{4,}", (text or "").lower())
    return {w for w in words if w not in _STOP}


def _slug(title: str) -> str:
    s = re.sub(r"[^\w]+", "-", (title or "").lower()).strip("-")
    return (s or "skill")[:60]


# ---------------------------------------------------------------------------
# Outcome records — who was injected, and did the job land?

def _task_key(task: str) -> str:
    return hashlib.sha1(" ".join((task or "").lower().split()).encode()).hexdigest()[:12]


def _load_stats() -> dict:
    try:
        d = json.loads((_DIR / _STATS_NAME).read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return {"cards": d.get("cards") or {}, "pending": d.get("pending") or {}}
    except Exception:
        pass
    return {"cards": {}, "pending": {}}


def _save_stats(stats: dict) -> None:
    # drop expired pending entries + cap the backlog before every write
    now = time.time()
    pend = {k: v for k, v in stats.get("pending", {}).items()
            if now - v.get("ts", 0) < _PENDING_TTL}
    if len(pend) > _PENDING_CAP:
        for k in sorted(pend, key=lambda k: pend[k].get("ts", 0))[:-_PENDING_CAP]:
            del pend[k]
    stats["pending"] = pend
    _DIR.mkdir(parents=True, exist_ok=True)
    (_DIR / _STATS_NAME).write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")


def _quality(rec: dict) -> int:
    return int(rec.get("wins", 0)) - int(rec.get("losses", 0))


def _record_injection(task: str, slugs: list[str]) -> None:
    """relevant() injected these cards for this task — remember, await verdict."""
    stats = _load_stats()
    for s in slugs:
        rec = stats["cards"].setdefault(s, {"uses": 0, "wins": 0, "losses": 0})
        rec["uses"] = int(rec.get("uses", 0)) + 1
        rec["last_used"] = int(time.time())
    stats["pending"][_task_key(task)] = {"slugs": slugs, "ts": time.time()}
    _save_stats(stats)


def _credit(task: str, success: bool) -> None:
    """The job for `task` finished — pay out to the cards injected for it.
    A card that only ever loses gets retired (file + record deleted)."""
    stats = _load_stats()
    entry = stats["pending"].pop(_task_key(task), None)
    if not entry:
        return
    for s in entry.get("slugs", []):
        rec = stats["cards"].setdefault(s, {"uses": 0, "wins": 0, "losses": 0})
        rec["wins" if success else "losses"] = \
            int(rec.get("wins" if success else "losses", 0)) + 1
        if not success and rec.get("wins", 0) == 0 \
                and rec.get("losses", 0) >= _RETIRE_LOSSES:
            (_DIR / f"{s}.md").unlink(missing_ok=True)
            del stats["cards"][s]
            sense.emit("skill", f"retired (never won): {s}")
    _save_stats(stats)


def stats_snapshot() -> dict:
    """Read-only view of the outcome ledger, for panels and tests."""
    return _load_stats()["cards"]


def _distill(task: str, result: str) -> dict | None:
    """Ask the free model to compress this job into a reusable card."""
    import sys
    sys.path.insert(0, str(ROOT))
    from llm_router import complete_json
    prompt = (
        f"A task was completed successfully.\nTASK: {task}\n\n"
        f"RESULT (truncated): {result[:1500]}\n\n"
        "Extract a REUSABLE skill for next time. Return STRICT JSON: "
        '{"title": "short imperative name", "triggers": ["3-6 lowercase keywords '
        'that a similar future task would contain"], "steps": ["3-6 concise, '
        'generalized how-to steps — no specifics from THIS task"]}. '
        "If nothing generalizable, return {\"title\": \"\"}."
    )
    data, _ = complete_json(prompt, tier="cheap", temperature=0.3)
    if not isinstance(data, dict) or not (data.get("title") or "").strip():
        return None
    return {
        "title": str(data["title"]).strip()[:80],
        "triggers": [str(t).strip().lower() for t in (data.get("triggers") or [])][:6],
        "steps": [str(s).strip() for s in (data.get("steps") or []) if str(s).strip()][:6],
    }


def learn_from_job(task: str, result: str) -> str | None:
    """Save a skill card from a successful work job. Returns the slug or None.
    Also settles the outcome ledger for cards injected into this job — even a
    soft failure teaches (a loss), it just never becomes a new card.
    Fully guarded — any failure is swallowed (learning never breaks delivery)."""
    try:
        if len((task or "").split()) < _MIN_TASK_WORDS:
            return None
        mode = _mode_of(result)
        if mode not in _WORK_MODES:
            return None
        low = (result or "").lower()
        success = not any(x in low for x in _FAIL_MARKS)
        _credit(task, success)
        if not success:
            return None
        card = _distill(task, result)
        if not card or not card["steps"]:
            return None
        _DIR.mkdir(parents=True, exist_ok=True)
        slug = _slug(card["title"])
        body = (
            f"# {card['title']}\n\n"
            f"**Triggers:** {', '.join(card['triggers'])}\n\n"
            "**Steps:**\n" + "\n".join(f"- {s}" for s in card["steps"]) + "\n"
        )
        (_DIR / f"{slug}.md").write_text(body, encoding="utf-8")
        _prune()
        sense.emit("skill", f"learned: {card['title']}", {"slug": slug})
        return slug
    except Exception as exc:  # noqa: BLE001
        sense.emit("skill", f"learn skipped: {exc}")
        return None


def _prune() -> None:
    """Over the cap, drop the WEAKEST cards first (worst win/loss record),
    age only breaking ties — a proven old card outlives an unproven new one."""
    cards = _load_stats()["cards"]
    ranked = sorted(_DIR.glob("*.md"),
                    key=lambda p: (_quality(cards.get(p.stem, {})), p.stat().st_mtime))
    for p in ranked[:-_MAX_SKILLS]:  # keep the strongest/newest _MAX_SKILLS
        try:
            p.unlink()
        except Exception:
            pass


def relevant(task: str, k: int = 2) -> str:
    """Top-k learned skill cards whose triggers overlap the task, as prompt text.
    On equal overlap the card with the better track record wins. Injections are
    logged so the job's outcome can later credit the cards (see _credit).
    Empty string when nothing matches — the caller adds it verbatim."""
    try:
        if not _DIR.exists():
            return ""
        kw = _keywords(task)
        if not kw:
            return ""
        records = _load_stats()["cards"]
        scored = []
        for p in _DIR.glob("*.md"):
            text = p.read_text(encoding="utf-8")
            mt = re.search(r"\*\*Triggers:\*\*(.*)", text)
            triggers = _keywords(mt.group(1)) if mt else set()
            score = len(kw & (triggers | _keywords(text)))
            if score:
                scored.append((score, _quality(records.get(p.stem, {})), p.stem, text))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        top = scored[:k]
        if not top:
            return ""
        _record_injection(task, [t[2] for t in top])
        return ("\n\nLEARNED SKILLS (reuse what worked before):\n\n"
                + "\n\n".join(t[3] for t in top))
    except Exception:
        return ""
