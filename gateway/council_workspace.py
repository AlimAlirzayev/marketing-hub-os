"""Operator-visible, consultation-only workspace for the legacy CLI council.

This module deliberately does not route work, change council settings, or call
the legacy ``council.run`` auto-execution path.  It gives the unified Hub a
durable, inspectable view of independent model notes and their synthesis.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import council


ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "output" / "council"
_LOCK = threading.RLock()
_RUNS: dict[str, dict] = {}
_SAFE_ID = re.compile(r"^[0-9]{8}T[0-9]{6}-[a-f0-9]{8}$")


def _member_specs() -> list[tuple[str, object, object]]:
    specs: list[tuple[str, object, object]] = [
        ("Codex", council._ask_codex, council._codex_exe),
        ("Claude Code", council._ask_claude, council._claude_exe),
        ("Gemini CLI", council._ask_gemini, council._gemini_exe),
    ]
    if council._opencode_in_council():
        specs.append(("OpenCode", council._ask_opencode, council._opencode_exe))
    return specs


def availability() -> dict:
    """Return safe member readiness without exposing executable paths."""
    members = []
    for name, _ask, resolver in _member_specs():
        try:
            ready = bool(resolver())
        except Exception:
            ready = False
        members.append({"name": name, "available": ready})
    return {
        "available": any(m["available"] for m in members),
        "mode": "consultation-only",
        "members": members,
        "auto_execute": False,
    }


def _note_dict(note: council.CouncilNote) -> dict:
    return {
        "name": note.name,
        "status": note.status,
        "text": note.text,
        "seconds": round(float(note.seconds), 2),
        "auth": note.auth,
    }


def _public(run: dict) -> dict:
    return json.loads(json.dumps(run, ensure_ascii=False))


def _persist(run: dict) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    target = RUNS_DIR / f"{run['id']}.json"
    temp = RUNS_DIR / f".{run['id']}.tmp"
    temp.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)

    if run.get("status") == "done":
        lines = [
            "# AI Şurası — konsultasiya",
            "",
            f"**Mövzu:** {run['topic']}",
            "",
            "> Bu sessiya yalnız müzakirədir; heç bir auto-icra aparılmayıb.",
            "",
        ]
        for note in run.get("members", []):
            lines.extend([
                f"## {note['name']} — {note['status']}",
                "",
                note.get("text") or "Rəy alınmadı.",
                "",
            ])
        syn = run.get("synthesis") or {}
        lines.extend(["## Yekun sintez", "", syn.get("text") or "Sintez alınmadı.", ""])
        (RUNS_DIR / f"{run['id']}.md").write_text("\n".join(lines), encoding="utf-8")


def _run_consultation(run_id: str) -> None:
    with _LOCK:
        run = _RUNS[run_id]
        run["status"] = "running"
        run["started_at"] = time.time()
        for member in run["members"]:
            if member.get("status") == "queued":
                member["status"] = "running"
        _persist(run)

    specs = _member_specs()
    notes: list[council.CouncilNote] = []
    try:
        with ThreadPoolExecutor(max_workers=max(len(specs), 1)) as pool:
            futures = {pool.submit(ask, run["topic"]): name for name, ask, _ in specs}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    note = future.result()
                except Exception as exc:
                    note = council.CouncilNote(name, "error", f"{type(exc).__name__}: {exc}", 0.0)
                notes.append(note)
                with _LOCK:
                    for member in run["members"]:
                        if member["name"] == name:
                            member.update(_note_dict(note))
                            break
                    _persist(run)

        notes.sort(key=lambda item: item.name)
        if any(note.status == "ok" and note.text.strip() for note in notes):
            synthesis = council._synthesize_with_cli(run["topic"], notes)
        else:
            synthesis = council.CouncilNote(
                "Şura workspace",
                "unavailable",
                "Heç bir üzvdən etibarlı rəy alınmadı. Runtime əlçatanlığını düzəldib sessiyanı yenidən başladın.",
                0.0,
                "deterministic",
            )
        with _LOCK:
            run["members"] = [_note_dict(note) for note in notes]
            run["synthesis"] = _note_dict(synthesis)
            run["status"] = "done"
            run["finished_at"] = time.time()
            _persist(run)
    except Exception as exc:
        with _LOCK:
            run["status"] = "error"
            run["error"] = f"{type(exc).__name__}: {exc}"
            run["finished_at"] = time.time()
            _persist(run)


def start(topic: str) -> dict:
    topic = (topic or "").strip()
    if len(topic) < 10:
        raise ValueError("Müzakirə mövzusu ən azı 10 simvol olmalıdır.")
    if len(topic) > 12_000:
        raise ValueError("Müzakirə mövzusu 12 000 simvoldan uzun ola bilməz.")

    now = time.time()
    run_id = time.strftime("%Y%m%dT%H%M%S", time.localtime(now)) + "-" + uuid.uuid4().hex[:8]
    members = []
    for name, _ask, resolver in _member_specs():
        try:
            ready = bool(resolver())
        except Exception:
            ready = False
        members.append({
            "name": name,
            "status": "queued" if ready else "unavailable",
            "text": "",
            "seconds": 0.0,
            "auth": "",
        })
    run = {
        "id": run_id,
        "topic": topic,
        "status": "queued",
        "mode": "consultation-only",
        "auto_execute": False,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "members": members,
        "synthesis": None,
        "error": None,
    }
    with _LOCK:
        _RUNS[run_id] = run
        _persist(run)
    threading.Thread(target=_run_consultation, args=(run_id,), daemon=True).start()
    return _public(run)


def _load(run_id: str) -> dict | None:
    if not _SAFE_ID.fullmatch(run_id):
        return None
    with _LOCK:
        if run_id in _RUNS:
            return _RUNS[run_id]
    path = RUNS_DIR / f"{run_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    # A live run is always present in _RUNS. Reaching this branch means the
    # panel process restarted, so never leave the operator watching a false
    # "running" state forever.
    if data.get("status") in {"queued", "running"}:
        data["status"] = "error"
        data["error"] = "Panel restart olundu; bu konsultasiya yarımçıq qaldı. Yenidən başladın."
        data["finished_at"] = time.time()
        _persist(data)
    with _LOCK:
        _RUNS.setdefault(run_id, data)
        return _RUNS[run_id]


def get(run_id: str) -> dict | None:
    run = _load(run_id)
    return _public(run) if run else None


def recent(limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit), 50))
    ids = set(_RUNS)
    if RUNS_DIR.is_dir():
        ids.update(path.stem for path in RUNS_DIR.glob("*.json") if _SAFE_ID.fullmatch(path.stem))
    rows = [row for run_id in ids if (row := get(run_id))]
    rows.sort(key=lambda row: row.get("created_at", 0), reverse=True)
    return rows[:limit]
