"""Experiment Arena — "Paralel Gələcəklər" v0: a variant shootout that learns.

The operator's idea ([[project_autonomy_money_roadmap]], Pillar 4): when the system
faces a real improvement, don't build ONE version — build a few, replay past REAL
work against each, compare on time/quality/cost/risk, promote the winner, and write
WHY the losers lost back into the brain as negative reinforcement.

The grand framing (2–3 full vertical builds, auto-promotion into production, a live
comparison Hub) is deliberately NOT built here. The council verdict was: the payoff
part everyone wants (parallel verticals + auto-promote) is the risky, mis-sequenced
part; the FOUNDATION that pays for itself is a thin, honest champion-challenger loop.
So this module is that foundation and only that:

  * runs N variant callables over a set of replay cases (past real inputs),
  * measures quality (pluggable scorer), reliability, latency, cost — no invented
    numbers; a signal that isn't measured is simply absent,
  * ranks with transparent, tunable weights, normalising speed/cost across variants,
  * REFUSES to name a winner when the margin is within noise (no promoting luck),
  * files each loser's structured reason into the brain review queue (add_pending),
  * PROPOSES the winner (sense event + return value) and NEVER auto-applies it —
    promotion is the operator's call (internal-auto/outward-approve; a bad self-
    modification is high blast-radius, so it stays gated behind a human).

Deliberately out of scope (staged behind Pillars 1–3, see the module's decision note
in git): deterministic record/replay of external APIs, auto-promotion to production,
and any live Hub experiment UI. Variants must be replay-SAFE by construction — the
engine does not mock the outside world, and it does not pretend to.

Design mirrors self_review / impact_ledger: pure compute (aggregate / rank / verdict
/ postmortems) split from IO (run_arena / file_postmortems / propose), so the whole
decision path is unit-testable offline with zero tokens and zero side effects.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# Default weights for the composite score. Quality leads, reliability guards against
# a fast-but-broken variant, speed and cost are tie-breakers. Sum is 1.0 by contract.
DEFAULT_WEIGHTS = {"quality": 0.45, "reliability": 0.25, "speed": 0.15, "cost": 0.15}
# Below this composite gap between #1 and #2 the result is called INCONCLUSIVE:
# a margin inside the noise floor is luck, and promoting luck erodes trust faster
# than one good promotion earns it.
DEFAULT_MIN_MARGIN = 0.05


# --- contracts ----------------------------------------------------------------

@dataclass
class ReplayCase:
    """One past real input, optionally with the known-good reference it should
    reproduce (the golden signal). `meta` carries anything the scorer needs."""
    id: str
    input: Any
    reference: Any = None
    meta: dict = field(default_factory=dict)


@dataclass
class Outcome:
    """Optional return wrapper a variant may use to report real cost. A pure
    function can just return its output; an LLM-backed variant returns Outcome so
    its token cost enters the comparison honestly instead of being guessed."""
    output: Any
    cost_usd: float = 0.0


@dataclass
class Variant:
    """A candidate way of doing the work. `run(case_input) -> output | Outcome`.
    Must be replay-SAFE: no un-mocked external side effects during a shootout."""
    name: str
    run: Callable[[Any], Any]


@dataclass
class Trial:
    case_id: str
    ok: bool
    latency_s: float
    cost_usd: float
    quality: float
    error: str | None = None


Scorer = Callable[[ReplayCase, Any], float]  # -> quality in [0, 1]


# --- scorers (pluggable; the default is deterministic, not an LLM judge) -------

def exact_match_scorer(case: ReplayCase, output: Any) -> float:
    """1.0 when the output reproduces the reference exactly, else 0.0. The honest
    default: where a golden reference exists, quality is a fact, not an opinion —
    no LLM judge to game (Goodhart)."""
    return 1.0 if str(output) == str(case.reference) else 0.0


def llm_judge_scorer(rubric: str, *, tier: str = "cheap") -> Scorer:
    """A quality scorer backed by the free LLM router — for work with no clean
    reference (creative copy, summaries). Clearly SECONDARY: the judge is a fuzzy,
    gameable signal, so keep a reference-based check as primary wherever possible.
    Never raises; a judge failure scores 0.0 rather than crashing the shootout."""
    def _score(case: ReplayCase, output: Any) -> float:
        try:
            from llm_router import complete_json  # repo-root router, free-first
            prompt = (
                f"Rubric: {rubric}\nInput: {case.input}\nCandidate output: {output}\n"
                "Rate the candidate's quality from 0 to 100 for this rubric. "
                'Return JSON: {"score": <int 0-100>}'
            )
            data, _model = complete_json(prompt, tier=tier, temperature=0.0)
            return max(0.0, min(1.0, float(data.get("score", 0)) / 100.0))
        except Exception:
            return 0.0
    return _score


# --- pure compute: aggregate -> rank -> verdict -------------------------------

def _minmax(values: list[float], *, higher_better: bool) -> list[float]:
    """Normalise to [0,1] where 1 is always 'best'. All-equal -> all 1.0 (the
    dimension simply doesn't discriminate, so it must not penalise anyone)."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    span = hi - lo
    if higher_better:
        return [(v - lo) / span for v in values]
    return [(hi - v) / span for v in values]


def aggregate(name: str, trials: list[Trial]) -> dict:
    """Pure: collapse a variant's per-case trials into raw metrics. Quality is
    averaged only over successful trials (failures are punished via reliability,
    not double-counted); latency and cost include every trial."""
    n = len(trials)
    ok = [t for t in trials if t.ok]
    reliability = len(ok) / n if n else 0.0
    quality = sum(t.quality for t in ok) / len(ok) if ok else 0.0
    latency = sum(t.latency_s for t in trials) / n if n else 0.0
    cost = sum(t.cost_usd for t in trials)
    return {
        "variant": name,
        "trials": n,
        "passed": len(ok),
        "reliability": round(reliability, 4),
        "quality": round(quality, 4),
        "latency_s": round(latency, 6),
        "cost_usd": round(cost, 6),
        "errors": [t.error for t in trials if t.error][:5],
    }


def rank(aggregates: list[dict], weights: dict | None = None) -> list[dict]:
    """Pure: attach a normalised composite score to each aggregate and sort best
    first. Speed and cost are normalised ACROSS variants so a shootout compares
    like with like; quality and reliability are already absolute in [0,1]."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    if not aggregates:
        return []
    speed = _minmax([a["latency_s"] for a in aggregates], higher_better=False)
    cost = _minmax([a["cost_usd"] for a in aggregates], higher_better=False)
    scored = []
    for a, sp, co in zip(aggregates, speed, cost):
        composite = (w["quality"] * a["quality"] + w["reliability"] * a["reliability"]
                     + w["speed"] * sp + w["cost"] * co)
        scored.append({**a, "speed_score": round(sp, 4), "cost_score": round(co, 4),
                       "composite": round(composite, 4)})
    return sorted(scored, key=lambda a: a["composite"], reverse=True)


@dataclass
class Verdict:
    title: str
    status: str            # "decided" | "inconclusive" | "single"
    winner: str | None
    margin: float
    ranking: list[dict]
    weights: dict
    rationale: str
    postmortems: list[dict] = field(default_factory=list)
    ts: float = field(default_factory=time.time)


def decide(title: str, aggregates: list[dict], *, weights: dict | None = None,
           min_margin: float = DEFAULT_MIN_MARGIN) -> Verdict:
    """Pure: rank the variants and produce a verdict, refusing to name a winner
    when the top two are within the noise floor."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    ranked = rank(aggregates, w)
    if not ranked:
        return Verdict(title, "single", None, 0.0, [], w, "Heç bir variant yoxdur.")
    if len(ranked) == 1:
        top = ranked[0]
        return Verdict(title, "single", top["variant"], 0.0, ranked, w,
                       f"Tək variant ('{top['variant']}') — müqayisə üçün rəqib yoxdur.")
    margin = round(ranked[0]["composite"] - ranked[1]["composite"], 4)
    if margin < min_margin:
        return Verdict(title, "inconclusive", None, margin, ranked, w,
                       (f"Qərarsız: '{ranked[0]['variant']}' və '{ranked[1]['variant']}' "
                        f"fərqi {margin:.3f} < {min_margin} (səs-küy həddi) — "
                        "təsadüfü tətbiq etmirik."),
                       postmortems=[])
    winner, runner = ranked[0], ranked[1]
    rationale = (f"Qalib '{winner['variant']}' (composite {winner['composite']:.3f}) — "
                 f"'{runner['variant']}'-dən {margin:.3f} irəli.")
    return Verdict(title, "decided", winner["variant"], margin, ranked, w, rationale,
                   postmortems=postmortems(title, ranked))


def postmortems(title: str, ranked: list[dict]) -> list[dict]:
    """Pure: for every non-winner, a structured 'why it lost' the brain can recall
    next time — the compounding asset the operator asked for. Each -> {title, body,
    tags}. Names the dimension where the loser fell furthest behind the winner."""
    if len(ranked) < 2:
        return []
    winner = ranked[0]
    out: list[dict] = []
    dims = (("quality", "keyfiyyət"), ("reliability", "etibarlılıq"),
            ("speed_score", "sürət"), ("cost_score", "xərc"))
    for loser in ranked[1:]:
        gaps = [(winner[k] - loser[k], az) for k, az in dims]
        gaps.sort(reverse=True)
        worst_gap, worst_az = gaps[0]
        reasons = ", ".join(
            f"{az} {loser[k]:.2f} vs qalib {winner[k]:.2f}"
            for k, az in dims if (winner[k] - loser[k]) > 0.001
        ) or "ölçülən fərq yoxdur"
        out.append({
            "title": f"Arena: '{loser['variant']}' uduzdu ({title})",
            "body": (f"'{title}' sınağında '{loser['variant']}' variantı "
                     f"'{winner['variant']}'-ə uduzdu. Ən böyük fərq: {worst_az} "
                     f"(Δ{worst_gap:.2f}). Səbəblər: {reasons}. "
                     f"Xətalar: {loser.get('errors') or 'yox'}. "
                     "Gələcəkdə oxşar yanaşmadan çəkinməli və ya qalibin üsulunu "
                     "başlanğıc kimi götürməli."),
            "tags": ["arena", "paralel-gelecekler", _slug(title)],
        })
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40] or "arena"


# --- IO: run trials, file lessons, propose (never apply) ----------------------

def run_arena(title: str, variants: list[Variant], cases: list[ReplayCase], *,
              scorer: Scorer = exact_match_scorer, weights: dict | None = None,
              min_margin: float = DEFAULT_MIN_MARGIN) -> Verdict:
    """Run every variant over every case, then decide. Each trial is timed and its
    exceptions are caught (a crash is data — it counts as a reliability hit, not a
    stack trace that aborts the shootout)."""
    aggregates: list[dict] = []
    for v in variants:
        trials: list[Trial] = []
        for case in cases:
            started = time.perf_counter()
            try:
                result = v.run(case.input)
                output, cost = ((result.output, result.cost_usd)
                                if isinstance(result, Outcome) else (result, 0.0))
                elapsed = time.perf_counter() - started
                try:
                    quality = float(scorer(case, output))
                except Exception as exc:  # a broken scorer must not fail the trial
                    quality = 0.0
                    trials.append(Trial(case.id, False, elapsed, cost, 0.0,
                                        f"scorer error: {exc}"))
                    continue
                trials.append(Trial(case.id, True, elapsed, cost, quality))
            except Exception as exc:  # noqa: BLE001 — variant crash is measured, not raised
                elapsed = time.perf_counter() - started
                trials.append(Trial(case.id, False, elapsed, 0.0, 0.0, str(exc)[:200]))
        aggregates.append(aggregate(v.name, trials))
    return decide(title, aggregates, weights=weights, min_margin=min_margin)


def file_postmortems(verdict: Verdict) -> int:
    """Write each loser's reason to the brain REVIEW QUEUE (never the trusted store
    directly — the curator promotes). Best-effort; returns count filed; never raises."""
    if not verdict.postmortems:
        return 0
    filed = 0
    try:
        import datetime as _dt
        from brain import store
        from brain.store import Entry
        today = _dt.date.today().isoformat()
        for pm in verdict.postmortems:
            try:
                eid = store.slugify(f"arena-{pm['title']}")
                store.add_pending(Entry(
                    id=eid, type="lesson", title=pm["title"], body=pm["body"],
                    tags=sorted(pm["tags"]), source="arena", confidence="low",
                    created=today, updated=today, related=[]))
                filed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[arena] postmortem file skipped: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[arena] brain unavailable: {exc}")
    return filed


def propose(verdict: Verdict) -> dict:
    """Emit the verdict as a PROPOSAL on the event bus and return it. This is the
    hard boundary: the arena recommends, it never promotes. Applying the winner is
    a separate, human-gated action (internal-auto/outward-approve)."""
    try:
        from . import sense
        if verdict.status == "decided":
            summary = (f"{verdict.title}: qalib '{verdict.winner}' "
                       f"(margin {verdict.margin:.3f}) — TƏKLİF, avtomatik tətbiq YOX")
        else:
            summary = f"{verdict.title}: {verdict.status} — qalib təklif edilmədi"
        sense.emit("arena", summary, {"winner": verdict.winner or "",
                                      "status": verdict.status,
                                      "margin": verdict.margin})
    except Exception:
        pass
    return {"title": verdict.title, "status": verdict.status, "winner": verdict.winner,
            "margin": verdict.margin, "applied": False, "auto_apply": False}


# --- human-readable rendering (Azerbaijani) -----------------------------------

def format(verdict: Verdict) -> str:
    lamp = {"decided": "🟢", "inconclusive": "🟡", "single": "⚪"}.get(verdict.status, "·")
    lines = [f"🏁 PARALEL GƏLƏCƏKLƏR — variant sınağı: {verdict.title}",
             "=" * 40,
             f"Nəticə: {lamp} {verdict.status.upper()}"
             + (f" — qalib: {verdict.winner}" if verdict.winner else ""), ""]
    lines.append(f"{'variant':<22}{'keyf':>7}{'etib':>7}{'sürət':>8}{'xərc$':>10}{'composite':>11}")
    lines.append("-" * 65)
    for a in verdict.ranking:
        star = " ◄" if a["variant"] == verdict.winner else ""
        lines.append(f"{a['variant'][:22]:<22}{a['quality']:>7.2f}{a['reliability']:>7.2f}"
                     f"{a.get('speed_score', 0):>8.2f}{a['cost_usd']:>10.4f}"
                     f"{a['composite']:>11.3f}{star}")
    lines += ["", f"→ {verdict.rationale}"]
    w = verdict.weights
    lines.append(f"  (çəkilər: keyf {w['quality']}, etib {w['reliability']}, "
                 f"sürət {w['speed']}, xərc {w['cost']}; margin həddi {DEFAULT_MIN_MARGIN})")
    if verdict.postmortems:
        lines += ["", "ÖYRƏNİLƏN (beyin növbəsinə yazılacaq):"]
        lines += [f"  • {p['title']}" for p in verdict.postmortems]
    lines += ["", "Qeyd: bu TƏKLİFDİR — qalib avtomatik tətbiq edilmir (insan təsdiqi)."]
    return "\n".join(lines)


# --- demo: proves the full loop, zero tokens, zero external calls -------------

def _demo_verdict() -> Verdict:
    """A real, deterministic shootout: two AZ phone-number normalisers over recorded
    raw inputs with known references. One is correct, one is naive — so the ranking,
    the inconclusive guard, and the loser post-mortem all exercise on honest data."""
    cases = [
        ReplayCase("c1", "+994 50 123 45 67", "+994501234567"),
        ReplayCase("c2", "0501234567", "+994501234567"),
        ReplayCase("c3", "994 55 765 43 21", "+994557654321"),
        ReplayCase("c4", "(050) 987-65-43", "+994509876543"),
        ReplayCase("c5", "12345", ""),  # invalid -> empty
    ]

    def strict(raw: str) -> str:
        digits = re.sub(r"\D", "", raw)
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("994"):
            local = digits[3:]
        elif digits.startswith("0"):
            local = digits[1:]
        else:
            local = digits
        return f"+994{local}" if len(local) == 9 else ""

    def naive(raw: str) -> str:
        s = raw.replace(" ", "").replace("-", "")
        return s if s.startswith("+") else f"+994{s}"

    verdict = run_arena(
        "AZ telefon normalizasiyası",
        [Variant("strict-normalizer", strict), Variant("naive-normalizer", naive)],
        cases,
    )
    return verdict


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    v = _demo_verdict()
    print(format(v))
    print("\n[demo] — bu nümunə heç nə tətbiq etmir və beyinə heç nə yazmır.")
