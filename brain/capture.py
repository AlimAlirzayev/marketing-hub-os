"""Reflect: turn a finished job (task + result) into durable lessons.

This is the part that makes the system compound. After work is done, an LLM reads
what happened and proposes a few *reusable* lessons -- not a summary of this one
job, but knowledge that would help the next similar task.

Quality guardrail: suggestions are written to the **pending review queue**
(``data/memory/_pending/``), never straight into the trusted store. A human (or
``brain review approve``) promotes the good ones. This honours the project rule
"no fabricated data" -- the brain never silently fills itself with guesses.

Decoupled on purpose: it calls Gemini directly via the env key and degrades to a
no-op (returns ``[]``) when no key / rate-limited / offline, so importing this
never drags in the whole gateway.
"""

from __future__ import annotations

import difflib
import json
import os
import re

from .store import TYPES, Entry, add_pending, slugify

_REFLECT_MODEL = os.getenv("BRAIN_REFLECT_MODEL", "gemini-2.5-flash")

_PROMPT = """You are the memory of an autonomous marketing/business operations system
called RAMIN OS. A background job just finished. Extract durable, REUSABLE lessons
that would help the system do the NEXT similar task better.

Rules:
- Only extract knowledge that generalises beyond this one job. Skip one-off facts.
- 0 to 3 items. If nothing is worth remembering, return an empty list. Prefer
  fewer, higher-quality items over filler.
- Each item must be independently useful months from now.
- "type" is one of: decision, lesson, playbook, pattern, glossary, preference.
- "body" is 1-4 sentences, concrete and actionable. For a lesson/decision include
  the WHY.
- Write the body in the same spirit as the operator's notes: plain, direct.

Return STRICT JSON, no prose, no code fence:
{"items": [{"type": "...", "title": "...", "tags": ["..."], "confidence": "high|medium|low", "body": "..."}]}

--- TASK ---
{task}

--- RESULT ---
{result}
"""


def _via_router(prompt: str) -> str | None:
    """Prefer the unified router (free-first cascade + one spend log) for the
    reflection call. Returns None on any failure → caller falls back / no-ops."""
    if os.getenv("BRAIN_DISABLE_LLM_ROUTER", "0").lower() in {"1", "true", "yes", "on"}:
        return None
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        import llm_router
        text, _model = llm_router.complete(prompt, tier="cheap", want_json=True, temperature=0.2)
        return (text or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def _gemini_json(prompt: str) -> str | None:
    routed = _via_router(prompt)
    if routed is not None:
        return routed
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=_REFLECT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return (resp.text or "").strip()
    except Exception:
        return None


def _parse_items(raw: str) -> list[dict]:
    if not raw:
        return []
    # Strip a ```json ... ``` fence if the model added one despite instructions.
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    # Otherwise grab the outermost {...} object.
    if not raw.startswith("{"):
        brace = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace:
            raw = brace.group(0)
    try:
        data = json.loads(raw)
    except Exception:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def distill(task: str, result: str, *, source: str = "reflect") -> list[Entry]:
    """Run the LLM and return candidate lessons WITHOUT persisting them anywhere.

    The pure extraction half of reflection: callers decide what to do with the
    result (queue for review, auto-commit with a quality gate, etc.). Returns
    ``[]`` when no LLM is available -- never raises.
    """
    # Keep the prompt bounded; long artifacts add cost without adding signal.
    prompt = _PROMPT.replace("{task}", task.strip()[:2000]).replace(
        "{result}", result.strip()[:6000]
    )
    raw = _gemini_json(prompt)
    items = _parse_items(raw or "")

    entries: list[Entry] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        body = str(it.get("body", "")).strip()
        if not title or not body:
            continue
        etype = str(it.get("type", "lesson")).strip().lower()
        if etype not in TYPES:
            etype = "lesson"
        conf = str(it.get("confidence", "medium")).strip().lower()
        if conf not in {"high", "medium", "low"}:
            conf = "medium"
        tags = it.get("tags") or []
        tags = [str(t).strip().lower() for t in tags if str(t).strip()]

        entry = Entry(
            id=slugify(f"{etype}-{title}"),
            type=etype,
            title=title,
            body=body,
            tags=sorted(set(tags)),
            source=source,
            confidence=conf,
        )
        entries.append(entry)
    return entries


_TITLE_SIM_THRESHOLD = 0.8
_BODY_SIM_THRESHOLD = 0.85


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9əöüğışç ]+", " ", text.lower()).strip()


def _is_near_duplicate(candidate: Entry, existing: Entry) -> bool:
    """True when ``candidate`` says essentially what ``existing`` already says.

    The reflect loop runs after every job, and repetitive jobs (e.g. the price
    bot answering "qiymət nədir?" daily) kept proposing the same lesson under
    slightly different titles — 16 of 20 queued items were such repeats on
    2026-07-13. Titles are compared fuzzily; bodies as a fallback for
    same-lesson-different-title cases.
    """
    if candidate.id == existing.id:
        return True
    t1, t2 = _norm(candidate.title), _norm(existing.title)
    if t1 and t1 == t2:
        return True
    if difflib.SequenceMatcher(None, t1, t2).ratio() >= _TITLE_SIM_THRESHOLD:
        return True
    b1, b2 = _norm(candidate.body)[:200], _norm(existing.body)[:200]
    if b1 and difflib.SequenceMatcher(None, b1, b2).ratio() >= _BODY_SIM_THRESHOLD:
        return True
    return False


def dedupe_against_store(entries: list[Entry]) -> tuple[list[Entry], list[Entry]]:
    """Split candidates into (fresh, duplicates) vs the trusted store, the
    pending queue, and each other. Never raises — on store errors everything
    passes through as fresh (queueing a dup is cheaper than losing a lesson)."""
    try:
        from .store import all_entries, list_pending, rejected_tombstones

        known: list[Entry] = (
            all_entries() + [e for _, e in list_pending()] + rejected_tombstones()
        )
    except Exception:  # noqa: BLE001
        return entries, []

    fresh: list[Entry] = []
    dups: list[Entry] = []
    for cand in entries:
        if any(_is_near_duplicate(cand, k) for k in known):
            dups.append(cand)
        else:
            fresh.append(cand)
            known.append(cand)  # a batch must not duplicate itself either
    return fresh, dups


def reflect(task: str, result: str, *, source: str = "reflect", commit: bool = False) -> list[Entry]:
    """Distill ``(task, result)`` into candidate lessons and persist them.

    By default writes them to the pending review queue and returns them. Set
    ``commit=True`` only when the caller has already vetted the source.
    Candidates that near-duplicate the store or the queue are dropped silently
    (they add review noise, not knowledge). Returns ``[]`` when no LLM is
    available -- never raises.
    """
    entries = distill(task, result, source=source)
    entries, _dropped = dedupe_against_store(entries)

    if commit:
        from .store import save

        for e in entries:
            save(e, rebuild_index=False)
        if entries:
            from .store import rebuild_index_file

            rebuild_index_file()
    else:
        for e in entries:
            add_pending(e)

    return entries
