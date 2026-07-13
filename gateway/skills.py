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

Scope + safety: learns ONLY from successful work-lane jobs (not chat, not
errors/checkpoints); cards are capped and deduped; stored LOCALLY per machine
(data/skills/, git-ignored) so this can never jam the cross-twin sync. Every
step is guarded — learning must never delay or break a delivery.
"""

from __future__ import annotations

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


def _mode_of(result: str) -> str | None:
    m = re.match(r"^_\[([^\]\n]*)\]_", result or "")
    return m.group(1).split(":")[0] if m else None


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[\wğışçöüəĞİŞÇÖÜƏ]{4,}", (text or "").lower())
    return {w for w in words if w not in _STOP}


def _slug(title: str) -> str:
    s = re.sub(r"[^\w]+", "-", (title or "").lower()).strip("-")
    return (s or "skill")[:60]


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
    Fully guarded — any failure is swallowed (learning never breaks delivery)."""
    try:
        if len((task or "").split()) < _MIN_TASK_WORDS:
            return None
        mode = _mode_of(result)
        if mode not in _WORK_MODES:
            return None
        low = (result or "").lower()
        if any(x in low for x in ("icra xətası", "❌", "⏸", "alınmadı", "failed")):
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
    cards = sorted(_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime)
    for p in cards[:-_MAX_SKILLS]:  # keep the newest _MAX_SKILLS
        try:
            p.unlink()
        except Exception:
            pass


def relevant(task: str, k: int = 2) -> str:
    """Top-k learned skill cards whose triggers overlap the task, as prompt text.
    Empty string when nothing matches — the caller adds it verbatim."""
    try:
        if not _DIR.exists():
            return ""
        kw = _keywords(task)
        if not kw:
            return ""
        scored = []
        for p in _DIR.glob("*.md"):
            text = p.read_text(encoding="utf-8")
            mt = re.search(r"\*\*Triggers:\*\*(.*)", text)
            triggers = _keywords(mt.group(1)) if mt else set()
            score = len(kw & (triggers | _keywords(text)))
            if score:
                scored.append((score, text))
        scored.sort(key=lambda t: t[0], reverse=True)
        top = [t for _, t in scored[:k]]
        if not top:
            return ""
        return ("\n\nLEARNED SKILLS (reuse what worked before):\n\n"
                + "\n\n".join(top))
    except Exception:
        return ""
