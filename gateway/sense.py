"""Proprioception — the system's nervous system: live state + event bus + reflex.

The problem this fixes (the operator's "barber" insight): agents start cold and
assert facts from point-in-time *memory snapshots* instead of *live reality* — so
one room doesn't know the other room already cut the hair. The literal cause of the
"TELEGRAM_BOT_TOKEN is empty" mistake.

Three organs:
  * emit()/recent()  — an append-only event bus (the blinking lights): every
    meaningful change writes one redacted line to data/logs/system_events.jsonl.
  * env_status()      — the REFLEX: read the .env reality *now* (masked), so a
    claim about a credential is checked against the body, never against memory.
  * snapshot()/pulse()— proprioception: one live read of env + queue + memory +
    schedules + git + recent events — the server-room board you glance at first.

Dependency-light, every section guarded: sensing must never crash a caller.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_EVENTS_DEFAULT = ROOT / "data" / "logs" / "system_events.jsonl"

CRITICAL_ENV = (
    "TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "GROQ_API_KEY", "APIFY_API_TOKEN",
    "RAPIDAPI_KEY", "YOUTUBE_API_KEY", "GATEWAY_ALLOW_CREDENTIALS",
)


def _events_path() -> Path:
    return Path(os.getenv("SYSTEM_EVENTS_PATH", str(_EVENTS_DEFAULT)))


def _redact(value):
    try:
        from . import security
        return security.redact(value if isinstance(value, str) else json.dumps(value, default=str))
    except Exception:
        return value if isinstance(value, str) else json.dumps(value, default=str)


# --- event bus (blinking lights) ------------------------------------------

def emit(kind: str, summary: str, data: dict | None = None) -> None:
    """Append one redacted event. Never raises — a sensor must not break a caller."""
    try:
        path = _events_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": time.time(), "kind": kind, "summary": _redact(summary)}
        if data:
            record["data"] = {k: _redact(v) for k, v in data.items()}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return


def recent(n: int = 20, kind: str | None = None) -> list[dict]:
    """The last n events (newest last), optionally filtered by kind."""
    path = _events_path()
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if kind and rec.get("kind") != kind:
                continue
            out.append(rec)
    except Exception:
        return out[-n:]
    return out[-n:]


# --- the reflex: read .env reality now, masked ----------------------------

def env_status(keys=CRITICAL_ENV, env_path: str | None = None) -> dict[str, str]:
    """Live, masked status of credentials straight from .env — the anti-stale-
    memory reflex. Use this BEFORE asserting whether a key exists."""
    values: dict[str, str] = {}
    path = Path(env_path or (ROOT / ".env"))
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    out: dict[str, str] = {}
    for k in keys:
        v = values.get(k, os.getenv(k))
        if v is None:
            out[k] = "MISSING"
        elif not v:
            out[k] = "EMPTY"
        else:
            out[k] = f"SET (len={len(v)}, …{v[-4:]})"
    return out


# --- the reflex, part 2: reconcile logged claims against the live body ----

_CLAIM_RE = re.compile(r"([A-Z][A-Z0-9_]{2,})\s+acquired")


def contradictions(snap: dict | None = None) -> list[dict]:
    """Reflex reconciliation: where do logged *claims* disagree with body *reality*?

    The generalization of the TELEGRAM_BOT_TOKEN mistake — never trust a remembered
    claim over the live body. Today it reconciles credential-acquisition events
    ("<KEY> acquired") against the live .env reflex: a claim of acquisition that
    env_status() reports as MISSING/EMPTY is a contradiction the operator must see
    (either the acquisition silently failed, or the event is noise/test-leak). The
    function is the structural reason a future "I have key X" claim gets checked
    against the body, not against memory. Returns [] when consistent; never raises.
    """
    out: list[dict] = []
    seen: set[str] = set()
    try:
        env = (snap or {}).get("env") if snap else None
        if not env:
            env = env_status()
        for ev in recent(50, kind="credential"):
            m = _CLAIM_RE.match(str(ev.get("summary", "")))
            if not m:
                continue
            key = m.group(1)
            if key in seen:
                continue
            reality = env.get(key) or env_status([key]).get(key, "MISSING")
            if not str(reality).startswith("SET"):
                seen.add(key)
                out.append({
                    "kind": "credential",
                    "key": key,
                    "claim": "acquired",
                    "reality": reality,
                    "detail": f"Hadisə jurnalı '{key} acquired' deyir, amma .env reallığı: {reality}.",
                })
    except Exception:
        return out
    return out


# --- proprioception: one live snapshot of the body ------------------------

def _queue_state() -> dict:
    try:
        from . import queue
        counts: dict[str, int] = {}
        for st in ("queued", "running", "done", "error", "awaiting_approval", "rejected"):
            counts[st] = len(queue.list_jobs(status=st, limit=10_000))
        return counts
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:80]}


def _memory_state() -> dict:
    try:
        import sqlite3
        from brain import blackboard
        blackboard.init()
        with sqlite3.connect(str(blackboard._db_path())) as c:
            threads = c.execute("SELECT COUNT(DISTINCT thread_id) FROM memory_turns").fetchone()[0]
            turns = c.execute("SELECT COUNT(*) FROM memory_turns").fetchone()[0]
            ents = c.execute("SELECT COUNT(*) FROM memory_entities").fetchone()[0]
        return {"threads": threads, "turns": turns, "entities": ents}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:80]}


def _schedules_state() -> dict:
    try:
        from . import scheduler
        rows = scheduler.list_schedules()
        return {"total": len(rows), "enabled": sum(1 for r in rows if r.get("enabled"))}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:80]}


def _llm_state() -> dict:
    """Today's LLM spend from the unified router's usage log (no double-logging:
    llm_router.py already records every served call)."""
    import datetime
    log = Path(os.getenv("LLM_USAGE_PATH", str(ROOT / "data" / "logs" / "llm_usage.jsonl")))
    if not log.exists():
        return {"calls_today": 0}
    today = datetime.date.today().isoformat()
    calls = in_tok = out_tok = 0
    cost = 0.0
    by_model: dict[str, int] = {}
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not str(r.get("ts", "")).startswith(today):
                continue
            calls += 1
            in_tok += int(r.get("prompt_tokens", 0) or 0)
            out_tok += int(r.get("completion_tokens", 0) or 0)
            cost += float(r.get("cost_usd", 0.0) or 0.0)
            by_model[r.get("model", "?")] = by_model.get(r.get("model", "?"), 0) + 1
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:80]}
    return {"calls_today": calls, "in_tok": in_tok, "out_tok": out_tok,
            "cost_usd_today": round(cost, 4), "by_model": by_model}


def _git_state() -> dict:
    def _run(args):
        # utf-8 pinned: git subjects carry Azerbaijani + em-dashes, and the locale
        # default (cp1252 on Windows) cannot decode them — see claude_bridge._TEXT_IO.
        return subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                              timeout=8, encoding="utf-8", errors="replace")
    try:
        head = _run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
        dirty = bool(_run(["git", "status", "--porcelain"]).stdout.strip())
        state = {"head": head or "unknown", "dirty": dirty}
        # ahead = local commits not yet mailed; behind = arrived but not pulled.
        # (No fetch here — pure local read; the sync brain does the fetching.)
        try:
            counts = _run(["git", "rev-list", "--left-right", "--count",
                           "@{u}...HEAD"]).stdout.split()
            if len(counts) == 2:
                state["behind"], state["ahead"] = int(counts[0]), int(counts[1])
        except Exception:
            pass
        return state
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:80]}


def snapshot() -> dict:
    """One live read of the system's current body-state. Every section guarded."""
    snap = {
        "ts": time.time(),
        "env": env_status(),
        "queue": _queue_state(),
        "memory": _memory_state(),
        "schedules": _schedules_state(),
        "llm": _llm_state(),
        "git": _git_state(),
        "recent_events": recent(8),
    }
    snap["contradictions"] = contradictions(snap)
    return snap


def pulse() -> str:
    """Human-readable board — the blinking lights, glance at it first."""
    s = snapshot()
    lines = ["=== RAMIN OS — canlı vəziyyət (pulse) ==="]
    lines.append("ENV:")
    for k, v in s["env"].items():
        lamp = "🟢" if v.startswith("SET") else ("⚪" if v == "EMPTY" else "🔴")
        lines.append(f"  {lamp} {k:26} {v}")
    lines.append(f"QUEUE:     {s['queue']}")
    lines.append(f"MEMORY:    {s['memory']}")
    lines.append(f"SCHEDULES: {s['schedules']}")
    lines.append(f"LLM(bugün):{s['llm']}")
    # Which brain actually answers the conversational path. This was invisible once
    # and the system silently served Groq for weeks (MIC_BRAIN defaulted to 'free',
    # so executor._converse never called claude_bridge). Surface it so "why is it
    # dumb" is answerable at a glance, not after tracing the call path.
    mic = os.getenv("MIC_BRAIN", "free").strip().lower()
    if mic == "claude":
        lines.append("BEYİN:     🟢 claude-code (premium) — söhbət Claude-a gedir")
    else:
        lines.append("BEYİN:     🟡 free (Gemini→Groq) — premium üçün MIC_BRAIN=claude")
    lines.append(f"GIT:       {s['git']}")
    if s["recent_events"]:
        lines.append("SON HADİSƏLƏR:")
        for e in s["recent_events"][-5:]:
            lines.append(f"  · [{e.get('kind')}] {e.get('summary')}")
    contra = s.get("contradictions") or []
    if contra:
        lines.append("⚠️  ZİDDİYYƏTLƏR (loglanmış iddia ≠ canlı reallıq):")
        for c in contra:
            lines.append(f"  ✗ {c.get('key')}: {c.get('detail')}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(pulse())
