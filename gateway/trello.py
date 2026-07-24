"""Governed Trello connector for the Xalq Insurance work board.

Read operations may run after the operator supplies Trello credentials through
the process environment. Every write is first saved as a local, reviewable plan
and can only be applied with that exact plan's approval code. Credentials are
never included in reports, plans, audit events, or exception messages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import permissions, security
from ._bootstrap import load_env


load_env()


ROOT_DIR = Path(__file__).resolve().parent.parent
PERMISSIONS_PATH = ROOT_DIR / "config" / "agent_permissions.json"
REPORT_PATH = ROOT_DIR / "output" / "trello" / "trello_readiness.md"
CONNECTION_STATUS_PATH = ROOT_DIR / "output" / "trello" / "connection_status.json"
CONNECTION_REPORT_PATH = ROOT_DIR / "output" / "trello" / "connection_status.md"
PLAN_DIR = ROOT_DIR / "data" / "trello" / "pending"

TRELLO_AGENT_ID = "trello_work_board"
TRELLO_API_BASE = "https://api.trello.com/1"
DEFAULT_BOARD_REF = "RRlLCaSG"
DEFAULT_BOARD_URL = "https://trello.com/b/RRlLCaSG/xalg-insurance"
ALLOWED_BOARD_REFS = {DEFAULT_BOARD_REF}
ALLOWED_OPERATIONS = {"create_card", "move_card", "update_card", "comment_card"}
BLOCKED_FIELDS = {"closed", "idmembers", "idboard", "email"}


class TrelloError(RuntimeError):
    """A safe Trello connector error that never contains credentials."""


def board_ref(value: str) -> str:
    """Return a board short-link from a short-link or Trello board URL."""

    raw = value.strip()
    if "://" not in raw:
        ref = raw.split("/", 1)[0]
    else:
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme != "https" or parsed.hostname not in {"trello.com", "www.trello.com"}:
            raise TrelloError("Only https://trello.com board URLs are allowed.")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0] != "b":
            raise TrelloError("Expected a Trello board URL in /b/<board-ref>/... format.")
        ref = parts[1]
    if ref not in ALLOWED_BOARD_REFS:
        raise TrelloError("Board is not in the Ramin-OS Trello allowlist.")
    return ref


def _manifest_entry() -> dict[str, Any] | None:
    return permissions.get_agent(TRELLO_AGENT_ID)


def local_readiness() -> dict[str, Any]:
    """Check local connector/governance only; never inspect credential values."""

    entry = _manifest_entry()
    blocked_inputs = {str(item).casefold() for item in (entry or {}).get("blocked_inputs") or []}
    blocked_actions = {str(item).casefold() for item in (entry or {}).get("blocked_actions") or []}
    required = " ".join((entry or {}).get("required_controls") or []).casefold()
    return {
        "connector_exists": Path(__file__).exists(),
        "manifest_has_trello": entry is not None,
        "manifest_status": (entry or {}).get("status", "missing"),
        "board_allowlisted": DEFAULT_BOARD_REF in ALLOWED_BOARD_REFS,
        "manifest_blocks_secrets": "secrets" in blocked_inputs and ".env content" in blocked_inputs,
        "manifest_blocks_customer_data": "customer data" in blocked_inputs,
        "manifest_blocks_deletion": "delete cards, lists, or boards" in blocked_actions,
        "manifest_blocks_member_changes": "invite or remove members" in blocked_actions,
        "manifest_requires_write_approval": "approval code" in required,
        "credential_presence_checked": False,
        "board_access_checked": False,
        "note": "Credential values, .env files, token stores, and live board access are intentionally not inspected by doctor.",
    }


def build_status(now: float | None = None) -> dict[str, Any]:
    timestamp = time.time() if now is None else now
    ready = local_readiness()
    configured = all(
        ready[key]
        for key in (
            "connector_exists",
            "manifest_has_trello",
            "board_allowlisted",
            "manifest_blocks_secrets",
            "manifest_blocks_customer_data",
            "manifest_blocks_deletion",
            "manifest_blocks_member_changes",
            "manifest_requires_write_approval",
        )
    )
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
        "board_url": DEFAULT_BOARD_URL,
        "local_readiness": ready,
        "recommendation": {
            "status": "configured_needs_human_authorization" if configured else "not_integrated",
            "verdict": "ready_for_read_authorization" if configured else "not_ready",
            "next_action": "Authorize a least-privilege Trello token, then run snapshot before enabling any write plan.",
        },
    }


def render_report(status: dict[str, Any]) -> str:
    ready = status["local_readiness"]
    return "\n".join(
        [
            "# Trello Work Board Readiness",
            "",
            f"Generated: {status['generated_at']}",
            f"Board: {status['board_url']}",
            f"Status: {status['recommendation']['status']}",
            f"Verdict: {status['recommendation']['verdict']}",
            "",
            "## Local controls",
            "",
            f"- Connector exists: {ready['connector_exists']}",
            f"- Permission manifest entry: {ready['manifest_has_trello']}",
            f"- Board allowlisted: {ready['board_allowlisted']}",
            f"- Secrets blocked: {ready['manifest_blocks_secrets']}",
            f"- Customer data blocked: {ready['manifest_blocks_customer_data']}",
            f"- Deletion blocked: {ready['manifest_blocks_deletion']}",
            f"- Member changes blocked: {ready['manifest_blocks_member_changes']}",
            f"- Exact write approval required: {ready['manifest_requires_write_approval']}",
            f"- Note: {ready['note']}",
            "",
            "## Operating model",
            "",
            "- Snapshot/list/card reading is allowed after human Trello authorization.",
            "- Create, move, edit, due-date, and comment actions require a saved plan plus its exact approval code.",
            "- Card/list/board deletion and member changes are blocked.",
            "- Trello credentials remain local and must never be pasted into chat, commits, reports, or command history.",
            "",
            "See `docs/TRELLO_WORK_BOARD.md` for activation and use.",
            "",
        ]
    )


class TrelloClient:
    def __init__(
        self,
        api_key: str,
        token: str,
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: int = 20,
    ) -> None:
        if not api_key or not token:
            raise TrelloError("Trello authorization is missing. Configure it locally; do not paste credentials into chat.")
        self._api_key = api_key
        self._token = token
        self._opener = opener
        self._timeout = timeout

    @classmethod
    def from_environment(cls) -> "TrelloClient":
        return cls(os.getenv("TRELLO_API_KEY", ""), os.getenv("TRELLO_API_TOKEN", ""))

    def request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        if not path.startswith("/") or ".." in path:
            raise TrelloError("Unsafe Trello API path blocked.")
        query = {key: value for key, value in (params or {}).items() if value is not None}
        url = f"{TRELLO_API_BASE}{path}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(
            url,
            method=method,
            headers={
                "Accept": "application/json",
                # Trello officially supports this header form. Keeping credentials
                # out of the URL prevents accidental exposure in proxy/access logs.
                "Authorization": (
                    f'OAuth oauth_consumer_key="{self._api_key}", '
                    f'oauth_token="{self._token}"'
                ),
            },
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            raise TrelloError(f"Trello API returned HTTP {exc.code}.") from None
        except urllib.error.URLError:
            raise TrelloError("Trello API could not be reached.") from None

    def snapshot(self, board: str = DEFAULT_BOARD_REF) -> dict[str, Any]:
        ref = board_ref(board)
        return self.request(
            "GET",
            f"/boards/{ref}",
            {
                "fields": "name,url,dateLastActivity,closed",
                "lists": "open",
                "list_fields": "name,pos,closed",
                "cards": "open",
                "card_fields": "name,desc,idList,due,dueComplete,labels,dateLastActivity,url",
            },
        )

    def connection_probe(self, board: str = DEFAULT_BOARD_REF) -> dict[str, Any]:
        """Verify identity and allowlisted-board access without reading cards."""

        ref = board_ref(board)
        member = self.request("GET", "/members/me", {"fields": "id"})
        board_data = self.request(
            "GET",
            f"/boards/{ref}",
            {"fields": "name,url,closed,dateLastActivity"},
        )
        return {
            "member_authorized": bool(member.get("id")),
            "board_accessible": bool(board_data.get("url") or board_data.get("name")),
            "board": {
                "name": str(board_data.get("name") or ""),
                "url": str(board_data.get("url") or DEFAULT_BOARD_URL),
                "closed": bool(board_data.get("closed", False)),
                "date_last_activity": board_data.get("dateLastActivity"),
            },
        }


def build_connection_status(
    client: TrelloClient | None = None,
    *,
    now: float | None = None,
    inspect_environment: bool = True,
) -> dict[str, Any]:
    """Return a secret-free, browser-free live connection status.

    The check never creates, edits, moves, comments on, or deletes Trello data.
    It only verifies the current user token and reads minimal metadata for the
    one allowlisted board.
    """

    timestamp = time.time() if now is None else now
    status: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
        "board_ref": DEFAULT_BOARD_REF,
        "board_url": DEFAULT_BOARD_URL,
        "check_mode": "headless_read_only",
        "browser_opened": False,
        "board_write_attempted": False,
        "credential_presence_checked": False,
        "credentials_present": None,
        "member_authorized": False,
        "board_accessible": False,
        "state": "waiting_for_human_authorization",
        "blocker": "Trello API key and user token are not available to the connector.",
        "next_action": (
            "Complete Trello Power-Up registration and the Trello user consent step, "
            "then store TRELLO_API_KEY and TRELLO_API_TOKEN with the approved local secret flow."
        ),
    }

    if client is None:
        if not inspect_environment:
            status["state"] = "human_authorization_not_verified"
            status["blocker"] = "Live credential inspection was intentionally skipped."
            status["next_action"] = "Run connection-check after the human Trello consent step is complete."
            return status
        api_key = os.getenv("TRELLO_API_KEY", "")
        token = os.getenv("TRELLO_API_TOKEN", "")
        status["credential_presence_checked"] = True
        status["credentials_present"] = bool(api_key and token)
        if not status["credentials_present"]:
            return status
        client = TrelloClient(api_key, token)
    else:
        status["credential_presence_checked"] = True
        status["credentials_present"] = True

    try:
        probe = client.connection_probe()
    except TrelloError as exc:
        safe_error = str(exc)
        status["state"] = "authorization_or_access_failed"
        status["blocker"] = safe_error
        if "HTTP 401" in safe_error:
            status["next_action"] = "Re-authorize the Trello user token; the current token was rejected."
        elif "HTTP 403" in safe_error:
            status["next_action"] = (
                "Ask the Trello/Atlassian workspace admin to allow the app and verify board membership."
            )
        else:
            status["next_action"] = "Retry the background check after Trello connectivity is restored."
        return status

    connected = probe["member_authorized"] and probe["board_accessible"]
    status.update(
        {
            "member_authorized": probe["member_authorized"],
            "board_accessible": probe["board_accessible"],
            "board": probe["board"],
            "state": "connected_governed" if connected else "access_incomplete",
            "blocker": None if connected else "The token is valid but the allowlisted board is not accessible.",
            "next_action": (
                "Run a read-only snapshot. Board writes remain disabled unless an exact saved plan is approved."
                if connected
                else "Verify that the authorized Trello user can open the allowlisted board."
            ),
        }
    )
    return status


def render_connection_report(status: dict[str, Any]) -> str:
    board = status.get("board") or {}
    lines = [
        "# Trello Background Connection Status",
        "",
        f"Generated: {status['generated_at']}",
        f"Board: {status['board_url']}",
        f"State: {status['state']}",
        "Mode: headless read-only probe (no browser window)",
        "",
        "## Checks",
        "",
        f"- Credential presence checked: {status['credential_presence_checked']}",
        f"- Credentials available to connector: {status['credentials_present'] if status['credential_presence_checked'] else 'unknown'}",
        f"- Trello member authorized: {status['member_authorized']}",
        f"- Allowlisted board accessible: {status['board_accessible']}",
        f"- Board write attempted: {status['board_write_attempted']}",
    ]
    if board:
        lines.extend(
            [
                f"- Board name: {board.get('name') or 'unavailable'}",
                f"- Board closed: {board.get('closed', False)}",
                f"- Last activity: {board.get('date_last_activity') or 'unavailable'}",
            ]
        )
    lines.extend(
        [
            "",
            "## Result",
            "",
            f"- Blocker: {status.get('blocker') or 'none'}",
            f"- Next action: {status['next_action']}",
            "",
            "Trello credentials are never included in this report.",
            "",
        ]
    )
    return "\n".join(lines)


def save_connection_status(status: dict[str, Any]) -> tuple[Path, Path]:
    CONNECTION_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONNECTION_STATUS_PATH.write_text(
        json.dumps(status, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    CONNECTION_REPORT_PATH.write_text(render_connection_report(status), encoding="utf-8")
    return CONNECTION_STATUS_PATH, CONNECTION_REPORT_PATH


def _canonical_plan_data(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key not in {"approval_code", "created_at"}}


def approval_code(plan: dict[str, Any]) -> str:
    raw = json.dumps(_canonical_plan_data(plan), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def build_write_plan(operation: str, target_id: str, changes: dict[str, Any], board: str = DEFAULT_BOARD_REF) -> dict[str, Any]:
    if operation not in ALLOWED_OPERATIONS:
        raise TrelloError(f"Unsupported or blocked Trello operation: {operation}")
    ref = board_ref(board)
    clean_changes = {str(key): value for key, value in changes.items() if value is not None}
    if any(key.casefold() in BLOCKED_FIELDS for key in clean_changes):
        raise TrelloError("Plan includes a blocked Trello field.")
    if operation == "create_card" and not {"name", "idList"}.issubset(clean_changes):
        raise TrelloError("create_card requires name and idList.")
    if operation != "create_card" and not target_id.strip():
        raise TrelloError(f"{operation} requires a target card id.")
    if operation == "move_card" and set(clean_changes) != {"idList"}:
        raise TrelloError("move_card accepts only idList.")
    if operation == "comment_card" and set(clean_changes) != {"text"}:
        raise TrelloError("comment_card accepts only text.")
    if operation == "update_card" and not set(clean_changes).issubset({"name", "desc", "due", "dueComplete"}):
        raise TrelloError("update_card accepts only name, desc, due, and dueComplete.")
    plan = {
        "schema_version": 1,
        "board_ref": ref,
        "board_url": DEFAULT_BOARD_URL,
        "operation": operation,
        "target_id": target_id.strip(),
        "changes": clean_changes,
        "risk": "Writes to the shared Xalq Insurance Trello board.",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    plan["approval_code"] = approval_code(plan)
    return plan


def save_plan(plan: dict[str, Any]) -> Path:
    code = approval_code(plan)
    if plan.get("approval_code") != code:
        raise TrelloError("Plan approval code is invalid.")
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    path = PLAN_DIR / f"{code}.json"
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def apply_plan(client: TrelloClient, plan: dict[str, Any], supplied_approval: str) -> Any:
    expected = approval_code(plan)
    if supplied_approval != expected or plan.get("approval_code") != expected:
        raise TrelloError("Write blocked: approval code does not match the exact saved plan.")
    permissions.require_allowed(TRELLO_AGENT_ID, "approval_required")
    board_ref(str(plan.get("board_ref", "")))
    operation = plan.get("operation")
    target = str(plan.get("target_id", ""))
    changes = dict(plan.get("changes") or {})
    build_write_plan(str(operation), target, changes, str(plan["board_ref"]))
    if operation == "create_card":
        result = client.request("POST", "/cards", changes)
    elif operation in {"move_card", "update_card"}:
        result = client.request("PUT", f"/cards/{urllib.parse.quote(target, safe='')}", changes)
    elif operation == "comment_card":
        result = client.request("POST", f"/cards/{urllib.parse.quote(target, safe='')}/actions/comments", changes)
    else:
        raise TrelloError("Write blocked: unsupported operation.")
    security.audit_event(
        "trello_write_applied",
        security.allow("trello", f"Approved Trello {operation} plan applied."),
        {"board_ref": plan["board_ref"], "operation": operation, "approval_code": expected},
    )
    return result


def doctor_errors(status: dict[str, Any]) -> list[str]:
    checks = {
        "connector_exists": "gateway/trello.py is missing",
        "manifest_has_trello": "config/agent_permissions.json is missing trello_work_board",
        "board_allowlisted": "Xalq Insurance Trello board is not allowlisted",
        "manifest_blocks_secrets": "Trello manifest must block secrets and .env content",
        "manifest_blocks_customer_data": "Trello manifest must block customer data",
        "manifest_blocks_deletion": "Trello manifest must block deletion",
        "manifest_blocks_member_changes": "Trello manifest must block member changes",
        "manifest_requires_write_approval": "Trello writes must require an exact approval code",
    }
    ready = status["local_readiness"]
    return [message for key, message in checks.items() if not ready.get(key)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed Xalq Insurance Trello board connector.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check local governance without inspecting credentials.")
    sub.add_parser("report", help="Write a local readiness report.")
    sub.add_parser("connection-check", help="Run a headless read-only check and save secret-free status artifacts.")
    sub.add_parser("snapshot", help="Read the allowlisted board using local environment authorization.")
    plan_parser = sub.add_parser("plan", help="Save a reviewable Trello write plan.")
    plan_parser.add_argument("operation", choices=sorted(ALLOWED_OPERATIONS))
    plan_parser.add_argument("--target-id", default="")
    plan_parser.add_argument("--changes-json", required=True, help="Non-secret JSON object containing the requested changes.")
    apply_parser = sub.add_parser("apply", help="Apply one exact, previously saved plan.")
    apply_parser.add_argument("approval_code")
    args = parser.parse_args()

    try:
        if args.command == "doctor":
            errors = doctor_errors(build_status())
            if errors:
                for error in errors:
                    print(f"ERROR: {error}")
                return 1
            print("Trello connector governance OK. Live authorization was not checked.")
            return 0
        if args.command == "report":
            status = build_status()
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(render_report(status), encoding="utf-8")
            print(render_report(status))
            return 0
        if args.command == "connection-check":
            status = build_connection_status()
            json_path, report_path = save_connection_status(status)
            print(
                json.dumps(
                    {
                        "state": status["state"],
                        "board_accessible": status["board_accessible"],
                        "browser_opened": False,
                        "board_write_attempted": False,
                        "status_json": str(json_path),
                        "report": str(report_path),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0 if status["state"] == "connected_governed" else 2
        if args.command == "snapshot":
            print(json.dumps(TrelloClient.from_environment().snapshot(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "plan":
            changes = json.loads(args.changes_json)
            if not isinstance(changes, dict):
                raise TrelloError("--changes-json must be a JSON object.")
            plan = build_write_plan(args.operation, args.target_id, changes)
            path = save_plan(plan)
            print(json.dumps({"plan": plan, "saved_to": str(path)}, indent=2, ensure_ascii=False))
            return 0
        if args.command == "apply":
            path = PLAN_DIR / f"{args.approval_code}.json"
            if not path.exists():
                raise TrelloError("No saved Trello plan matches that approval code.")
            plan = json.loads(path.read_text(encoding="utf-8"))
            result = apply_plan(TrelloClient.from_environment(), plan, args.approval_code)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
    except (TrelloError, json.JSONDecodeError, permissions.PermissionManifestError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
