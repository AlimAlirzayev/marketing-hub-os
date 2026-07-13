"""Persistent certification journey state machine.

The journey engine turns a certificate goal into a gated path. It can coach,
record practice, and prepare handoff checklists. It cannot take the official
exam, answer live questions, book, pay, or enter credentials.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

from . import coach, knowledge, source_verifier


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / "data" / "certification_coach"
JOURNEY_DIR = RUNTIME_DIR / "journeys"
EVENT_LOG_PATH = RUNTIME_DIR / "journey_events.jsonl"

READINESS_SCORE_TARGET = 85
MOCK_SCORE_TARGET = 85

STAGES: tuple[dict[str, str], ...] = (
    {
        "id": "source_verify",
        "title": "Official source",
        "description": "Provider page is reachable, official, and recently checked.",
    },
    {
        "id": "baseline",
        "title": "Baseline",
        "description": "First original self-test or diagnostic score is recorded.",
    },
    {
        "id": "study_sprint",
        "title": "Study sprint",
        "description": "Core study blocks are completed against the roadmap.",
    },
    {
        "id": "drills",
        "title": "Scenario drills",
        "description": "Topic drills turn theory into decisions and artifacts.",
    },
    {
        "id": "mock_exam",
        "title": "Mock gate",
        "description": "Original mock attempts reach the readiness score.",
    },
    {
        "id": "weakness_repair",
        "title": "Weakness repair",
        "description": "Missed topics are repaired before official handoff.",
    },
    {
        "id": "portfolio_proof",
        "title": "Portfolio proof",
        "description": "A work artifact proves the badge has business value.",
    },
    {
        "id": "readiness_gate",
        "title": "Readiness review",
        "description": "The system produces a go/no-go report with blockers.",
    },
    {
        "id": "human_approval",
        "title": "Human approval",
        "description": "The user approves any credentialed, paid, booked, live, or public step.",
    },
    {
        "id": "official_exam_setup",
        "title": "Official setup",
        "description": "The human handles login, registration, payment, and scheduling.",
    },
    {
        "id": "exam_day",
        "title": "Exam day",
        "description": "The human takes the assessment; the agent stays outside.",
    },
    {
        "id": "certificate_capture",
        "title": "Certificate capture",
        "description": "The result, proof artifact, and optional sharing draft are recorded.",
    },
)

SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|cookie|api[_-]?key|authorization|credential|payment|card)",
    re.IGNORECASE,
)
JOURNEY_ID_RE = re.compile(r"^[a-z0-9_.-]+$")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:42] or "journey"


def _redact(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            skey = str(key)
            out[skey] = "[redacted]" if SENSITIVE_KEY_RE.search(skey) else _redact(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [_redact(item, depth=depth + 1) for item in value[:80]]
    if isinstance(value, str):
        return value[:1200]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def _journey_path(journey_id: str) -> Path:
    if not JOURNEY_ID_RE.match(journey_id):
        raise KeyError(f"Unknown journey: {journey_id}")
    return JOURNEY_DIR / f"{journey_id}.json"


def _default_progress() -> dict[str, Any]:
    return {
        "baseline": {"done": False, "score": None, "source": ""},
        "study_tasks_done": 0,
        "drills_done": 0,
        "mock_attempts": [],
        "weakness_repairs_done": 0,
        "portfolio": {"done": False, "summary": ""},
        "readiness_review_requested": False,
        "human_approval": {"done": False, "approved_at": "", "note": ""},
        "exam_setup_done": False,
        "exam_taken": False,
        "certificate_captured": False,
        "certificate_note": "",
    }


def _progress(journey: dict[str, Any]) -> dict[str, Any]:
    progress = journey.setdefault("progress", {})
    defaults = _default_progress()
    for key, value in defaults.items():
        if key not in progress:
            progress[key] = value
    if not isinstance(progress.get("baseline"), dict):
        progress["baseline"] = defaults["baseline"]
    if not isinstance(progress.get("portfolio"), dict):
        progress["portfolio"] = defaults["portfolio"]
    if not isinstance(progress.get("human_approval"), dict):
        progress["human_approval"] = defaults["human_approval"]
    if not isinstance(progress.get("mock_attempts"), list):
        progress["mock_attempts"] = []
    return progress


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _targets(cert: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    difficulty = max(1, min(5, _to_int(cert.get("difficulty"), 3)))
    estimated = max(4, _to_int(cert.get("estimated_hours"), 12))
    weekly = max(2, min(30, _to_int(profile.get("weekly_hours"), 6)))
    topic_count = len(cert.get("prep_topics") or [])
    study_target = max(3, min(10, math.ceil(estimated / weekly) + difficulty))
    drill_target = max(3, min(10, topic_count + (1 if difficulty >= 4 else 0)))
    mock_target = 2 if difficulty >= 3 or cert.get("proctored") else 1
    return {
        "study_tasks": study_target,
        "drills": drill_target,
        "mock_attempts_at_target": mock_target,
        "mock_score": MOCK_SCORE_TARGET,
        "readiness_score": READINESS_SCORE_TARGET,
        "requires_human_approval": True,
    }


def _source_status(cert_id: str) -> dict[str, Any]:
    cached = source_verifier.load_cached()
    checks = {str(item.get("cert_id")): item for item in cached.get("checks", [])}
    check = checks.get(cert_id)
    stale = bool(cached.get("stale", True))
    if not check:
        return {
            "ok": False,
            "stale": stale,
            "verdict": "missing",
            "checked_at": cached.get("summary", {}).get("checked_at", ""),
            "note": "Official source has not been verified for this journey.",
            "check": {},
        }
    verdict = str(check.get("verdict") or "")
    ok = verdict in {"verified", "reachable_official"} and not stale
    return {
        "ok": ok,
        "stale": stale,
        "verdict": verdict,
        "checked_at": cached.get("summary", {}).get("checked_at", ""),
        "note": check.get("note") or "",
        "check": check,
    }


def _weakness_target(progress: dict[str, Any], targets: dict[str, Any]) -> int:
    attempts = list(progress.get("mock_attempts") or [])
    if len(attempts) < targets["mock_attempts_at_target"]:
        return 0
    failed = [item for item in attempts if _to_float(item.get("score")) < targets["mock_score"]]
    weak_ids = {
        str(qid)
        for item in attempts
        for qid in (item.get("weak_question_ids") or [])
        if str(qid)
    }
    if not failed and not weak_ids:
        return 0
    return max(1, min(3, len(failed) or len(weak_ids)))


def _write_journey(journey: dict[str, Any]) -> dict[str, Any]:
    JOURNEY_DIR.mkdir(parents=True, exist_ok=True)
    journey["updated_at"] = _now()
    _journey_path(journey["journey_id"]).write_text(
        json.dumps(journey, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return journey


def _append_event(journey: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    event = {
        "ts": _now(),
        "kind": kind,
        "payload": _redact(payload),
    }
    journey.setdefault("events", []).append(event)
    journey["events"] = journey["events"][-80:]
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log_event = {
        **event,
        "journey_id": journey.get("journey_id"),
        "cert_id": journey.get("cert_id"),
    }
    with EVENT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(log_event, ensure_ascii=False) + "\n")


def _load_raw(journey_id: str) -> dict[str, Any]:
    path = _journey_path(journey_id)
    if not path.exists():
        raise KeyError(f"Unknown journey: {journey_id}")
    try:
        journey = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise KeyError(f"Unreadable journey: {journey_id}") from exc
    _progress(journey)
    return journey


def create_journey(cert_id: str | None, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create and persist a new certification journey."""
    profile = _redact(profile or {})
    if not isinstance(profile, dict):
        profile = {}
    if not cert_id:
        ranked = coach.rank_certifications(profile)
        if not ranked:
            raise ValueError("No certifications are available.")
        cert_id = ranked[0]["cert"]["id"]
    cert = coach.certification(cert_id)
    plan_profile = dict(profile)
    plan_profile["focus_tags"] = plan_profile.get("focus_tags") or list(cert.get("focus_tags", [])[:4])
    plan = coach.build_roadmap(plan_profile)
    knowledge.record_plan(plan_profile, plan)

    journey_id = f"{_safe_slug(cert_id)}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    journey = {
        "schema_version": 1,
        "journey_id": journey_id,
        "cert_id": cert_id,
        "cert_title": cert["title"],
        "provider": cert["provider"],
        "profile": profile,
        "plan": knowledge.enrich_plan(plan, plan_profile),
        "created_at": _now(),
        "updated_at": _now(),
        "progress": _default_progress(),
        "events": [],
    }
    _append_event(journey, "journey_created", {"cert_id": cert_id, "profile": profile})
    _write_journey(journey)
    knowledge.record_event(
        "journey_created",
        {
            "journey_id": journey_id,
            "cert_id": cert_id,
            "title": cert["title"],
        },
    )
    return journey_view(journey_id)


def list_journeys() -> dict[str, Any]:
    JOURNEY_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(JOURNEY_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            view = _view_from_raw(raw, compact=True)
            items.append(view["summary"])
        except Exception:
            continue
    items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {"journeys": items, "count": len(items), "journey_dir": str(JOURNEY_DIR)}


def journey_view(journey_id: str) -> dict[str, Any]:
    return _view_from_raw(_load_raw(journey_id), compact=False)


def _view_from_raw(journey: dict[str, Any], *, compact: bool) -> dict[str, Any]:
    cert = coach.certification(journey["cert_id"])
    progress = _progress(journey)
    targets = _targets(cert, journey.get("profile") or {})
    report = readiness_report(journey)
    stages = _stages(progress, report)
    current = next((stage for stage in stages if stage["status"] in {"current", "blocked"}), stages[-1])
    summary = {
        "journey_id": journey["journey_id"],
        "cert_id": journey["cert_id"],
        "cert_title": journey.get("cert_title") or cert["title"],
        "provider": journey.get("provider") or cert["provider"],
        "created_at": journey.get("created_at", ""),
        "updated_at": journey.get("updated_at", ""),
        "current_stage": current,
        "readiness_score": report["score"],
        "prep_ready": report["prep_ready"],
        "human_handoff_ready": report["human_handoff_ready"],
        "certificate_captured": bool(progress.get("certificate_captured")),
    }
    if compact:
        return {"summary": summary}
    return {
        "summary": summary,
        "certification": cert,
        "profile": journey.get("profile") or {},
        "plan": journey.get("plan") or {},
        "targets": targets,
        "progress": progress,
        "readiness": report,
        "stages": stages,
        "next_action": _next_action(current, progress, report, cert, targets),
        "available_actions": _available_actions(progress, report),
        "events": journey.get("events", [])[-24:],
        "policy": {
            "mode": "exam_prep_only",
            "agent_never": [
                "log in as the user",
                "pay or book exams",
                "open live exam screens",
                "answer live exam questions",
                "submit official exams",
            ],
        },
    }


def readiness_report(journey: dict[str, Any]) -> dict[str, Any]:
    cert = coach.certification(journey["cert_id"])
    progress = _progress(journey)
    targets = _targets(cert, journey.get("profile") or {})
    source = _source_status(journey["cert_id"])
    attempts = list(progress.get("mock_attempts") or [])
    strong_attempts = [
        item for item in attempts if _to_float(item.get("score")) >= targets["mock_score"]
    ]
    weakness_needed = _weakness_target(progress, targets)
    weakness_done = _to_int(progress.get("weakness_repairs_done")) >= weakness_needed
    checks = [
        {
            "id": "official_source",
            "label": "Official source current",
            "ok": source["ok"],
            "weight": 12,
            "detail": source["note"] or source["verdict"],
        },
        {
            "id": "baseline",
            "label": "Baseline recorded",
            "ok": bool(progress.get("baseline", {}).get("done")),
            "weight": 8,
            "detail": f"score {progress.get('baseline', {}).get('score')}",
        },
        {
            "id": "study_sprint",
            "label": "Study blocks complete",
            "ok": _to_int(progress.get("study_tasks_done")) >= targets["study_tasks"],
            "weight": 16,
            "detail": f"{_to_int(progress.get('study_tasks_done'))}/{targets['study_tasks']}",
        },
        {
            "id": "drills",
            "label": "Scenario drills complete",
            "ok": _to_int(progress.get("drills_done")) >= targets["drills"],
            "weight": 12,
            "detail": f"{_to_int(progress.get('drills_done'))}/{targets['drills']}",
        },
        {
            "id": "mock_exam",
            "label": "Mock score gate",
            "ok": len(strong_attempts) >= targets["mock_attempts_at_target"],
            "weight": 24,
            "detail": f"{len(strong_attempts)}/{targets['mock_attempts_at_target']} at {targets['mock_score']}%+",
        },
        {
            "id": "weakness_repair",
            "label": "Weakness repair complete",
            "ok": len(attempts) >= targets["mock_attempts_at_target"] and weakness_done,
            "weight": 12,
            "detail": f"{_to_int(progress.get('weakness_repairs_done'))}/{weakness_needed}",
        },
        {
            "id": "portfolio_proof",
            "label": "Portfolio proof complete",
            "ok": bool(progress.get("portfolio", {}).get("done")),
            "weight": 16,
            "detail": cert.get("portfolio_task", ""),
        },
    ]
    score = sum(item["weight"] for item in checks if item["ok"])
    prep_ready = all(item["ok"] for item in checks) and score >= targets["readiness_score"]
    readiness_requested = bool(progress.get("readiness_review_requested"))
    human_approval = bool(progress.get("human_approval", {}).get("done"))
    handoff_ready = prep_ready and readiness_requested and human_approval
    blockers = [f"{item['label']}: {item['detail']}" for item in checks if not item["ok"]]
    if prep_ready and not readiness_requested:
        blockers.append("Readiness review has not been requested.")
    if prep_ready and readiness_requested and not human_approval:
        blockers.append("Human approval is required before official exam setup.")
    return {
        "score": score,
        "target_score": targets["readiness_score"],
        "mock_score_target": targets["mock_score"],
        "checks": checks,
        "source": source,
        "prep_ready": prep_ready,
        "readiness_review_requested": readiness_requested,
        "human_handoff_ready": handoff_ready,
        "can_start_official_setup": handoff_ready,
        "can_go_to_exam": handoff_ready and bool(progress.get("exam_setup_done")),
        "blocked_reasons": blockers,
        "weakness_repairs_required": weakness_needed,
        "strong_mock_attempts": len(strong_attempts),
    }


def _stages(progress: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    check_ok = {item["id"]: bool(item["ok"]) for item in report["checks"]}
    done = {
        "source_verify": check_ok.get("official_source", False),
        "baseline": check_ok.get("baseline", False),
        "study_sprint": check_ok.get("study_sprint", False),
        "drills": check_ok.get("drills", False),
        "mock_exam": check_ok.get("mock_exam", False),
        "weakness_repair": check_ok.get("weakness_repair", False),
        "portfolio_proof": check_ok.get("portfolio_proof", False),
        "readiness_gate": report["prep_ready"] and bool(progress.get("readiness_review_requested")),
        "human_approval": bool(progress.get("human_approval", {}).get("done")),
        "official_exam_setup": bool(progress.get("exam_setup_done")),
        "exam_day": bool(progress.get("exam_taken")),
        "certificate_capture": bool(progress.get("certificate_captured")),
    }
    first_open = next((stage["id"] for stage in STAGES if not done.get(stage["id"])), STAGES[-1]["id"])
    rendered: list[dict[str, Any]] = []
    for stage in STAGES:
        sid = stage["id"]
        status = "done" if done.get(sid) else "locked"
        if sid == first_open:
            status = "blocked" if sid == "source_verify" and not report["source"]["ok"] else "current"
        rendered.append({**stage, "status": status})
    return rendered


def _next_action(
    current: dict[str, Any],
    progress: dict[str, Any],
    report: dict[str, Any],
    cert: dict[str, Any],
    targets: dict[str, Any],
) -> dict[str, Any]:
    stage_id = current["id"]
    actions = {
        "source_verify": {
            "label": "Verify official source",
            "detail": "Run the source verifier before relying on this certificate path.",
            "action": "run_source_verifier",
        },
        "baseline": {
            "label": "Record baseline",
            "detail": "Take an original mock or diagnostic and record the score.",
            "action": "baseline_submitted",
        },
        "study_sprint": {
            "label": "Complete next study block",
            "detail": f"Finish study block {_to_int(progress.get('study_tasks_done')) + 1}/{targets['study_tasks']}.",
            "action": "study_task_completed",
        },
        "drills": {
            "label": "Complete next scenario drill",
            "detail": f"Finish drill {_to_int(progress.get('drills_done')) + 1}/{targets['drills']}.",
            "action": "drill_completed",
        },
        "mock_exam": {
            "label": "Pass original mock gate",
            "detail": f"Reach {targets['mock_attempts_at_target']} mock attempt(s) at {targets['mock_score']}%+.",
            "action": "take_mock",
        },
        "weakness_repair": {
            "label": "Repair weak topics",
            "detail": f"Complete weakness repair {_to_int(progress.get('weakness_repairs_done')) + 1}/{report['weakness_repairs_required']}.",
            "action": "weakness_repair_completed",
        },
        "portfolio_proof": {
            "label": "Submit portfolio proof",
            "detail": cert.get("portfolio_task", ""),
            "action": "portfolio_completed",
        },
        "readiness_gate": {
            "label": "Request readiness review",
            "detail": "Generate the go/no-go report and freeze blockers before handoff.",
            "action": "readiness_review_requested",
        },
        "human_approval": {
            "label": "Approve official handoff",
            "detail": "Human confirms login/payment/booking/exam launch remain human-only.",
            "action": "human_approval_granted",
        },
        "official_exam_setup": {
            "label": "Mark official setup complete",
            "detail": "Human handled provider login, scheduling, payment if any, and setup.",
            "action": "official_exam_setup_completed",
        },
        "exam_day": {
            "label": "Mark exam taken",
            "detail": "Human took the official assessment without agent assistance.",
            "action": "exam_taken",
        },
        "certificate_capture": {
            "label": "Capture certificate result",
            "detail": "Record result notes and keep public sharing behind approval.",
            "action": "certificate_captured",
        },
    }
    return actions.get(stage_id, actions["source_verify"])


def _available_actions(progress: dict[str, Any], report: dict[str, Any]) -> list[dict[str, str]]:
    actions = [
        {"id": "baseline_submitted", "label": "Baseline done"},
        {"id": "study_task_completed", "label": "Study block done"},
        {"id": "drill_completed", "label": "Scenario drill done"},
        {"id": "weakness_repair_completed", "label": "Weakness repair done"},
        {"id": "portfolio_completed", "label": "Portfolio proof done"},
        {"id": "readiness_review_requested", "label": "Request readiness review"},
    ]
    if report["prep_ready"] and progress.get("readiness_review_requested"):
        actions.append({"id": "human_approval_granted", "label": "Human approval granted"})
    if report["human_handoff_ready"]:
        actions.append({"id": "official_exam_setup_completed", "label": "Official setup done"})
    if report["can_go_to_exam"]:
        actions.append({"id": "exam_taken", "label": "Exam taken by human"})
    if progress.get("exam_taken"):
        actions.append({"id": "certificate_captured", "label": "Certificate/result captured"})
    if progress.get("human_approval", {}).get("done"):
        actions.append({"id": "human_approval_revoked", "label": "Revoke human approval"})
    return actions


def apply_action(journey_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply a safe journey action and return the updated view."""
    payload = _redact(payload or {})
    journey = _load_raw(journey_id)
    progress = _progress(journey)
    cert = coach.certification(journey["cert_id"])
    targets = _targets(cert, journey.get("profile") or {})

    if action == "baseline_submitted":
        progress["baseline"] = {
            "done": True,
            "score": max(0.0, min(100.0, _to_float(payload.get("score"), 0.0))),
            "source": str(payload.get("source") or "manual"),
        }
    elif action == "study_task_completed":
        progress["study_tasks_done"] = min(targets["study_tasks"] * 2, _to_int(progress.get("study_tasks_done")) + 1)
    elif action == "drill_completed":
        progress["drills_done"] = min(targets["drills"] * 2, _to_int(progress.get("drills_done")) + 1)
    elif action == "weakness_repair_completed":
        progress["weakness_repairs_done"] = min(12, _to_int(progress.get("weakness_repairs_done")) + 1)
    elif action == "portfolio_completed":
        progress["portfolio"] = {
            "done": True,
            "summary": str(payload.get("summary") or cert.get("portfolio_task") or "")[:1200],
        }
    elif action == "readiness_review_requested":
        progress["readiness_review_requested"] = True
    elif action == "human_approval_granted":
        report = readiness_report(journey)
        if not report["prep_ready"] or not progress.get("readiness_review_requested"):
            raise ValueError("Human handoff can be approved only after prep readiness and readiness review.")
        progress["human_approval"] = {
            "done": True,
            "approved_at": _now(),
            "note": str(payload.get("note") or "Human approved official handoff.")[:1200],
        }
    elif action == "human_approval_revoked":
        progress["human_approval"] = {"done": False, "approved_at": "", "note": ""}
        progress["exam_setup_done"] = False
    elif action == "official_exam_setup_completed":
        if not progress.get("human_approval", {}).get("done"):
            raise ValueError("Official setup requires human approval first.")
        progress["exam_setup_done"] = True
    elif action == "exam_taken":
        if not progress.get("exam_setup_done"):
            raise ValueError("Exam day can be marked only after official setup.")
        progress["exam_taken"] = True
    elif action == "certificate_captured":
        if not progress.get("exam_taken"):
            raise ValueError("Capture the certificate/result only after the human took the exam.")
        progress["certificate_captured"] = True
        progress["certificate_note"] = str(payload.get("note") or "")[:1200]
    else:
        raise ValueError(f"Unknown journey action: {action}")

    _append_event(journey, action, payload)
    _write_journey(journey)
    knowledge.record_event(
        "journey_action",
        {
            "journey_id": journey_id,
            "cert_id": journey["cert_id"],
            "action": action,
        },
    )
    return journey_view(journey_id)


def record_mock_grade(journey_id: str, grade: dict[str, Any]) -> dict[str, Any]:
    """Attach a mock grade to a journey and update baseline/readiness."""
    journey = _load_raw(journey_id)
    if grade.get("cert_id") != journey.get("cert_id"):
        raise ValueError("Mock grade certification does not match this journey.")
    progress = _progress(journey)
    weak = [item["id"] for item in grade.get("review", []) if not item.get("correct")]
    attempt = {
        "ts": _now(),
        "score": _to_float(grade.get("score")),
        "correct": _to_int(grade.get("correct")),
        "total": _to_int(grade.get("total")),
        "verdict": str(grade.get("verdict") or ""),
        "weak_question_ids": weak[:24],
    }
    progress.setdefault("mock_attempts", []).append(attempt)
    progress["mock_attempts"] = progress["mock_attempts"][-20:]
    if not progress.get("baseline", {}).get("done"):
        progress["baseline"] = {
            "done": True,
            "score": attempt["score"],
            "source": "first_mock",
        }
    _append_event(
        journey,
        "mock_grade_recorded",
        {
            "score": attempt["score"],
            "correct": attempt["correct"],
            "total": attempt["total"],
            "weak_question_ids": weak[:12],
        },
    )
    _write_journey(journey)
    return journey_view(journey_id)
