"""Attempt Meta webhook/page subscription from current .env.

This script is intentionally safe:
- It never prints tokens.
- It first verifies the public callback.
- It attempts only the Graph subscription calls Meta officially exposes.
- If Meta refuses because app review/permission is missing, it prints the exact
  missing permission in a redacted form.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

import requests


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    env = _read_env(ROOT / ".env")
    base_url = env.get("CX_PUBLIC_BASE_URL", "").rstrip("/")
    verify = env.get("CX_META_VERIFY_TOKEN", "")
    token = env.get("META_GRAPH_ACCESS_TOKEN") or env.get("META_ACCESS_TOKEN") or ""
    version = env.get("META_GRAPH_API_VERSION") or env.get("META_API_VERSION") or "v25.0"
    page_ids = _csv(env.get("META_FACEBOOK_PAGE_IDS", ""))

    result = {
        "public_callback": f"{base_url}/api/webhooks/meta" if base_url else "",
        "public_verify_ok": False,
        "page_subscriptions": [],
        "ok": False,
        "errors": [],
    }

    if not base_url or not base_url.startswith("https://"):
        result["errors"].append("CX_PUBLIC_BASE_URL must be a public https URL")
        return _done(result, 1)
    if not verify:
        result["errors"].append("CX_META_VERIFY_TOKEN is empty")
        return _done(result, 1)
    if not token:
        result["errors"].append("META_GRAPH_ACCESS_TOKEN or META_ACCESS_TOKEN is empty")
        return _done(result, 1)
    if not page_ids:
        result["errors"].append("META_FACEBOOK_PAGE_IDS is empty")
        return _done(result, 1)

    verify_url = f"{base_url}/api/webhooks/meta?hub.mode=subscribe&hub.verify_token={quote(verify)}&hub.challenge=codex-ok"
    try:
        response = requests.get(verify_url, timeout=30)
        result["public_verify_ok"] = response.ok and response.text.strip() == "codex-ok"
    except requests.RequestException as exc:
        result["errors"].append(f"public callback failed: {type(exc).__name__}")
        return _done(result, 1)
    if not result["public_verify_ok"]:
        result["errors"].append("public callback did not return challenge")
        return _done(result, 1)

    session = requests.Session()
    session.trust_env = False
    graph = f"https://graph.facebook.com/{version}"

    for page_id in page_ids:
        row = {"page_id": page_id, "page_token": False, "get_ok": False, "post_ok": False, "error": None}
        page = _graph_get(session, graph, page_id, token, {"fields": "access_token"})
        page_token = (page.get("data") or {}).get("access_token") if page.get("ok") else None
        row["page_token"] = bool(page_token)
        if not page_token:
            row["error"] = page.get("error") or "page access token unavailable"
            result["page_subscriptions"].append(row)
            continue

        before = _graph_get(session, graph, f"{page_id}/subscribed_apps", page_token, {})
        row["get_ok"] = bool(before.get("ok"))
        if not before.get("ok"):
            row["error"] = before.get("error")

        post = _graph_post(
            session,
            graph,
            f"{page_id}/subscribed_apps",
            page_token,
            {
                "subscribed_fields": "feed,messages,mention,conversations",
            },
        )
        row["post_ok"] = bool(post.get("ok"))
        if not post.get("ok"):
            row["error"] = post.get("error")
        result["page_subscriptions"].append(row)

    result["ok"] = all(row.get("post_ok") for row in result["page_subscriptions"])
    return _done(result, 0 if result["ok"] else 2)


def _done(result: dict, code: int) -> int:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _graph_get(session: requests.Session, graph: str, path: str, token: str, params: dict[str, str]) -> dict:
    request_params = dict(params)
    request_params["access_token"] = token
    try:
        response = session.get(f"{graph}/{path}", params=request_params, timeout=25)
    except requests.RequestException as exc:
        return {"ok": False, "error": type(exc).__name__}
    return _graph_result(response)


def _graph_post(session: requests.Session, graph: str, path: str, token: str, payload: dict[str, str]) -> dict:
    data = dict(payload)
    data["access_token"] = token
    try:
        response = session.post(f"{graph}/{path}", data=data, timeout=25)
    except requests.RequestException as exc:
        return {"ok": False, "error": type(exc).__name__}
    return _graph_result(response)


def _graph_result(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.ok:
        return {"ok": True, "data": payload}
    error = payload.get("error") if isinstance(payload, dict) else {}
    message = error.get("message") if isinstance(error, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if code:
        message = f"{message or 'Graph error'} (code {code})"
    return {"ok": False, "error": message or f"HTTP {response.status_code}"}


if __name__ == "__main__":
    raise SystemExit(main())
