"""Thin JSON-RPC-over-stdio client for the FLORA AI MCP.

This is the missing link that makes "işə sal" real: it drives the official FLORA
remote MCP (via `mcp-remote`) using the OAuth token already cached in
~/.mcp-auth, and exposes the two FLORA tools — `search_docs` and `execute` — as
plain Python calls. MediaForge uses it to ground the model catalog, check
run_cost, and run a generation.

Governance: this only *talks* to FLORA. It does not decide to spend. The caller
(pipeline / CLI) checks cost against FLORA_MAX_BATCH_COST_USD before any
generation and surfaces the number first.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
_NODE_DIR = ROOT / "video-studio" / "tools" / "node-v24.15.0-win-x64"
FLORA_URL = "https://agents.flora.ai/mcp"


def _npx_env() -> dict[str, str]:
    env = dict(os.environ)
    # mcp-remote is launched by npx.cmd whose child `node` must be resolvable —
    # the portable runtime has to be PREPENDED to PATH or the spawn fails.
    if _NODE_DIR.exists():
        env["PATH"] = str(_NODE_DIR) + os.pathsep + env.get("PATH", "")
    return env


class FloraMCPError(RuntimeError):
    pass


class FloraMCP:
    """One short-lived MCP session over mcp-remote stdio."""

    def __init__(self, *, connect_timeout: float = 90.0):
        npx = _NODE_DIR / "npx.cmd"
        cmd = [str(npx) if npx.exists() else "npx", "-y", "mcp-remote", FLORA_URL]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=_npx_env(), text=True, encoding="utf-8", bufsize=1,
        )
        self._id = 0
        self._stderr: list[str] = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._initialize(connect_timeout)

    def _drain_stderr(self) -> None:
        for line in self.proc.stderr:  # type: ignore[union-attr]
            self._stderr.append(line)

    def _send(self, obj: dict[str, Any]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _read_reply(self, want_id: int, timeout: float) -> dict[str, Any]:
        deadline = time.time() + timeout
        assert self.proc.stdout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                if self.proc.poll() is not None:
                    raise FloraMCPError(
                        "mcp-remote exited: " + "".join(self._stderr)[-400:]
                    )
                time.sleep(0.1)
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == want_id:
                if "error" in msg:
                    raise FloraMCPError(str(msg["error"]))
                return msg.get("result", {})
        raise FloraMCPError(f"timeout waiting for reply id={want_id}")

    def _initialize(self, timeout: float) -> None:
        rid = self._next_id()
        self._send({
            "jsonrpc": "2.0", "id": rid, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "mediaforge", "version": "0.1"}},
        })
        self.server_info = self._read_reply(rid, timeout).get("serverInfo", {})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, arguments: dict[str, Any], *, timeout: float = 180.0) -> str:
        rid = self._next_id()
        self._send({
            "jsonrpc": "2.0", "id": rid, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        result = self._read_reply(rid, timeout)
        parts = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        text = "\n".join(p for p in parts if p)
        if result.get("isError"):
            raise FloraMCPError(text or "tool returned isError with no text")
        return text

    def search_docs(self, query: str, *, language: str = "javascript",
                    detail: str = "default", **kw) -> str:
        return self.call_tool(
            "search_docs",
            {"query": query, "language": language, "detail": detail}, **kw,
        )

    def execute(self, code: str, *, intent: str = "", **kw) -> str:
        args: dict[str, Any] = {"code": code}
        if intent:
            args["intent"] = intent
        return self.call_tool("execute", args, **kw)

    # -- higher-level helpers over the FLORA SDK (execute runs `run(client)`) -- #
    def run_json(self, body: str, *, intent: str = "", timeout: float = 180.0) -> Any:
        js = "async function run(client) {\n" + body + "\n}"
        text = self.execute(js, intent=intent, timeout=timeout)
        data = json.loads(text)
        return data.get("result", data) if isinstance(data, dict) else data

    def default_workspace_id(self) -> str:
        ws = self.run_json("const w = await client.workspaces.list(); return w.workspaces || w;",
                           intent="list workspaces")
        if not ws:
            raise FloraMCPError("no workspace accessible to this API session")
        return ws[0]["workspace_id"]

    def ensure_project(self, workspace_id: str, name: str) -> dict[str, Any]:
        body = f"""
  try {{
    const p = await client.projects.create({{ workspace_id: {json.dumps(workspace_id)}, name: {json.dumps(name)} }});
    return {{ project_id: p.project_id, created: true }};
  }} catch (e) {{
    const projs = [];
    for await (const p of client.projects.list({{ workspace_id: {json.dumps(workspace_id)}, limit: 50 }})) projs.push(p);
    const hit = projs.find(p => p.name === {json.dumps(name)});
    if (hit) return {{ project_id: hit.project_id, created: false }};
    return {{ project_id: projs.length ? projs[0].project_id : null, created: false, note: e.message }};
  }}"""
        return self.run_json(body, intent="ensure project")

    def generate_video(self, *, workspace_id: str, project_id: str, model: str,
                       prompt: str, params: dict[str, Any]) -> dict[str, Any]:
        """Fire a paid video generation. Returns run_id + charged_cost."""
        body = f"""
  const gen = await client.generations.create({{
    workspace_id: {json.dumps(workspace_id)}, project_id: {json.dumps(project_id)},
    type: "video", model: {json.dumps(model)}, prompt: {json.dumps(prompt)},
    params: {json.dumps(params)}
  }});
  return {{ run_id: gen.run_id, charged_cost: gen.charged_cost,
           estimated_seconds: gen.estimated_seconds, status: gen.status }};"""
        return self.run_json(body, intent="generate promo video", timeout=180)

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Poll a run's status + outputs (read-only).

        Response: {run_id, status: pending|running|completed|failed, progress,
        charged_cost?, outputs?: {output_id, type: 'videoUrl'|..., url}, ...}
        """
        body = f"const r = await client.generations.retrieve({json.dumps(run_id)}); return r;"
        return self.run_json(body, intent="poll run", timeout=60)

    def close(self) -> None:
        try:
            self.proc.terminate()
        except Exception:  # noqa: BLE001
            pass


def _main(argv: list[str]) -> int:
    import sys
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    if not argv or (argv[0] != "ping" and len(argv) < 2):
        print("usage: python -m mediaforge.flora_client {docs <query> | exec <js> | ping}")
        return 2
    mode = argv[0]
    payload = " ".join(argv[1:])
    flora = FloraMCP()
    try:
        if mode == "ping":
            print("connected:", flora.server_info)
            return 0
        if mode == "docs":
            print(flora.search_docs(payload))
            return 0
        if mode == "exec":
            print(flora.execute(payload))
            return 0
        print(f"unknown mode: {mode}")
        return 2
    finally:
        flora.close()


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
