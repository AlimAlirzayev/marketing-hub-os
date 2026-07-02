"""Agent permission manifest loader and validator for Ramin-OS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "config" / "agent_permissions.json"

FORBIDDEN_AUTONOMOUS_ACTIONS = {
    "send replies",
    "post publicly",
    "handle payments",
    "access payments",
    "grant production access",
    "destructive changes",
    "secret exposure",
}


class PermissionManifestError(ValueError):
    pass


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def agents(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    manifest = load_manifest() if manifest is None else manifest
    return list(manifest.get("agents") or [])


def get_agent(agent_id: str, manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    for agent in agents(manifest):
        if agent.get("id") == agent_id:
            return agent
    return None


def validate_manifest(manifest: dict[str, Any] | None = None) -> list[str]:
    manifest = load_manifest() if manifest is None else manifest
    errors: list[str] = []
    permission_levels = set((manifest.get("permission_levels") or {}).keys())
    seen: set[str] = set()

    for index, agent in enumerate(agents(manifest)):
        prefix = f"agents[{index}]"
        agent_id = agent.get("id")
        if not agent_id:
            errors.append(f"{prefix}: missing id")
            continue
        if agent_id in seen:
            errors.append(f"{prefix}: duplicate id {agent_id}")
        seen.add(agent_id)

        permissions = set(agent.get("permissions") or [])
        unknown = sorted(permissions - permission_levels)
        if unknown:
            errors.append(f"{agent_id}: unknown permissions {', '.join(unknown)}")

        blocked_actions = {str(item).casefold() for item in agent.get("blocked_actions") or []}
        if not blocked_actions:
            errors.append(f"{agent_id}: blocked_actions must not be empty")

        status = str(agent.get("status") or "")
        if "production" in status.casefold():
            errors.append(f"{agent_id}: status must not imply production approval")

        if "send replies" not in blocked_actions and agent_id.startswith("cx_"):
            errors.append(f"{agent_id}: CX agents must block autonomous reply sending")

    return errors


def require_allowed(agent_id: str, permission: str) -> bool:
    agent = get_agent(agent_id)
    if not agent:
        raise PermissionManifestError(f"Unknown agent: {agent_id}")
    if permission not in set(agent.get("permissions") or []):
        raise PermissionManifestError(f"{agent_id} does not have permission: {permission}")
    return True


def render_report(manifest: dict[str, Any] | None = None) -> str:
    manifest = load_manifest() if manifest is None else manifest
    errors = validate_manifest(manifest)
    lines = [
        "# Agent Permission Manifest Report",
        "",
        f"Schema version: {manifest.get('schema_version')}",
        f"Agents: {len(agents(manifest))}",
        f"Validation: {'OK' if not errors else 'FAILED'}",
        "",
    ]
    if errors:
        lines.append("## Errors")
        lines.extend(f"- {error}" for error in errors)
        lines.append("")

    lines.append("## Agents")
    for agent in agents(manifest):
        lines.extend(
            [
                f"### {agent['id']}",
                f"- Name: {agent.get('name')}",
                f"- Status: {agent.get('status')}",
                f"- Permissions: {', '.join(agent.get('permissions') or [])}",
                f"- Required controls: {'; '.join(agent.get('required_controls') or [])}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect Ramin-OS agent permissions.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Validate the permission manifest.")
    sub.add_parser("report", help="Print a Markdown permission report.")
    args = parser.parse_args()

    manifest = load_manifest()
    if args.command == "doctor":
        errors = validate_manifest(manifest)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print("Agent permission manifest OK.")
        return 0
    if args.command == "report":
        print(render_report(manifest))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
