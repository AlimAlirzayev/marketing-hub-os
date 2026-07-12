"""Generic MCP client (Streamable HTTP) — the engine's own hands for remote MCP servers.

Until now the engine could only *describe* MCP servers (gateway/flora_ai.py is a
readiness report, not a client). This module actually SPEAKS the protocol, so the
system — not just a Claude Code session — can call remote MCP tools from Telegram,
the panel, or the executor. One client serves every MCP the research lab has found:
Meta Ads, TikTok Ads, AdRoll, Canva.

Transport: JSON-RPC 2.0 over Streamable HTTP (spec 2025-06-18). Handles both
`application/json` and `text/event-stream` responses, session ids, and bearer auth.
Stdlib only (urllib) — the engine takes no new dependencies.

Auth: pass a bearer token. A 401 raises McpAuthError carrying the server's
WWW-Authenticate hint (resource metadata URL + required scopes), so the caller can
tell the human exactly what is missing instead of failing blind.

CLI:
    python3 -m gateway.mcp_client <url> [--token T] tools      # list tools
    python3 -m gateway.mcp_client <url> [--token T] call <tool> '<json args>'
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "marketing-hub-os"
CLIENT_VERSION = "1.0"
TIMEOUT = 60


class McpError(RuntimeError):
    """The MCP server returned a protocol- or transport-level error."""


class McpAuthError(McpError):
    """401 — no/invalid token. Carries the server's auth hint for the human."""

    def __init__(self, message: str, *, resource_metadata: str = "", scopes: str = "") -> None:
        super().__init__(message)
        self.resource_metadata = resource_metadata
        self.scopes = scopes


def _parse_www_authenticate(header: str) -> tuple[str, str]:
    """Pull resource_metadata= and scope= out of a WWW-Authenticate Bearer header."""
    meta, scope = "", ""
    for part in header.split(","):
        part = part.strip()
        for key, target in (("resource_metadata=", "meta"), ("scope=", "scope")):
            if part.lower().startswith(("bearer " + key).lower()):
                part = part[len("Bearer "):]
            if part.lower().startswith(key):
                value = part[len(key):].strip().strip('"')
                if target == "meta":
                    meta = value
                else:
                    scope = value
    return meta, scope


def _parse_sse(body: str) -> list[dict[str, Any]]:
    """Extract JSON payloads from a text/event-stream body."""
    out: list[dict[str, Any]] = []
    for block in body.split("\n\n"):
        data = "".join(
            line[len("data:"):].strip()
            for line in block.splitlines()
            if line.startswith("data:")
        )
        if not data:
            continue
        try:
            out.append(json.loads(data))
        except json.JSONDecodeError:
            continue
    return out


class McpClient:
    """A minimal, correct Streamable-HTTP MCP client."""

    def __init__(self, url: str, token: str = "", *, timeout: int = TIMEOUT) -> None:
        self.url = url
        self.token = token
        self.timeout = timeout
        self.session_id = ""
        self._initialized = False

    # ---------- transport ----------
    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                ctype = (resp.headers.get("Content-Type") or "").lower()
                body = resp.read().decode("utf-8", "replace")
                if resp.status == 202 or not body.strip():   # notification ack
                    return None
                if "text/event-stream" in ctype:
                    messages = _parse_sse(body)
                    # the response to our request is the message carrying our id
                    for m in messages:
                        if m.get("id") == payload.get("id"):
                            return m
                    return messages[-1] if messages else None
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 401:
                meta, scope = _parse_www_authenticate(e.headers.get("WWW-Authenticate", ""))
                raise McpAuthError(
                    f"401 unauthorized from {self.url} — a valid bearer token is required.",
                    resource_metadata=meta, scopes=scope,
                ) from e
            raise McpError(f"HTTP {e.code} from {self.url}: {body[:300]}") from e
        except urllib.error.URLError as e:
            raise McpError(f"cannot reach {self.url}: {e.reason}") from e

    def _rpc(self, method: str, params: dict[str, Any] | None = None, *, rpc_id: int = 1) -> Any:
        resp = self._post({"jsonrpc": "2.0", "id": rpc_id, "method": method,
                           "params": params or {}})
        if resp is None:
            raise McpError(f"empty response to {method}")
        if "error" in resp:
            err = resp["error"]
            raise McpError(f"{method} failed: {err.get('code')} {err.get('message')}")
        return resp.get("result")

    # ---------- protocol ----------
    def initialize(self) -> dict[str, Any]:
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
        })
        # required by spec: tell the server we're ready (notification, no id)
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True
        return result or {}

    def _ensure(self) -> None:
        if not self._initialized:
            self.initialize()

    def list_tools(self) -> list[dict[str, Any]]:
        self._ensure()
        return (self._rpc("tools/list", rpc_id=2) or {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        self._ensure()
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}}, rpc_id=3)


def _main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    url = argv[0]
    token = ""
    rest = argv[1:]
    if rest and rest[0] == "--token":
        token, rest = rest[1], rest[2:]
    client = McpClient(url, token)
    try:
        if not rest or rest[0] == "tools":
            for t in client.list_tools():
                print(f"- {t.get('name')}: {(t.get('description') or '')[:90]}")
        elif rest[0] == "call" and len(rest) > 1:
            args = json.loads(rest[2]) if len(rest) > 2 else {}
            print(json.dumps(client.call_tool(rest[1], args), ensure_ascii=False, indent=2))
        else:
            print(__doc__)
            return 1
    except McpAuthError as e:
        print(f"AUTH: {e}\n  scopes needed: {e.scopes}\n  metadata: {e.resource_metadata}")
        return 2
    except McpError as e:
        print(f"ERROR: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
