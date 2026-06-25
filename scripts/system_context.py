"""Generate the canonical Ramin-OS system context.

This script is intentionally local and offline. It reads the service registry,
security notes, and current agent-governance scan, then writes a concise context
brief that Codex, Claude Code, and future agents should read before planning.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "RAMIN_OS_CONTEXT.md"
AGENT_SCAN_PATH = ROOT / "data" / "agent_radar" / "marketing_os_scan.json"
HF_SCAN_PATH = ROOT / "data" / "hf_radar" / "hf_opportunity_scan.json"
SERVICES_PATH = ROOT / "services.json"

CAPABILITY_PATHS = [
    ("Hub / front door", "hub", "Unified Marketing OS entry point and service cards."),
    ("Classic HQ dashboard", "app.py", "Streamlit command center with briefing, agent terminal, RAG, creative studio, and Agent Radar."),
    ("Service registry", "services.json", "Single source of truth for ports, launchers, and hub visibility."),
    ("Service drift audit", "audit_services.py", "Compares services.json with real listening ports and missing dirs."),
    ("Security Guard", "gateway/security.py", "Blocks secrets, destructive actions, payments, unsafe URLs, and unknown scripts."),
    ("Autonomous gateway", "gateway", "Queue, worker, executor, browser tools, AI Council, Telegram delivery path."),
    ("Knowledge Core", "brain", "Recall and reflect loop for institutional memory."),
    ("Daily briefing", "briefing_panel.py", "Executive CX and ads briefing panel."),
    ("Agent Radar", "gateway/agent_radar.py", "Agent governance, sandbox scoring, and automatic Marketing OS scan."),
    ("Hugging Face Opportunity Radar", "gateway/hf_radar.py", "Governed HF model, MCP, Spaces, and private RAG opportunity scoring."),
    ("CX Command Center", "cx-command-center", "Customer complaint radar, AI triage, sentiment, SLA, and draft-only resolution planning."),
    ("Ads Studio", "ads-studio", "Meta ads performance reporting and campaign analytics."),
    ("Conversions API", "meta-capi", "CRM to Meta CAPI and pixel/CAPI gateway."),
    ("GA4 Studio", "ga4-studio", "Website analytics, sessions, conversion and funnel view."),
    ("Influencer Hunter", "influencer-hunter", "Creator shortlist, evidence scoring, brand-safety notes, YouTube proof of concept."),
    ("Price Hunter", "price-hunter", "Competitor pricing and market anomaly monitoring."),
    ("Creative Studio / Atelier", "atelier", "Brand brain, creative lab, critique, prompt and image workflow."),
    ("Copy Studio", "copy-studio", "Voice DNA, copy kits, captions, and critique."),
    ("Publisher", "publisher", "Publish package planning and Postiz/manual routing."),
    ("Audio Studio", "audio-studio", "Music, SFX, TTS, voice references, and audio generation workflows."),
    ("Video Studio", "video-studio", "Video editing, Remotion, motion graphics, and clip pipeline."),
    ("Claude Code control plane", "claude-agents", "Claude subagents, MCP setup, slash command conventions."),
]


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _exists(path: str) -> str:
    return "yes" if (ROOT / path).exists() else "no"


def _services_table(services: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Key | Name | Port | Category | Launch | Target | Health |",
        "|---|---|---:|---|---|---|---|",
    ]
    for service in services:
        lines.append(
            "| {key} | {name} | {port} | {cat} | {launch} | {target} | {health} |".format(
                key=service.get("key", ""),
                name=service.get("name", ""),
                port=service.get("port", ""),
                cat=service.get("cat", ""),
                launch=service.get("launch", ""),
                target=service.get("target", ""),
                health=service.get("health", ""),
            )
        )
    return lines


def _capabilities_table() -> list[str]:
    lines = [
        "| Capability | Path | Present | Role |",
        "|---|---|---|---|",
    ]
    for name, path, role in CAPABILITY_PATHS:
        lines.append(f"| {name} | `{path}` | {_exists(path)} | {role} |")
    return lines


def _agent_radar_summary(scan: dict[str, Any] | None) -> list[str]:
    if not scan:
        return [
            "- Agent Radar scan: not generated yet.",
            "- Run: `python -m gateway.agent_radar autoscan`.",
        ]

    recommendation = scan.get("recommendation", {})
    summary = scan.get("system_fit_summary", {})
    lines = [
        f"- Best variant: {summary.get('best_variant', 'unknown')}",
        f"- Overall rating: {summary.get('overall_rating', 'n/a')}/100",
        f"- Current recommendation: {recommendation.get('name', 'unknown')}",
        f"- Decision: {recommendation.get('decision', 'unknown')}",
        f"- Phase: {recommendation.get('phase', 'unknown')}",
        f"- Automatic job: {recommendation.get('automation_job', 'unknown')}",
    ]
    return lines


def _hf_radar_summary(scan: dict[str, Any] | None) -> list[str]:
    if not scan:
        return [
            "- HF Radar scan: not generated yet.",
            "- Run: `python -m gateway.hf_radar scan`.",
        ]

    recommendation = scan.get("recommendation", {})
    summary = scan.get("system_fit_summary", {})
    lines = [
        f"- Best HF path: {summary.get('best_variant', 'unknown')}",
        f"- Overall rating: {summary.get('overall_rating', 'n/a')}/100",
        f"- Current recommendation: {recommendation.get('name', 'unknown')}",
        f"- Decision: {recommendation.get('decision', 'unknown')}",
        f"- Risk: {recommendation.get('risk_score', 'n/a')}/100",
    ]
    return lines


def render_context(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    services_data = _read_json(SERVICES_PATH, {"services": [], "port_range": []})
    services = services_data.get("services", [])
    scan = _read_json(AGENT_SCAN_PATH, None)
    hf_scan = _read_json(HF_SCAN_PATH, None)

    lines = [
        "# RAMIN OS System Context",
        "",
        f"Generated UTC: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## Mission",
        "",
        "Ramin-OS is the unified Xalq Insurance Digital / Marketing OS. Every Codex, Claude Code,",
        "Gemini, automation, script, and module change must improve this one system, not create",
        "a disconnected side project.",
        "",
        "## Prime Directives",
        "",
        "- Security is the highest law. Prefer a blocked action over an unsafe action.",
        "- Never read, print, copy, upload, or summarize `.env`, `.env.bak`, tokens, cookies, or secrets.",
        "- `services.json` is the single source of truth for service ports and launch metadata.",
        "- Before major work, understand the current system state, relevant module README, and security rules.",
        "- Do not hardcode service lists when the registry can be read.",
        "- Any risky write, send, payment, posting, deletion, or credentialed action needs a checkpoint.",
        "- Keep changes useful to Ramin-OS as a whole: hub, gateway, brain, modules, docs, and tests should stay aligned.",
        "",
        "## Current Service Registry",
        "",
        f"- Port range: {services_data.get('port_range', ['?', '?'])}",
        "",
    ]
    lines.extend(_services_table(services))
    lines.extend(
        [
            "",
            "## Capability Map",
            "",
        ]
    )
    lines.extend(_capabilities_table())
    lines.extend(
        [
            "",
            "## Agent Governance State",
            "",
        ]
    )
    lines.extend(_agent_radar_summary(scan))
    lines.extend(
        [
            "",
            "## Hugging Face Model Governance State",
            "",
        ]
    )
    lines.extend(_hf_radar_summary(hf_scan))
    lines.extend(
        [
            "",
            "## Operating Loop For AI Agents",
            "",
            "1. Read `AGENTS.md`, this file, `SECURITY.md`, and `services.json` before broad changes.",
            "2. Locate the relevant module and its README before editing.",
            "3. Prefer existing patterns and registries over new parallel structures.",
            "4. Make a narrow, testable change; avoid unrelated refactors.",
            "5. Run the smallest meaningful tests, plus wider tests when shared contracts change.",
            "6. Update this context with `python scripts/system_context.py` when the system shape changes.",
            "7. Capture durable lessons through the Brain workflow when a decision should survive the session.",
            "",
            "## Useful Commands",
            "",
            "```powershell",
            "python scripts/system_context.py",
            "python audit_services.py",
            "python -m gateway.agent_radar autoscan-report",
            "python -m gateway.hf_radar report",
            "python -m unittest discover -s tests",
            ".\\START_MARKETING_OS.ps1",
            ".\\STOP_MARKETING_OS.ps1",
            "```",
            "",
            "## Coordination Note",
            "",
            "Codex work, Claude Code work, and generated automation are all part of the same Ramin-OS",
            "improvement stream. Treat prior work as system context unless it is proven obsolete, and",
            "do not undo another agent's changes without understanding why they were made.",
            "",
        ]
    )
    return "\n".join(lines)


def write_context(path: Path = DOC_PATH) -> str:
    text = render_context()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def _timestamp_from_context(text: str) -> datetime | None:
    for line in text.splitlines():
        if not line.startswith("Generated UTC: "):
            continue
        raw = line.replace("Generated UTC: ", "", 1).strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the canonical Ramin-OS system context.")
    parser.add_argument("--stdout", action="store_true", help="Print the context instead of writing it.")
    parser.add_argument("--check", action="store_true", help="Fail if the generated context differs from disk.")
    args = parser.parse_args()

    if args.stdout:
        text = render_context()
        print(text)
        return 0
    if args.check:
        current = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
        text = render_context(_timestamp_from_context(current))
        if current != text:
            print(f"System context is stale: {DOC_PATH}")
            return 1
        print(f"System context is current: {DOC_PATH}")
        return 0
    text = render_context()
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
