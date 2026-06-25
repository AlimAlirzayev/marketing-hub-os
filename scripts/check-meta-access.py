"""Safe Meta Graph access check.

Reads .env, calls Meta Graph, and prints only non-secret diagnostics.
It never prints access tokens or token-bearing URLs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    env = _read_env(ROOT / ".env")
    token = env.get("META_GRAPH_ACCESS_TOKEN") or env.get("META_ACCESS_TOKEN") or ""
    version = env.get("META_GRAPH_API_VERSION") or env.get("META_API_VERSION") or "v25.0"
    page_ids = _csv(env.get("META_FACEBOOK_PAGE_IDS", ""))
    ig_ids = _csv(env.get("META_INSTAGRAM_BUSINESS_IDS", ""))

    result: dict[str, Any] = {
        "token_present": bool(token),
        "graph_version": version,
        "configured_page_ids": len(page_ids),
        "configured_instagram_business_ids": len(ig_ids),
        "me": None,
        "permissions": [],
        "pages": [],
        "instagram_business_accounts": [],
        "configured_asset_tests": [],
        "errors": [],
    }

    if not token:
        result["errors"].append("META_GRAPH_ACCESS_TOKEN or META_ACCESS_TOKEN is empty")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    base = f"https://graph.facebook.com/{version}"
    me = _get(base, "me", token, {"fields": "id,name"})
    if me["ok"]:
        result["me"] = me["data"]
    else:
        result["errors"].append(f"/me: {me['error']}")

    permissions = _get(base, "me/permissions", token, {"limit": "100"})
    if permissions["ok"]:
        result["permissions"] = permissions["data"].get("data") or []
    else:
        result["errors"].append(f"/me/permissions: {permissions['error']}")

    accounts = _get(
        base,
        "me/accounts",
        token,
        {
            "fields": "id,name,tasks,instagram_business_account{id,username,name}",
            "limit": "100",
        },
    )
    if accounts["ok"]:
        pages = accounts["data"].get("data") or []
        result["pages"] = [
            {
                "id": page.get("id"),
                "name": page.get("name"),
                "tasks": page.get("tasks") or [],
                "has_instagram_business_account": bool(page.get("instagram_business_account")),
            }
            for page in pages
        ]
        result["instagram_business_accounts"] = [
            page["instagram_business_account"]
            for page in pages
            if isinstance(page.get("instagram_business_account"), dict)
        ]
    else:
        result["errors"].append(f"/me/accounts: {accounts['error']}")

    for page_id in page_ids:
        test: dict[str, Any] = {"type": "facebook_page", "id": page_id}
        page = _get(base, page_id, token, {"fields": "id,name,access_token"})
        test["page_lookup_ok"] = page["ok"]
        test["page_lookup_error"] = None if page["ok"] else page["error"]
        page_token = (page.get("data") or {}).get("access_token") if page["ok"] else None
        test["page_access_token_available"] = bool(page_token)
        feed_system = _get(base, f"{page_id}/feed", token, {"fields": "id,message,created_time", "limit": "1"})
        test["feed_with_system_token_ok"] = feed_system["ok"]
        test["feed_with_system_token_error"] = None if feed_system["ok"] else feed_system["error"]
        if page_token:
            feed_page = _get(base, f"{page_id}/feed", page_token, {"fields": "id,message,created_time", "limit": "1"})
            test["feed_with_page_token_ok"] = feed_page["ok"]
            test["feed_with_page_token_error"] = None if feed_page["ok"] else feed_page["error"]
        result["configured_asset_tests"].append(test)

    for ig_id in ig_ids:
        media = _get(base, f"{ig_id}/media", token, {"fields": "id,caption,permalink,timestamp", "limit": "1"})
        result["configured_asset_tests"].append(
            {
                "type": "instagram_business",
                "id": ig_id,
                "media_lookup_ok": media["ok"],
                "media_lookup_error": None if media["ok"] else media["error"],
                "media_count_sample": len((media.get("data") or {}).get("data") or []) if media["ok"] else 0,
            }
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["pages"] or result["instagram_business_accounts"]:
        return 0
    return 2


def _get(base: str, path: str, token: str, params: dict[str, str]) -> dict[str, Any]:
    safe_params = dict(params)
    safe_params["access_token"] = token
    try:
        resp = requests.get(f"{base}/{path}", params=safe_params, timeout=25)
    except requests.RequestException as exc:
        return {"ok": False, "error": type(exc).__name__}
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.ok:
        return {"ok": True, "data": data}
    error = data.get("error") if isinstance(data, dict) else {}
    message = error.get("message") if isinstance(error, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if code:
        message = f"{message or 'Graph error'} (code {code})"
    return {"ok": False, "error": message or f"HTTP {resp.status_code}"}


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


if __name__ == "__main__":
    raise SystemExit(main())
