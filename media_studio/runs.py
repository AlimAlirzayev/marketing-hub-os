"""Studio-runner for Media Studio generation stages.

This gives the web UI a real button workflow without hiding the safety gate:
paid FLORA stages require an explicit stage/slug/credit approval payload before
anything with ``--confirm`` is spawned.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import generate, pipeline, resources


ROOT = Path(__file__).resolve().parent.parent
PAID_STAGES = {"frames", "film", "beats", "oner", "pro"}
FREE_STAGES = {"animatic", "pick"}
ALL_STAGES = PAID_STAGES | FREE_STAGES

_RUNS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def safe_slug(slug: str) -> str:
    safe = (slug or "").replace("..", "").replace("/", "").replace("\\", "").strip()
    if not safe:
        raise ValueError("empty slug")
    return safe


def load_package(slug: str) -> dict[str, Any]:
    safe = safe_slug(slug)
    path = pipeline.CAMPAIGNS / safe / "package.json"
    if not path.exists():
        raise FileNotFoundError(f"package not found: {safe}")
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(rel: str, exists: bool, label: str) -> dict[str, Any]:
    return {"path": rel, "exists": exists, "label": label}


def artifacts(slug: str) -> list[dict[str, Any]]:
    safe = safe_slug(slug)
    folder = pipeline.CAMPAIGNS / safe
    candidates = [
        ("storyboard-board.svg", "Storyboard board"),
        ("ugc-pack/resources-readiness.md", "Resource readiness"),
        ("frames/contact-sheet.html", "Keyframe contact sheet"),
        ("animatic.mp4", "Timing animatic"),
        ("promo-film-master.mp4", "Single-run film"),
        ("promo-beats-master.mp4", "Beat-stitched master"),
    ]
    return [_artifact(rel, (folder / rel).exists(), label) for rel, label in candidates]


def plan_for_slug(slug: str) -> dict[str, Any]:
    pkg = load_package(slug)
    status = resources.build_status(pkg)
    return {
        "slug": pkg["slug"],
        "resources": status,
        "stage_plan": status.get("stage_plan"),
        "commands": status.get("commands", {}),
        "artifacts": artifacts(pkg["slug"]),
    }


def _stage_row(stage_plan: dict[str, Any], stage: str) -> dict[str, Any] | None:
    rows = stage_plan.get("stages") or []
    for row in rows:
        name = str(row.get("stage", "")).casefold()
        if stage == "film" and name.startswith("film"):
            return row
        if stage == "oner" and name.startswith("oner"):
            return row
        if name == stage:
            return row
    return None


def planned_credits(pkg: dict[str, Any], stage: str) -> int:
    stage = stage.casefold()
    if stage not in ALL_STAGES:
        raise ValueError(f"unknown stage: {stage}")
    if stage in FREE_STAGES:
        return 0

    stage_plan = generate.plan_stages(pkg)
    if stage == "pro":
        frames = _stage_row(stage_plan, "frames") or {}
        beats = _stage_row(stage_plan, "beats") or {}
        return int(frames.get("credits") or 0) + int(beats.get("credits") or 0)
    row = _stage_row(stage_plan, stage)
    if row is None:
        raise ValueError(f"stage not in plan: {stage}")
    return int(row.get("credits") or 0)


def validate_approval(
    pkg: dict[str, Any],
    *,
    stage: str,
    confirm_spend: bool,
    approved_slug: str | None,
    approved_stage: str | None,
    approved_credits: int | None,
) -> int:
    stage = stage.casefold()
    credits = planned_credits(pkg, stage)
    if stage not in PAID_STAGES:
        return credits
    if not confirm_spend:
        raise PermissionError("paid stage requires confirm_spend=true")
    if approved_slug != pkg["slug"]:
        raise PermissionError("approved_slug does not match package")
    if (approved_stage or "").casefold() != stage:
        raise PermissionError("approved_stage does not match requested stage")
    if int(approved_credits if approved_credits is not None else -1) != credits:
        raise PermissionError("approved_credits does not match current plan")
    return credits


def build_command(slug: str, stage: str, *, picks: str | None = None) -> list[str]:
    safe = safe_slug(slug)
    stage = stage.casefold()
    if stage not in ALL_STAGES:
        raise ValueError(f"unknown stage: {stage}")
    cmd = [sys.executable, "-m", "media_studio.generate", safe]
    if stage == "pick":
        if not picks:
            raise ValueError("pick stage requires picks")
        cmd += ["--pick", picks]
        return cmd
    cmd.append(f"--{stage}")
    if stage in PAID_STAGES:
        cmd.append("--confirm")
    return cmd


def _tail(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _public(run: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in run.items() if k not in {"proc"}}
    out["log_tail"] = _tail(Path(run["log_path"]))
    out["artifacts"] = artifacts(run["slug"])
    return out


def _watch(run_id: str, proc: subprocess.Popen, log_handle) -> None:
    exit_code = proc.wait()
    log_handle.close()
    with _LOCK:
        run = _RUNS.get(run_id)
        if run:
            run["status"] = "succeeded" if exit_code == 0 else "failed"
            run["exit_code"] = exit_code
            run["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def start_run(
    slug: str,
    *,
    stage: str,
    confirm_spend: bool = False,
    approved_slug: str | None = None,
    approved_stage: str | None = None,
    approved_credits: int | None = None,
    picks: str | None = None,
) -> dict[str, Any]:
    pkg = load_package(slug)
    stage = stage.casefold()
    credits = validate_approval(
        pkg,
        stage=stage,
        confirm_spend=confirm_spend,
        approved_slug=approved_slug,
        approved_stage=approved_stage,
        approved_credits=approved_credits,
    )
    cmd = build_command(pkg["slug"], stage, picks=picks)

    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run_dir = pipeline.CAMPAIGNS / pkg["slug"] / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / f"{run_id}-{stage}.log"
    log_handle = log_path.open("w", encoding="utf-8", errors="replace")
    log_handle.write(
        f"Media Studio stage run\nslug={pkg['slug']}\nstage={stage}\ncredits={credits}\n"
        f"started_at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
    )
    log_handle.flush()

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=os.environ.copy(),
    )
    run = {
        "run_id": run_id,
        "slug": pkg["slug"],
        "stage": stage,
        "status": "running",
        "pid": proc.pid,
        "exit_code": None,
        "credits": credits,
        "paid": stage in PAID_STAGES,
        "approval": {
            "confirm_spend": bool(confirm_spend),
            "approved_slug": approved_slug,
            "approved_stage": approved_stage,
            "approved_credits": approved_credits,
        },
        "cmd": " ".join(cmd),
        "log_path": str(log_path),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ended_at": None,
        "proc": proc,
    }
    with _LOCK:
        _RUNS[run_id] = run
    threading.Thread(target=_watch, args=(run_id, proc, log_handle), daemon=True).start()
    return _public(run)


def get_run(run_id: str) -> dict[str, Any]:
    with _LOCK:
        run = _RUNS.get(run_id)
        if not run:
            raise FileNotFoundError(run_id)
        return _public(run)
