"""Safe local readiness audit for Doruk-style Media Studio production.

This module checks the resources we can verify without reading `.env`, printing
credentials, opening OAuth token caches, pinging paid providers, or spending
credits. It is intentionally local/offline: a green result means the workspace
is wired for a human-approved run, not that an external provider was contacted.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import time
from pathlib import Path
from typing import Any

from . import models


ROOT = Path(__file__).resolve().parent.parent
PERMISSIONS_PATH = ROOT / "config" / "agent_permissions.json"


def _rel(path: Path | str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _exists(rel_path: str) -> bool:
    return (ROOT / rel_path).exists()


def _first_glob(pattern: str) -> Path | None:
    hits = sorted(ROOT.glob(pattern), reverse=True)
    return hits[0] if hits else None


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _agent_manifest(agent_id: str) -> dict[str, Any] | None:
    data = _read_json(PERMISSIONS_PATH)
    for agent in data.get("agents") or []:
        if agent.get("id") == agent_id:
            return agent
    return None


def _manifest_controls(agent_id: str) -> dict[str, Any]:
    agent = _agent_manifest(agent_id) or {}
    blocked_inputs = {str(x).casefold() for x in agent.get("blocked_inputs") or []}
    blocked_actions = {str(x).casefold() for x in agent.get("blocked_actions") or []}
    controls = [str(x) for x in agent.get("required_controls") or []]
    return {
        "present": bool(agent),
        "status": agent.get("status", "missing"),
        "blocks_secrets": "secrets" in blocked_inputs or "api keys" in blocked_inputs,
        "blocks_customer_data": "customer data" in blocked_inputs,
        "blocks_public_posting": "post publicly" in blocked_actions,
        "blocks_payments": "handle payments" in blocked_actions or "manage billing" in blocked_actions,
        "requires_cost_control": any("cost" in x.casefold() or "run_cost" in x for x in controls),
    }


def _flora_gateway_readiness() -> dict[str, Any]:
    """Reuse the existing FLORA governance doctor when available.

    gateway.flora_ai is also local/offline and intentionally does not inspect
    credentials. If it is unavailable, Media Studio still reports its own local
    file checks.
    """
    try:
        from gateway import flora_ai  # type: ignore

        return flora_ai.local_readiness()
    except Exception as exc:  # noqa: BLE001
        return {
            "settings_has_flora": False,
            "settings_command_available": False,
            "settings_url_matches_official": False,
            "manifest_has_flora": False,
            "credential_presence_checked": False,
            "note": f"gateway.flora_ai readiness unavailable: {exc}",
        }


def local_readiness() -> dict[str, Any]:
    """Return resource checks that do not read secrets or ping providers."""

    ffmpeg = _first_glob("video-studio/tools/ffmpeg-*/bin/ffmpeg.exe")
    ffprobe = _first_glob("video-studio/tools/ffmpeg-*/bin/ffprobe.exe")
    npx = _first_glob("video-studio/tools/node-*-win-x64/npx.cmd")
    voice_dir = ROOT / "audio-studio" / "voices"
    voice_refs = [
        p for p in voice_dir.glob("*")
        if p.is_file() and p.suffix.casefold() in {".wav", ".mp3", ".m4a", ".ogg"}
    ] if voice_dir.exists() else []

    flora_gateway = _flora_gateway_readiness()
    flora_manifest = _manifest_controls("flora_ai_mcp")

    return {
        "credential_presence_checked": False,
        "oauth_token_cache_checked": False,
        "live_provider_pinged": False,
        "note": (
            "Credentials, .env values, OAuth token caches, and paid providers are "
            "intentionally not inspected by this audit."
        ),
        "flora": {
            "client_exists": _exists("media_studio/flora_client.py"),
            "generator_exists": _exists("media_studio/generate.py"),
            "models_catalog_count": len(models.CATALOG),
            "catalog_refreshed": models.CATALOG_REFRESHED,
            "portable_npx_available": bool(npx) or shutil.which("npx") is not None,
            "portable_npx_path": _rel(npx),
            "gateway_settings_has_flora": bool(flora_gateway.get("settings_has_flora")),
            "gateway_command_available": bool(flora_gateway.get("settings_command_available")),
            "gateway_url_matches_official": bool(flora_gateway.get("settings_url_matches_official")),
            "manifest": flora_manifest,
            "credential_presence_checked": False,
        },
        "local_finish": {
            "ffmpeg_available": bool(ffmpeg) or shutil.which("ffmpeg") is not None,
            "ffmpeg_path": _rel(ffmpeg) if ffmpeg else (shutil.which("ffmpeg") or ""),
            "ffprobe_available": bool(ffprobe) or shutil.which("ffprobe") is not None,
            "ffprobe_path": _rel(ffprobe) if ffprobe else (shutil.which("ffprobe") or ""),
            "remotion_dir_exists": _exists("video-studio/remotion"),
            "video_studio_renderer_exists": _exists("video-studio/render.py"),
        },
        "audio": {
            "audio_studio_exists": _exists("audio-studio/audio_studio.py"),
            "voices_dir_exists": voice_dir.exists(),
            "voice_reference_count": len(voice_refs),
            "edge_tts_importable": _module_available("edge_tts"),
            "gradio_client_importable": _module_available("gradio_client"),
            "premium_keys_checked": False,
        },
        "fallbacks": {
            "mediagen_router_exists": _exists("mediagen/media_router.py"),
            "hf_video_script_exists": _exists("mediagen/hf_video.py"),
            "hf_video_gradio_importable": _module_available("gradio_client"),
            "public_hf_allowed_for_private_data": False,
        },
    }


def _missing(items: list[tuple[str, bool]]) -> list[str]:
    return [name for name, ok in items if not ok]


def _capability(
    key: str,
    label: str,
    status: str,
    detail: str,
    *,
    blockers: list[str] | None = None,
    next_step: str = "",
    approval_required: bool = False,
    paid: bool = False,
    external: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "blockers": blockers or [],
        "next_step": next_step,
        "approval_required": approval_required,
        "paid": paid,
        "external": external,
    }


def capabilities(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    flora = readiness["flora"]
    finish = readiness["local_finish"]
    audio = readiness["audio"]
    fallbacks = readiness["fallbacks"]

    flora_missing = _missing([
        ("media_studio/flora_client.py", flora["client_exists"]),
        ("media_studio/generate.py", flora["generator_exists"]),
        ("portable npx or PATH npx", flora["portable_npx_available"]),
        ("FLORA MCP project settings", flora["gateway_settings_has_flora"]),
        ("FLORA MCP command available", flora["gateway_command_available"]),
        ("FLORA permission manifest", flora["manifest"]["present"]),
        ("FLORA cost controls", flora["manifest"]["requires_cost_control"]),
    ])
    finish_missing = _missing([
        ("portable ffmpeg or PATH ffmpeg", finish["ffmpeg_available"]),
        ("portable ffprobe or PATH ffprobe", finish["ffprobe_available"]),
        ("video-studio/remotion", finish["remotion_dir_exists"]),
    ])
    draft_voice_missing = _missing([
        ("audio-studio/audio_studio.py", audio["audio_studio_exists"]),
        ("edge_tts Python package", audio["edge_tts_importable"]),
    ])
    clone_missing = _missing([
        ("audio-studio/audio_studio.py", audio["audio_studio_exists"]),
        ("gradio_client Python package", audio["gradio_client_importable"]),
        ("at least one approved local voice reference", audio["voice_reference_count"] > 0),
        ("ffmpeg for audio conversion", finish["ffmpeg_available"]),
    ])
    hf_missing = _missing([
        ("mediagen/hf_video.py", fallbacks["hf_video_script_exists"]),
        ("gradio_client Python package", fallbacks["hf_video_gradio_importable"]),
    ])

    return [
        _capability(
            "flora_real_video",
            "Seedance/Kling/Runway/Sora/Veo via FLORA",
            "ready_with_human_cost_gate" if not flora_missing else "needs_setup",
            "Cost-gated real video route. No live provider ping was performed.",
            blockers=flora_missing,
            next_step="Run a plan first, then a human-approved --confirm stage.",
            approval_required=True,
            paid=True,
            external=True,
        ),
        _capability(
            "keyframes_first",
            "Cheap keyframes before video spend",
            "ready_with_human_cost_gate" if not flora_missing else "needs_setup",
            "Generates stills first so the look is approved before expensive motion.",
            blockers=flora_missing,
            next_step="python -m media_studio.generate <slug> --frames --confirm",
            approval_required=True,
            paid=True,
            external=True,
        ),
        _capability(
            "local_finish",
            "Local animatic and deterministic finishing",
            "ready" if not finish_missing else "needs_setup",
            "FFmpeg/Remotion path for animatic, stitching, overlays, captions, and final polish.",
            blockers=finish_missing,
            next_step="python -m media_studio.generate <slug> --animatic",
        ),
        _capability(
            "draft_voice",
            "Free draft Azerbaijani TTS",
            "ready" if not draft_voice_missing else "needs_dependency",
            "Edge TTS is enough for timing drafts; final naturalness still needs ear review.",
            blockers=draft_voice_missing,
            next_step='python audio-studio\\audio_studio.py tts "<script>" --lang az',
        ),
        _capability(
            "natural_voice_clone",
            "Natural Azerbaijani voice clone",
            "ready" if not clone_missing else "needs_reference_or_dependency",
            "Uses a consented local reference clip with OmniVoice; quality is a human-ear call.",
            blockers=clone_missing,
            next_step=(
                'python audio-studio\\audio_studio.py clone "<script>" --lang az'
                "  # house voice (AUDIO_DEFAULT_REF) by default; --ref overrides"
            ),
            external=True,
        ),
        _capability(
            "free_hf_video_fallback",
            "Free public HF video fallback",
            "ready_synthetic_only" if not hf_missing else "needs_dependency",
            "Useful for synthetic tests only; do not send customer data or private strategy.",
            blockers=hf_missing,
            next_step='python mediagen\\hf_video.py --prompt "<synthetic prompt>" --out output.mp4',
            external=True,
        ),
        _capability(
            "premium_voice",
            "ElevenLabs premium voice route",
            "approval_required_not_inspected",
            "Premium keys and credits are intentionally not checked here.",
            blockers=[],
            next_step="Enable only after a human approves key/credit use.",
            approval_required=True,
            paid=True,
            external=True,
        ),
        _capability(
            "publisher",
            "Publisher dry-run handoff",
            "dry_run_only",
            "Final packages can be prepared, but live posting remains a separate checkpoint.",
            blockers=[],
            next_step="Run Publisher dry-run after a finished MP4 exists.",
            approval_required=True,
        ),
    ]


def build_status(package: dict[str, Any] | None = None, *, now: float | None = None) -> dict[str, Any]:
    timestamp = time.time() if now is None else now
    readiness = local_readiness()
    caps = capabilities(readiness)
    cap_by_key = {cap["key"]: cap for cap in caps}
    flora_ready = cap_by_key["flora_real_video"]["status"] == "ready_with_human_cost_gate"
    finish_ready = cap_by_key["local_finish"]["status"] == "ready"
    voice_ready = cap_by_key["natural_voice_clone"]["status"] == "ready" or cap_by_key["draft_voice"]["status"] == "ready"

    commands: dict[str, str] = {}
    stage_plan: dict[str, Any] | None = None
    if package:
        slug = package["slug"]
        commands = {
            "plan": f"python -m media_studio.generate {slug}",
            "first_paid_probe": f"python -m media_studio.generate {slug} --frames --confirm",
            "free_timing_animatic": f"python -m media_studio.generate {slug} --animatic",
            "doruk_like_single_film": f"python -m media_studio.generate {slug} --film --confirm",
            "controlled_beats": f"python -m media_studio.generate {slug} --beats --confirm",
            "full_pro_pipeline": f"python -m media_studio.generate {slug} --pro --confirm",
        }
        try:
            from . import generate

            stage_plan = generate.plan_stages(package)
        except Exception as exc:  # noqa: BLE001
            stage_plan = {"error": str(exc)}

    return {
        "generated_at": timestamp,
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
        "status": (
            "ready_for_human_approved_real_video"
            if flora_ready and voice_ready
            else "draft_ready_missing_some_runtime_resources"
        ),
        "can_make_doruk_like_final_video_after_approval": bool(flora_ready and voice_ready),
        "live_result_guaranteed": False,
        "why_not_guaranteed": (
            "This audit does not ping FLORA, inspect OAuth tokens, check account credits, "
            "or render paid media. It verifies local readiness only."
        ),
        "readiness": readiness,
        "capabilities": caps,
        "commands": commands,
        "stage_plan": stage_plan,
        "recommended_route": [
            "Create UGC pack and approve persona/script.",
            "Run plan command and review exact stage costs.",
            "Generate keyframes first, then approve the look.",
            "Build free animatic for timing.",
            "Run single-film or beats stage only with --confirm.",
            "Generate/clone voice and finish overlays locally.",
            "Publisher dry-run; live posting remains separate.",
        ],
        "local_finish_ready": finish_ready,
    }


def render_status_report(status: dict[str, Any]) -> str:
    lines = [
        "# Media Studio Resource Readiness",
        "",
        f"Generated: {status['generated_at_iso']}",
        f"Status: {status['status']}",
        f"Doruk-like final video after approval: {status['can_make_doruk_like_final_video_after_approval']}",
        f"Live result guaranteed by this audit: {status['live_result_guaranteed']}",
        "",
        "## Safety Boundary",
        "",
        f"- {status['why_not_guaranteed']}",
        f"- {status['readiness']['note']}",
        "",
        "## Capabilities",
        "",
        "| Capability | Status | Blockers |",
        "|---|---|---|",
    ]
    for cap in status["capabilities"]:
        blockers = ", ".join(cap["blockers"]) if cap["blockers"] else "-"
        lines.append(f"| {cap['label']} | {cap['status']} | {blockers} |")

    if status.get("commands"):
        lines += ["", "## Commands", ""]
        for name, command in status["commands"].items():
            lines.append(f"- {name}: `{command}`")

    if status.get("stage_plan") and isinstance(status["stage_plan"], dict):
        stages = status["stage_plan"].get("stages") or []
        if stages:
            lines += ["", "## Stage Cost Plan", "", "| Stage | Credits | Command |", "|---|---:|---|"]
            for stage in stages:
                lines.append(
                    f"| {stage['stage']} | {stage['credits']} | `{stage['cmd']}` |"
                )

    lines += ["", "## Recommended Route", ""]
    lines += [f"- {item}" for item in status["recommended_route"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    parser = argparse.ArgumentParser(description="Safe Media Studio resource readiness audit.")
    parser.add_argument("slug", nargs="?", help="Optional campaign slug for command/stage planning.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    package = None
    if args.slug:
        from . import pipeline

        path = pipeline.CAMPAIGNS / args.slug / "package.json"
        if not path.exists():
            raise SystemExit(f"Package not found: {path}")
        package = json.loads(path.read_text(encoding="utf-8"))

    status = build_status(package)
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(render_status_report(status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
