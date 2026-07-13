"""FLORA AI MCP readiness checks for Ramin-OS.

This module does not authenticate to FLORA, does not read `.env`, and does not
inspect OAuth token caches. It verifies that Ramin-OS has the right local MCP
registration and governance controls before a human signs in through OAuth.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from . import security


ROOT_DIR = Path(__file__).resolve().parent.parent
MCP_SETTINGS_PATH = ROOT_DIR / "claude-agents" / ".claude" / "settings.json"
SETUP_MCP_PATH = ROOT_DIR / "scripts" / "setup-mcp.ps1"
PERMISSIONS_PATH = ROOT_DIR / "config" / "agent_permissions.json"
REPORT_PATH = ROOT_DIR / "output" / "flora" / "flora_mcp_readiness.md"

FLORA_AGENT_ID = "flora_ai_mcp"
FLORA_SERVER_NAME = "flora"
FLORA_MCP_URL = "https://agents.flora.ai/mcp"

FLORA_REFERENCE_PATHS = [
    "video-studio/generative_ads/README.md",
    "video-studio/generative_ads/model_matrix.flora.md",
    "social-studio/prompt_kit/model_dialects/flora-video.md",
    "scripts/compile_generative_ad.py",
    "docs/media-studio-automation-action-plan.md",
]

OFFICIAL_REFERENCES = [
    {
        "name": "FLORA MCP",
        "url": "https://developer.flora.ai/mcp/",
        "why": "Official remote MCP overview and supported agent workflows.",
    },
    {
        "name": "Claude Code install",
        "url": "https://developer.flora.ai/mcp/install/claude-code/",
        "why": "Official Claude Code command and project-scoped config shape.",
    },
    {
        "name": "Authentication",
        "url": "https://developer.flora.ai/mcp/authentication/",
        "why": "OAuth and API-key boundary for interactive versus server-side use.",
    },
    {
        "name": "Tools reference",
        "url": "https://developer.flora.ai/mcp/tools/",
        "why": "The MCP exposes search_docs and execute over the FLORA SDK.",
    },
    {
        "name": "Batch with a coding agent",
        "url": "https://developer.flora.ai/mcp/recipes/batch-with-coding-agent/",
        "why": "Shows batch creative generation with explicit cost controls.",
    },
]


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _agent_manifest_entry(manifest: dict[str, Any]) -> dict[str, Any] | None:
    for agent in manifest.get("agents") or []:
        if agent.get("id") == FLORA_AGENT_ID:
            return agent
    return None


def _flora_server_url(server: dict[str, Any]) -> str:
    if not server:
        return ""
    if isinstance(server.get("url"), str):
        return server["url"]
    args = [str(item) for item in server.get("args") or []]
    for item in args:
        if item.startswith("https://") and "flora.ai" in item:
            return item
    return ""


def _flora_transport(server: dict[str, Any]) -> str:
    if not server:
        return "missing"
    if server.get("type") in {"http", "streamable-http"}:
        return str(server.get("type"))
    args = [str(item) for item in server.get("args") or []]
    command = str(server.get("command") or "")
    command_name = _basename(command).casefold()
    if command_name in {"npx", "npx.cmd", "npx.ps1"} and "mcp-remote" in args:
        return "stdio_proxy_to_http"
    if server.get("command"):
        return "stdio"
    return "unknown"


def _command_available(command: str) -> bool:
    if not command:
        return False
    if any(char in command for char in ("\\", "/")):
        return Path(command).exists()
    return shutil.which(command) is not None


def _portable_npx_candidates() -> list[str]:
    tools_dir = ROOT_DIR / "video-studio" / "tools"
    if not tools_dir.exists():
        return []
    return [str(path) for path in sorted(tools_dir.rglob("npx.cmd"), reverse=True)]


def _basename(command: str) -> str:
    """Basename of a command from EITHER OS.

    A POSIX Path does not treat '\\' as a separator, so Path(r'C:\\...\\npx.cmd').name
    returns the WHOLE string on Linux/macOS — which is how the twin's Windows path
    silently defeated every name check here.
    """
    return command.replace("\\", "/").rsplit("/", 1)[-1] if command else ""


def _resolve_command(command: str) -> str:
    """The command that would ACTUALLY launch the MCP on THIS machine.

    settings.json is git-tracked, so it travels between the twins — and it currently
    carries the Windows work PC's absolute path to its own vendored npx. That path
    cannot exist on the VPS or the Mac, yet npx does, so the integration is fine
    there and only the check was wrong. Resolve the way a launcher would: the
    configured command, then a repo-vendored npx, then npx on PATH. "" if none.
    """
    if _command_available(command):
        return command
    for candidate in _portable_npx_candidates():
        if Path(candidate).exists():
            return candidate
    base = _basename(command)
    for name in (base, Path(base).stem if base else "", "npx"):
        if name:
            found = shutil.which(name)
            if found:
                return found
    return ""


def local_readiness() -> dict[str, Any]:
    """Return local FLORA integration readiness without reading credentials."""

    settings = _read_json(MCP_SETTINGS_PATH)
    servers = settings.get("mcpServers") or {}
    flora_server = servers.get(FLORA_SERVER_NAME) or {}
    setup_text = _read_text(SETUP_MCP_PATH)
    manifest = _read_json(PERMISSIONS_PATH)
    manifest_entry = _agent_manifest_entry(manifest)

    reference_hits: list[str] = []
    for rel_path in FLORA_REFERENCE_PATHS:
        path = ROOT_DIR / rel_path
        text = _read_text(path)
        if "flora" in text.casefold():
            reference_hits.append(rel_path)

    blocked_actions = {str(item).casefold() for item in (manifest_entry or {}).get("blocked_actions") or []}
    blocked_inputs = {str(item).casefold() for item in (manifest_entry or {}).get("blocked_inputs") or []}
    required_controls = [str(item) for item in (manifest_entry or {}).get("required_controls") or []]
    flora_url = _flora_server_url(flora_server)
    flora_command = str(flora_server.get("command") or "")
    portable_npx = _portable_npx_candidates()
    resolved_command = _resolve_command(flora_command)

    return {
        "settings_path": str(MCP_SETTINGS_PATH.relative_to(ROOT_DIR)),
        "setup_script_path": str(SETUP_MCP_PATH.relative_to(ROOT_DIR)),
        "manifest_path": str(PERMISSIONS_PATH.relative_to(ROOT_DIR)),
        "settings_has_flora": bool(flora_server),
        "settings_command": flora_command,
        "settings_command_resolved": resolved_command,
        "settings_command_available": bool(resolved_command),
        "settings_transport": _flora_transport(flora_server),
        "settings_url": flora_url,
        "settings_url_matches_official": flora_url == FLORA_MCP_URL,
        "setup_script_has_flora": FLORA_SERVER_NAME in setup_text and FLORA_MCP_URL in setup_text,
        "portable_npx_candidates": portable_npx,
        "manifest_has_flora": manifest_entry is not None,
        "manifest_status": (manifest_entry or {}).get("status", "missing"),
        "manifest_blocks_customer_data": "customer data" in blocked_inputs,
        "manifest_blocks_public_posting": "post publicly" in blocked_actions,
        "manifest_blocks_billing": "manage billing" in blocked_actions or "handle payments" in blocked_actions,
        "manifest_requires_cost_control": any("run_cost" in item or "cost" in item.casefold() for item in required_controls),
        "prompt_workflow_references": reference_hits,
        "credential_presence_checked": False,
        "note": "Credential and OAuth token presence is intentionally not inspected.",
    }


def build_flora_status(now: float | None = None) -> dict[str, Any]:
    timestamp = now if now is not None else time.time()
    readiness = local_readiness()

    configured = (
        readiness["settings_has_flora"]
        and readiness["settings_command_available"]
        and readiness["settings_url_matches_official"]
        and readiness["setup_script_has_flora"]
        and readiness["manifest_has_flora"]
        and readiness["manifest_blocks_customer_data"]
        and readiness["manifest_blocks_public_posting"]
        and readiness["manifest_requires_cost_control"]
    )

    if configured:
        decision = "activate_with_oauth_checkpoint"
        status = "configured_pending_oauth"
        verdict = "ready_for_human_oauth"
    elif readiness["prompt_workflow_references"]:
        decision = "reinforce_before_use"
        status = "prompt_workflows_only"
        verdict = "not_ready"
    else:
        decision = "not_integrated"
        status = "missing"
        verdict = "not_ready"

    return {
        "generated_at": timestamp,
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
        "mission": "Connect FLORA to Ramin-OS as a governed draft-media MCP without exposing secrets.",
        "official_mcp_url": FLORA_MCP_URL,
        "local_readiness": readiness,
        "system_fit_summary": {
            "overall_rating": 89 if configured else 54,
            "best_fit": "Draft creative generation, Technique discovery, thumbnail grids, video plates, and localized batches.",
            "why_it_matters": (
                "Ramin-OS already has copy, brand, video finishing, and publisher QA layers. FLORA fills the "
                "external creative-canvas and premium generative-media gap without replacing our safety gates."
            ),
            "main_risk": "External media generation can consume credits and may receive sensitive briefs if not gated.",
        },
        "recommendation": {
            "status": status,
            "verdict": verdict,
            "decision": decision,
            "next_action": "Run setup-mcp, start the MCP client, list FLORA Techniques, and complete OAuth.",
        },
        "safety_controls": [
            "Do not send secrets, customer data, claims, payment data, internal policies, or unredacted private strategy.",
            "Check run_cost x count before batches or premium model work.",
            "Keep exact text, legal copy, logos, dates, prices, and CTA in deterministic local overlays.",
            "Use FLORA outputs as drafts, then pass final work through Video Studio QA and Publisher dry-run.",
            "Treat OAuth token caches and output URLs as sensitive operational material.",
        ],
        "official_references": OFFICIAL_REFERENCES,
    }


def render_flora_report(status: dict[str, Any]) -> str:
    readiness = status["local_readiness"]
    lines = [
        "# FLORA AI MCP Readiness",
        "",
        f"Generated: {status['generated_at_iso']}",
        "",
        "## Verdict",
        "",
        f"- Status: {status['recommendation']['status']}",
        f"- Verdict: {status['recommendation']['verdict']}",
        f"- Decision: {status['recommendation']['decision']}",
        f"- Overall rating: {status['system_fit_summary']['overall_rating']}/100",
        f"- Best fit: {status['system_fit_summary']['best_fit']}",
        f"- Main risk: {status['system_fit_summary']['main_risk']}",
        "",
        "## Local Checks",
        "",
        f"- Settings has FLORA: {readiness['settings_has_flora']}",
        f"- Settings command: {readiness['settings_command'] or 'missing'}",
        f"- Settings command available: {readiness['settings_command_available']}",
        f"- Settings transport: {readiness['settings_transport']}",
        f"- Settings URL: {readiness['settings_url'] or 'missing'}",
        f"- Official URL match: {readiness['settings_url_matches_official']}",
        f"- Setup script has FLORA: {readiness['setup_script_has_flora']}",
        f"- Permission manifest has FLORA: {readiness['manifest_has_flora']}",
        f"- Manifest status: {readiness['manifest_status']}",
        f"- Blocks customer data: {readiness['manifest_blocks_customer_data']}",
        f"- Blocks public posting: {readiness['manifest_blocks_public_posting']}",
        f"- Requires cost control: {readiness['manifest_requires_cost_control']}",
        f"- Credentials checked: {readiness['credential_presence_checked']}",
        f"- Note: {readiness['note']}",
        "",
        "## Existing Ramin-OS FLORA Touchpoints",
        "",
    ]
    for rel_path in readiness["prompt_workflow_references"]:
        lines.append(f"- `{rel_path}`")
    if not readiness["prompt_workflow_references"]:
        lines.append("- No local prompt workflow references found.")

    lines.extend(
        [
            "",
            "## Activation",
            "",
            "```powershell",
            ".\\scripts\\setup-mcp.ps1",
            "python -m gateway.flora_ai doctor",
            "```",
            "",
            "Then open the MCP client and ask: `List my FLORA Techniques.` The first tool call should open OAuth.",
            "",
            "## Safety Controls",
            "",
        ]
    )
    for control in status["safety_controls"]:
        lines.append(f"- {control}")

    lines.extend(["", "## Official References", ""])
    for ref in status["official_references"]:
        lines.append(f"- [{ref['name']}]({ref['url']}) - {ref['why']}")
    return "\n".join(lines).strip() + "\n"


def run_report() -> dict[str, Any]:
    status = build_flora_status()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_flora_report(status), encoding="utf-8")
    security.audit_event(
        "flora_ai_mcp_readiness",
        security.allow("flora_ai_mcp", "FLORA MCP readiness checked; no generation or OAuth action performed."),
        {
            "status": status["recommendation"]["status"],
            "decision": status["recommendation"]["decision"],
            "report": str(REPORT_PATH),
        },
    )
    return status


def doctor_errors(status: dict[str, Any]) -> list[str]:
    readiness = status["local_readiness"]
    checks = [
        ("settings_has_flora", "FLORA is missing from claude-agents/.claude/settings.json"),
        ("settings_command_available", "FLORA MCP command is not available on PATH or as an absolute path"),
        ("settings_url_matches_official", "FLORA MCP URL does not match the official endpoint"),
        ("setup_script_has_flora", "scripts/setup-mcp.ps1 does not register FLORA"),
        ("manifest_has_flora", "config/agent_permissions.json is missing flora_ai_mcp"),
        ("manifest_blocks_customer_data", "FLORA manifest must block customer data"),
        ("manifest_blocks_public_posting", "FLORA manifest must block public posting"),
        ("manifest_requires_cost_control", "FLORA manifest must require cost control"),
    ]
    return [message for key, message in checks if not readiness.get(key)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ramin-OS FLORA AI MCP readiness checks.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Validate local FLORA MCP readiness without reading credentials.")
    sub.add_parser("report", help="Write and print the FLORA MCP readiness report.")
    sub.add_parser("status-json", help="Print machine-readable FLORA MCP readiness JSON.")
    args = parser.parse_args()

    if args.command == "doctor":
        status = build_flora_status()
        errors = doctor_errors(status)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print("FLORA AI MCP readiness OK. OAuth is still required on first real MCP use.")
        return 0
    if args.command == "report":
        status = run_report()
        print(render_flora_report(status))
        print(f"Report written: {REPORT_PATH}")
        return 0
    if args.command == "status-json":
        print(json.dumps(build_flora_status(), indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
