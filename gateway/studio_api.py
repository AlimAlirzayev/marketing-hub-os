"""HTTP bridge — let the autonomous agent USE the live studio web APIs.

The studios run as local FastAPI/Streamlit services (see services.json). This
gives the executor (tools mode) two functions so the brain can drive the body:

  * list_studios()        — discover what studios exist (key, purpose, port).
  * call_studio_api(...)  — call a studio's local HTTP endpoint by key.

Safety (inbound hard shell stays intact):
  * Only studios registered in services.json are reachable, and only on
    127.0.0.1 (no arbitrary URLs).
  * GET is free (read / discover / analytics). POST is allowed for
    read/generate-style endpoints but BLOCKED when the path looks like a real
    spend/post/delete action — those must go through an explicit checkpoint.
"""

import json
from pathlib import Path

import requests
import os

# Per-call timeout for studio HTTP calls; short by default so a slow or dead
# studio cannot stall an orchestration loop for minutes (2026-07-19). Overridable.
_STUDIO_TIMEOUT = int(os.getenv("STUDIO_API_TIMEOUT", "20"))

_ROOT = Path(__file__).resolve().parent.parent
_SERVICES_CACHE = None

# POST paths that imply an irreversible / spend / outward action need a human
# checkpoint and must NOT be fired autonomously from a tool call.
_RISKY = (
    "create", "publish", "send", "post", "pay", "charge", "checkout", "spend",
    "campaign", "/ad", "ads", "delete", "remove", "launch", "submit", "buy",
    "order", "subscribe", "transfer", "approve",
)


import re as _re

# Meta Graph responses embed the FULL access token inside paging.next/previous
# URLs — key-name redaction misses it because the secret hides in a value
# (2026-07-15 leak). Any studio may proxy a raw Graph page, so every response
# that leaves this module is scrubbed: paging blocks dropped, token params
# stripped. Applies to the agent tool path and the CLI alike.
_TOKEN_PARAM_RE = _re.compile(r"(access_token|appsecret_proof)=[^&\s\"']+")


def _drop_paging(node):
    if isinstance(node, dict):
        return {k: _drop_paging(v) for k, v in node.items() if k != "paging"}
    if isinstance(node, list):
        return [_drop_paging(v) for v in node]
    return node


def scrub_response(text):
    try:
        cleaned = json.dumps(_drop_paging(json.loads(text)), ensure_ascii=False)
    except Exception:
        cleaned = text
    return _TOKEN_PARAM_RE.sub(r"\1=<redacted>", cleaned)


def _services():
    global _SERVICES_CACHE
    if _SERVICES_CACHE is None:
        data = json.loads((_ROOT / "services.json").read_text(encoding="utf-8"))
        _SERVICES_CACHE = {s["key"]: s for s in data.get("services", [])}
    return _SERVICES_CACHE


def list_studios():
    """List the studios the agent can call: key, name, purpose, port.

    Call this first to see what capabilities exist, then call_studio_api with a
    studio key. Use path '/openapi.json' on a studio to learn its real endpoints.
    """
    rows = []
    for k, s in _services().items():
        rows.append(f"{k}: {s.get('name','')} — {s.get('desc','')} (port {s.get('port')}, health {s.get('health','')})")
    return "\n".join(rows)


def call_studio_api(studio, path, method="GET", json_body=""):
    """Call a live studio's local HTTP API (127.0.0.1 only).

    studio: studio key from services.json (e.g. 'cx','ads','ga4','atelier','price','influencer','capi').
    path:   endpoint path, e.g. '/api/health' or '/openapi.json' (call '/openapi.json' first to discover endpoints).
    method: 'GET' (read/discover) or 'POST' (read/generate bodies only; spend/post/delete paths are blocked).
    json_body: JSON string for POST bodies (optional).
    Returns the response text (truncated).
    """
    svc = _services().get(studio)
    if not svc:
        return f"Unknown studio '{studio}'. Available keys: {', '.join(_services().keys())}"
    method = (method or "GET").upper()
    if method not in ("GET", "POST"):
        return f"Method '{method}' not allowed (GET/POST only)."
    if not path.startswith("/"):
        path = "/" + path
    low = path.lower()
    if method == "POST" and any(tok in low for tok in _RISKY):
        return (
            f"BLOCKED (checkpoint required): POST {studio}{path} looks like an "
            "irreversible / spend / outward action. The owner must approve it "
            "through a checkpoint before it can run."
        )
    url = f"http://127.0.0.1:{svc['port']}{path}"
    try:
        if method == "POST":
            body = json.loads(json_body) if (json_body or "").strip() else {}
            r = requests.post(url, json=body, timeout=_STUDIO_TIMEOUT)
        else:
            r = requests.get(url, timeout=_STUDIO_TIMEOUT)
        return f"HTTP {r.status_code} {url}\n{scrub_response(r.text)[:4000]}"
    except Exception as exc:  # never crash the agent loop
        return f"call_studio_api error for {url}: {exc}"


# Defensive: real annotations so google-genai automatic function-calling can
# introspect these even if a caller module uses `from __future__ import annotations`.
list_studios.__annotations__ = {"return": str}
call_studio_api.__annotations__ = {
    "studio": str, "path": str, "method": str, "json_body": str, "return": str,
}


# --- media generation: weave the fleet's /opt/media-gen service (127.0.0.1:8765) ---
import os as _os, time as _time

_MEDIA_URL = _os.getenv("MEDIA_GEN_URL", "http://127.0.0.1:8765")
_MEDIA_EXT = {"image": "png", "video": "mp4", "voice": "mp3", "music": "mp3"}


def generate_media(kind, prompt, provider="", model=""):
    """Generate an image/video/voice/music FILE from a text prompt via the
    fleet's media-gen service. kind: 'image'|'video'|'voice'|'music'.
    Prefer free providers (image: pollinations or gemini; voice: pollinations).
    Returns the saved file path. This only CREATES an asset; publishing/posting
    it is a separate, checkpoint-gated action.
    """
    kind = (kind or "").lower().strip()
    if kind not in _MEDIA_EXT:
        return f"Unknown media kind '{kind}'. Use: image|video|voice|music."
    body = {"prompt": prompt, "text": prompt}
    if provider:
        body["provider"] = provider
    if model:
        body["model"] = model
    url = f"{_MEDIA_URL}/generate/{kind}"
    try:
        r = requests.post(url, json=body, timeout=300)
    except Exception as exc:  # never crash the agent loop
        return f"generate_media error: {exc}"
    if r.status_code != 200:
        return f"media-gen HTTP {r.status_code}: {r.text[:300]}"
    out = _ROOT / "output" / "media"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{kind}-{int(_time.time())}.{_MEDIA_EXT[kind]}"
    path.write_bytes(r.content)
    return f"Generated {kind} ({len(r.content)} bytes) -> {path}"


generate_media.__annotations__ = {
    "kind": str, "prompt": str, "provider": str, "model": str, "return": str,
}


# --- CLI gate: the chat brain's ONE door to the live services -------------
# The headless chat brain (claude_bridge) runs `claude -p` with permission-mode
# "default", which auto-declines tools — so it could DESCRIBE the studios but
# never USE them. Instead of widening its Bash access, the bridge allowlists
# exactly one command prefix: `python3 -m gateway.studio_api ...`. This entry
# point re-uses the same hard shell as the agent tool (registered studios only,
# 127.0.0.1 only, GET + safe POST, risky paths blocked, responses scrubbed), so
# giving the brain hands does not widen what the hands can touch.

def _cli(argv):
    if not argv or argv[0] in ("-h", "--help"):
        return (
            "usage:\n"
            "  python3 -m gateway.studio_api list\n"
            "  python3 -m gateway.studio_api call <studio> <path> "
            "[--method GET|POST] [--body '<json>']\n"
            "Discover a studio's endpoints first: call <studio> /openapi.json"
        )
    if argv[0] == "list":
        return list_studios()
    if argv[0] == "call" and len(argv) >= 3:
        studio, path, method, body = argv[1], argv[2], "GET", ""
        rest = argv[3:]
        while rest:
            flag = rest.pop(0)
            if flag == "--method" and rest:
                method = rest.pop(0)
            elif flag == "--body" and rest:
                body = rest.pop(0)
            else:
                return f"unknown argument: {flag}"
        return call_studio_api(studio, path, method=method, json_body=body)
    return f"unknown command: {' '.join(argv)} (try --help)"


if __name__ == "__main__":
    import sys as _sys
    print(_cli(_sys.argv[1:]))
