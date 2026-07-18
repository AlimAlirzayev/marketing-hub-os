"""Curate: the brain reviews its OWN pending lessons.

The reflect loop proposes lessons after every job, but review was manual-only
(``brain review`` on the server) and nobody ran it — 297 suggestions piled up
by 2026-07-18 while the advisor nagged the operator daily about a queue he
could not clear from Telegram. Charter decision (Alim, 2026-07-18): learning
must compound WITHOUT the operator babysitting a queue. An LLM judges each
pending suggestion against a strict usefulness rubric, promotes the good ones
into the trusted store, rejects the noise (tombstoned, so it can never be
re-proposed), and the operator gets a short plain-Azerbaijani digest instead
of a chore.

Safety properties, in order of importance:
- **Never lose knowledge silently.** An item is only dropped by an explicit
  LLM verdict; anything unjudged (LLM down, malformed reply, missing index)
  stays in the queue for the next run. Rejects keep their text in the
  ``_rejected.jsonl`` tombstone log.
- **Protect the trusted store.** Junk lessons get injected into every
  execution prompt via recall, so the rubric is biased to DROP: generic
  truisms and one-off facts die; only specific, reusable knowledge survives.
- **Never break a job.** ``curate()`` returns a summary dict and does not
  raise; the rail degrades to an honest "could not review" message.
"""

from __future__ import annotations

import json
import re

from .store import Entry, approve_pending, list_pending, reject_pending

# Batch size balances prompt length against call count: ~20 compact lessons
# fit comfortably in one cheap-tier call, and 300 backlogged items still
# resolve in ~15 calls.
BATCH_SIZE = 20

# Hard cap per run so a runaway queue can never turn one scheduled job into
# hundreds of LLM calls.
MAX_ITEMS_PER_RUN = 400

_PROMPT = """You are the knowledge curator of RAMIN OS — an autonomous marketing/business
operations system run by a solo operator (insurance-sector day job + freelance
digital marketing, Azerbaijan market, cost-conscious, Telegram-first).

Below are auto-distilled lesson SUGGESTIONS from finished jobs. Decide for each
one whether it deserves a place in the system's trusted long-term memory.
Approved lessons get injected into future execution prompts, so every KEEP has
a recurring cost: junk pollutes every future job.

KEEP only if ALL are true:
- SPECIFIC: the body names something concrete about THIS system or its market —
  a particular tool/studio/script/API, the Azerbaijani or insurance market, a
  named workflow or constraint. The paste test: if the sentence would be
  equally true pasted into any other company's AI system, it fails this.
- actionable: the next similar job would concretely be done differently;
- non-obvious: a competent operator/agent would NOT already know it;
- durable: still useful months from now.

DROP everything else, especially: generic AI/engineering truisms ("check
dependencies before running", "verify errors indicate bugs", "interpret
ambiguous input in context"), generic marketing craft any copywriter knows
("use bullet points for benefits", "keep a reassuring tone"), restatements of
common knowledge ("insurance companies manage risk"), one-off facts tied to a
single job, and vague advice with no concrete action.

Calibration: the reflect loop over-proposes; in practice only about 1 in 5
suggestions deserves KEEP. If you find yourself keeping most of a batch, your
bar is too low. When in doubt, DROP — rejected text is tombstoned, not lost.

Return STRICT JSON, no prose, no code fence:
{"verdicts": [{"i": <item number>, "v": "KEEP" | "DROP"}]}
Every item number from the list must appear exactly once.

--- SUGGESTIONS ---
{items}
"""


def _llm_json(prompt: str) -> str | None:
    """One cheap-tier router call. Returns None on any failure — the caller
    treats that batch as unjudged and leaves it in the queue."""
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        import llm_router
        text, _model = llm_router.complete(
            prompt, tier="cheap", want_json=True, temperature=0.1
        )
        return (text or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def _parse_verdicts(raw: str) -> dict[int, str]:
    """Parse the strict-JSON verdict reply into {item_number: KEEP|DROP}.

    Anything unparseable yields an empty/partial map — unmapped items simply
    stay pending, so a bad reply can never cause a wrong drop."""
    if not raw:
        return {}
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    if not raw.startswith("{"):
        brace = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace:
            raw = brace.group(0)
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}
    verdicts = data.get("verdicts") if isinstance(data, dict) else None
    if not isinstance(verdicts, list):
        return {}
    out: dict[int, str] = {}
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        try:
            i = int(v.get("i"))
        except (TypeError, ValueError):
            continue
        verdict = str(v.get("v", "")).strip().upper()
        if verdict in {"KEEP", "DROP"}:
            out[i] = verdict
    return out


def _is_duplicate(entry: Entry) -> bool:
    """True when ``entry`` near-duplicates something already in the trusted store
    or tombstoned, reusing the reflect loop's own ``_is_near_duplicate`` so every
    path shares one definition of 'the same lesson'.

    Deliberately compares against the trusted store (not the pending queue): the
    item under judgement is itself still queued, so a queue-wide check would
    match it against itself. Because approvals write to the store immediately,
    the store already contains this run's earlier keeps — so cross-batch
    duplicates are still caught. Fails open (False) so a detector error can never
    block a legitimate keep."""
    try:
        from . import capture
        from .store import all_entries, rejected_tombstones

        known = all_entries() + rejected_tombstones()
        return any(capture._is_near_duplicate(entry, k) for k in known)
    except Exception:  # noqa: BLE001
        return False


def _format_batch(batch: list[Entry]) -> str:
    lines = []
    for n, entry in enumerate(batch, 1):
        lines.append(
            f"{n}. [{entry.type}] {entry.title}\n   {entry.body.strip()[:400]}"
        )
    return "\n".join(lines)


def curate(*, limit: int | None = None, dry_run: bool = False) -> dict:
    """Review the pending queue autonomously. Returns a summary dict:

    ``{"reviewed", "kept", "dropped", "left", "kept_titles", "llm_ok"}``

    ``left`` counts items that stay pending (not yet reached, or their batch
    got no usable LLM reply). ``llm_ok`` is False when not a single batch got
    a usable reply — the digest uses it to report honestly.
    """
    pending = list_pending()
    cap = min(limit or MAX_ITEMS_PER_RUN, MAX_ITEMS_PER_RUN)
    todo, rest = pending[:cap], pending[cap:]

    kept: list[Entry] = []
    dropped: list[Entry] = []
    unjudged = len(rest)
    any_reply = False

    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start:start + BATCH_SIZE]
        entries = [e for _, e in batch]
        prompt = _PROMPT.replace("{items}", _format_batch(entries))
        verdicts = _parse_verdicts(_llm_json(prompt) or "")
        if not verdicts:
            unjudged += len(batch)
            continue
        any_reply = True
        for n, (path, entry) in enumerate(batch, 1):
            verdict = verdicts.get(n)
            if verdict == "KEEP":
                # A KEEP still passes the same near-duplicate gate reflect uses,
                # against the trusted store, the queue, and tombstones. Because
                # approvals write to the store immediately, this also collapses
                # cross-batch duplicates within one run (batch 7 sees batch 3's
                # keeps). A duplicate KEEP is tombstoned, not promoted — the
                # store must not accumulate ten ways to say the same lesson.
                if _is_duplicate(entry):
                    if not dry_run:
                        reject_pending(path)
                    dropped.append(entry)
                    continue
                if not dry_run:
                    approve_pending(path)
                kept.append(entry)
            elif verdict == "DROP":
                if not dry_run:
                    reject_pending(path)
                dropped.append(entry)
            else:
                unjudged += 1

    return {
        "reviewed": len(kept) + len(dropped),
        "kept": len(kept),
        "dropped": len(dropped),
        "left": unjudged,
        "kept_titles": [e.title for e in kept],
        "llm_ok": any_reply or not todo,
        "dry_run": dry_run,
    }


_CONF_RANK = {"high": 3, "medium": 2, "low": 1}


def dedupe_store(*, dry_run: bool = False) -> dict:
    """Collapse near-duplicate entries already in the trusted store.

    A one-time repair for clutter that predates the curator's keep-time gate
    (e.g. the first bulk curation judged batches independently and let ten
    near-identical currency/price lessons through). Uses the reflect loop's own
    ``_is_near_duplicate`` so 'duplicate' means exactly what it means everywhere
    else. Within a cluster the highest-confidence entry survives; ties break to
    the earliest ``created`` (the original). Returns
    ``{"kept", "removed", "removed_titles"}``. The store is not git-tracked, so
    callers should back it up first — this deletes files.
    """
    from . import capture
    from .store import all_entries, delete

    entries = sorted(all_entries(), key=lambda e: (e.created, e.id))
    survivors: list[Entry] = []
    removed: list[Entry] = []

    for cand in entries:
        dup_of = next(
            (s for s in survivors if capture._is_near_duplicate(cand, s)), None
        )
        if dup_of is None:
            survivors.append(cand)
            continue
        # Keep whichever is higher-confidence; on a tie the survivor (earlier) wins.
        if _CONF_RANK.get(cand.confidence, 2) > _CONF_RANK.get(dup_of.confidence, 2):
            survivors.remove(dup_of)
            removed.append(dup_of)
            survivors.append(cand)
        else:
            removed.append(cand)

    if not dry_run:
        from .store import rebuild_index_file
        for e in removed:
            delete(e.id)
        rebuild_index_file()

    return {
        "kept": len(survivors),
        "removed": len(removed),
        "removed_titles": [e.title for e in removed],
    }


def report(*, limit: int | None = None) -> str:
    """Rail entry point: curate, then render the operator digest (Azerbaijani
    runtime output is allowed by the language policy — this text goes straight
    to Alim's Telegram)."""
    pending_before = len(list_pending())
    if pending_before == 0:
        return "📚 Beyin təftişi: dərs növbəsi boşdur — bu gün yeni dərs yoxdur."

    s = curate(limit=limit)
    if not s["llm_ok"]:
        return (
            "📚 Beyin təftişi: LLM əlçatan olmadığı üçün bu gün dərsləri "
            f"qiymətləndirə bilmədim — {pending_before} dərs növbədə qalır, "
            "sabah yenidən cəhd edəcəm."
        )

    lines = [
        "📚 **Beyin təftişi** — sistem öz dərslərini nəzərdən keçirdi",
        f"Baxıldı: {s['reviewed']} · Qəbul: {s['kept']} · "
        f"Atıldı: {s['dropped']} · Qaldı: {s['left']}",
    ]
    if s["kept_titles"]:
        lines.append("\nYaddaşa qəbul olunan dərslər:")
        shown = s["kept_titles"][:10]
        lines += [f"• {t}" for t in shown]
        if len(s["kept_titles"]) > len(shown):
            lines.append(f"… və daha {len(s['kept_titles']) - len(shown)}")
    else:
        lines.append("Bu partiyada yaddaşa layiq dərs çıxmadı — hamısı ümumi/təkrar idi.")
    return "\n".join(lines)
