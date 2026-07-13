"""Notion Workers readiness checks for Ramin-OS.

This module never authenticates to Notion, never deploys a worker, never reads
`.env`, and never inspects token stores. It only verifies local source,
tooling, and governance controls.
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
WORKER_DIR = ROOT_DIR / "notion-workers" / "ramin-os-agent-tools"
WORKER_SRC_PATH = WORKER_DIR / "src" / "index.ts"
WORKER_PACKAGE_PATH = WORKER_DIR / "package.json"
SETUP_SCRIPT_PATH = ROOT_DIR / "scripts" / "setup-notion-workers.ps1"
CLI_WRAPPER_PATH = ROOT_DIR / "scripts" / "notion-cli.ps1"
NTN_COMMAND_PATH = ROOT_DIR / ".tools" / "notion-cli" / "ntn.cmd"
PERMISSIONS_PATH = ROOT_DIR / "config" / "agent_permissions.json"
REPORT_PATH = ROOT_DIR / "output" / "notion-workers" / "notion_workers_readiness.md"

NOTION_AGENT_ID = "notion_workers"
EXPECTED_TOOLS = ("screenRaminOsAction", "prepareRaminOsHandoff")

OFFICIAL_REFERENCES = [
    {
        "name": "Notion Workers overview",
        "url": "https://developers.notion.com/workers/get-started/overview",
        "why": "Explains Workers as Notion-hosted tools, syncs, and webhooks.",
    },
    {
        "name": "Quickstart",
        "url": "https://developers.notion.com/workers/get-started/quickstart",
        "why": "Official CLI, scaffold, local test, deploy, and Custom Agent setup flow.",
    },
    {
        "name": "Agent tools",
        "url": "https://developers.notion.com/workers/guides/tools",
        "why": "Tool schema, execute handlers, output schemas, and read-only hints.",
    },
    {
        "name": "Secrets",
        "url": "https://developers.notion.com/workers/guides/secrets",
        "why": "Worker secret storage and env commands that require human checkpoints.",
    },
    {
        "name": "CLI commands",
        "url": "https://developers.notion.com/cli/reference/commands",
        "why": "Reference for deploy, exec, sync, env, OAuth, and webhook commands.",
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
        if agent.get("id") == NOTION_AGENT_ID:
            return agent
    return None


def _command_available(command: Path | str) -> bool:
    command_text = str(command)
    if any(char in command_text for char in ("\\", "/")):
        return Path(command_text).exists()
    return shutil.which(command_text) is not None


def _portable_node_available() -> bool:
    tools_dir = ROOT_DIR / "video-studio" / "tools"
    return tools_dir.exists() and any(tools_dir.rglob("node.exe"))


def local_readiness() -> dict[str, Any]:
    """Return local Notion Workers readiness without checking credentials."""

    manifest = _read_json(PERMISSIONS_PATH)
    manifest_entry = _agent_manifest_entry(manifest)
    package = _read_json(WORKER_PACKAGE_PATH)
    source_text = _read_text(WORKER_SRC_PATH)

    blocked_actions = {str(item).casefold() for item in (manifest_entry or {}).get("blocked_actions") or []}
    blocked_inputs = {str(item).casefold() for item in (manifest_entry or {}).get("blocked_inputs") or []}
    required_controls = [str(item) for item in (manifest_entry or {}).get("required_controls") or []]
    dependencies = package.get("dependencies") or {}

    tool_hits = {tool: tool in source_text for tool in EXPECTED_TOOLS}

    return {
        "worker_dir": str(WORKER_DIR.relative_to(ROOT_DIR)),
        "worker_project_exists": WORKER_DIR.exists(),
        "package_name": package.get("name", "missing"),
        "package_has_workers_sdk": "@notionhq/workers" in dependencies,
        "source_path": str(WORKER_SRC_PATH.relative_to(ROOT_DIR)),
        "source_has_expected_tools": all(tool_hits.values()),
        "tool_hits": tool_hits,
        "tools_are_read_only_hinted": source_text.count("readOnlyHint: true") >= len(EXPECTED_TOOLS),
        "setup_script_exists": SETUP_SCRIPT_PATH.exists(),
        "cli_wrapper_exists": CLI_WRAPPER_PATH.exists(),
        "repo_local_cli_installed": NTN_COMMAND_PATH.exists(),
        "repo_local_cli_command": str(NTN_COMMAND_PATH.relative_to(ROOT_DIR)),
        "repo_local_cli_available": _command_available(NTN_COMMAND_PATH),
        "global_ntn_available": shutil.which("ntn") is not None,
        "portable_node_available": _portable_node_available(),
        "local_exec_smoke_tested": False,
        "local_exec_note": "Doctor does not execute worker tools. On Windows, ntn 0.18.1 local exec can fail with ERR_UNSUPPORTED_ESM_URL_SCHEME.",
        "manifest_has_notion_workers": manifest_entry is not None,
        "manifest_status": (manifest_entry or {}).get("status", "missing"),
        "manifest_blocks_secrets": "secrets" in blocked_inputs and ".env content" in blocked_inputs,
        "manifest_blocks_customer_data": "customer data" in blocked_inputs,
        "manifest_blocks_public_posting": "post publicly" in blocked_actions,
        "manifest_blocks_payments": "handle payments" in blocked_actions or "access payments" in blocked_actions,
        "manifest_blocks_deploy_without_approval": "deploy workers without approval" in blocked_actions,
        "manifest_requires_no_dotenv_tests": any("--no-dotenv" in item for item in required_controls),
        "credential_presence_checked": False,
        "notion_login_checked": False,
        "note": "Credentials, .env files, OAuth token stores, and Notion login state are intentionally not inspected.",
    }


def build_notion_workers_status(now: float | None = None) -> dict[str, Any]:
    timestamp = now if now is not None else time.time()
    readiness = local_readiness()

    configured = (
        readiness["worker_project_exists"]
        and readiness["package_has_workers_sdk"]
        and readiness["source_has_expected_tools"]
        and readiness["tools_are_read_only_hinted"]
        and readiness["setup_script_exists"]
        and readiness["cli_wrapper_exists"]
        and readiness["manifest_has_notion_workers"]
        and readiness["manifest_blocks_secrets"]
        and readiness["manifest_blocks_customer_data"]
        and readiness["manifest_blocks_public_posting"]
        and readiness["manifest_blocks_deploy_without_approval"]
        and readiness["manifest_requires_no_dotenv_tests"]
    )
    cli_ready = readiness["repo_local_cli_available"] or readiness["global_ntn_available"]

    if configured and cli_ready:
        status = "configured_cli_installed"
        verdict = "ready_for_typecheck_and_human_checkpoint"
        decision = "activate_after_human_login_deploy_checkpoint"
    elif configured:
        status = "configured_needs_cli_setup"
        verdict = "source_ready"
        decision = "run_setup_before_local_tests"
    else:
        status = "not_integrated"
        verdict = "not_ready"
        decision = "reinforce_before_use"

    return {
        "generated_at": timestamp,
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
        "mission": "Connect Notion Custom Agents to Ramin-OS through governed draft/read-only Workers tools.",
        "local_readiness": readiness,
        "system_fit_summary": {
            "overall_rating": 86 if configured else 48,
            "best_fit": "Notion-side briefing, risk screening, and handoff preparation before work enters the Ramin-OS gateway.",
            "why_it_matters": (
                "Notion can be a planning surface for campaign and operations notes, while Ramin-OS remains the "
                "execution, approval, memory, and QA spine."
            ),
            "main_risk": "Notion-hosted tools can drift into secrets, customer data, publishing, or production writes if not gated.",
        },
        "recommendation": {
            "status": status,
            "verdict": verdict,
            "decision": decision,
            "next_action": "Run setup and type-check; use local --no-dotenv exec where the beta CLI supports it, then pause before Notion login/deploy.",
        },
        "safety_controls": [
            "Do not send secrets, .env content, customer data, claims, policies, payment data, or private strategy.",
            "Keep tools side-effect-free unless a new manifest entry and approval checkpoint authorizes more.",
            "Use --no-dotenv for local smoke tests by default.",
            "Treat worker deployment, secrets, OAuth, real sync triggers, and webhook URLs as checkpoint actions.",
            "Syncs must preview before writing and webhooks must verify provider signatures.",
        ],
        "official_references": OFFICIAL_REFERENCES,
    }


def render_notion_workers_report(status: dict[str, Any]) -> str:
    readiness = status["local_readiness"]
    lines = [
        "# Notion Workers Readiness",
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
        f"- Worker project exists: {readiness['worker_project_exists']}",
        f"- Package: {readiness['package_name']}",
        f"- Workers SDK dependency: {readiness['package_has_workers_sdk']}",
        f"- Source has expected tools: {readiness['source_has_expected_tools']}",
        f"- Tools are read-only hinted: {readiness['tools_are_read_only_hinted']}",
        f"- Setup script exists: {readiness['setup_script_exists']}",
        f"- CLI wrapper exists: {readiness['cli_wrapper_exists']}",
        f"- Repo-local CLI installed: {readiness['repo_local_cli_installed']}",
        f"- Repo-local CLI available: {readiness['repo_local_cli_available']}",
        f"- Portable Node available: {readiness['portable_node_available']}",
        f"- Local exec smoke tested by doctor: {readiness['local_exec_smoke_tested']}",
        f"- Local exec note: {readiness['local_exec_note']}",
        f"- Permission manifest has Notion Workers: {readiness['manifest_has_notion_workers']}",
        f"- Manifest status: {readiness['manifest_status']}",
        f"- Blocks secrets: {readiness['manifest_blocks_secrets']}",
        f"- Blocks customer data: {readiness['manifest_blocks_customer_data']}",
        f"- Blocks public posting: {readiness['manifest_blocks_public_posting']}",
        f"- Blocks deploy without approval: {readiness['manifest_blocks_deploy_without_approval']}",
        f"- Credentials checked: {readiness['credential_presence_checked']}",
        f"- Notion login checked: {readiness['notion_login_checked']}",
        f"- Note: {readiness['note']}",
        "",
        "## Tools",
        "",
    ]
    for tool, present in readiness["tool_hits"].items():
        lines.append(f"- `{tool}`: {present}")

    lines.extend(
        [
            "",
            "## Activation",
            "",
            "```powershell",
            "powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\setup-notion-workers.ps1",
            "python -m gateway.notion_workers doctor",
            "cd notion-workers\\ramin-os-agent-tools",
            "npm run check",
            "```",
            "",
            "Human checkpoint before:",
            "",
            "```powershell",
            "powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\notion-cli.ps1 login",
            "ntn workers deploy --name ramin-os-agent-tools",
            "```",
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
    status = build_notion_workers_status()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_notion_workers_report(status), encoding="utf-8")
    security.audit_event(
        "notion_workers_readiness",
        security.allow("notion_workers", "Notion Workers readiness checked; no login, deploy, or credential action performed."),
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
        ("worker_project_exists", "Notion Worker project is missing"),
        ("package_has_workers_sdk", "Worker package is missing @notionhq/workers"),
        ("source_has_expected_tools", "Worker source is missing expected Ramin-OS tools"),
        ("tools_are_read_only_hinted", "Worker tools must include readOnlyHint for side-effect-free tools"),
        ("setup_script_exists", "scripts/setup-notion-workers.ps1 is missing"),
        ("cli_wrapper_exists", "scripts/notion-cli.ps1 is missing"),
        ("repo_local_cli_available", "Repo-local Notion CLI is not installed; run scripts/setup-notion-workers.ps1"),
        ("manifest_has_notion_workers", "config/agent_permissions.json is missing notion_workers"),
        ("manifest_blocks_secrets", "Notion Workers manifest must block secrets and .env content"),
        ("manifest_blocks_customer_data", "Notion Workers manifest must block customer data"),
        ("manifest_blocks_public_posting", "Notion Workers manifest must block public posting"),
        ("manifest_blocks_deploy_without_approval", "Notion Workers manifest must block deployment without approval"),
        ("manifest_requires_no_dotenv_tests", "Notion Workers manifest must require --no-dotenv smoke tests"),
    ]
    return [message for key, message in checks if not readiness.get(key)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ramin-OS Notion Workers readiness checks.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Validate local Notion Workers readiness without reading credentials.")
    sub.add_parser("report", help="Write and print the Notion Workers readiness report.")
    sub.add_parser("status-json", help="Print machine-readable Notion Workers readiness JSON.")
    args = parser.parse_args()

    if args.command == "doctor":
        status = build_notion_workers_status()
        errors = doctor_errors(status)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print("Notion Workers readiness OK. Login/deploy still require a human checkpoint.")
        return 0
    if args.command == "report":
        status = run_report()
        print(render_notion_workers_report(status))
        print(f"Report written: {REPORT_PATH}")
        return 0
    if args.command == "status-json":
        print(json.dumps(build_notion_workers_status(), indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
