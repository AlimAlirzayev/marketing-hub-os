"""Customer Relations Center readiness audit.

The script prints a concise production-readiness report without exposing
secrets. Use --external to call safe provider diagnostics such as Telegram
getMe and Meta asset discovery.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
CX_DIR = ROOT / "cx-command-center"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external", action="store_true", help="Call provider diagnostics.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args()

    sys.path.insert(0, str(CX_DIR))
    env = _read_env(ROOT / ".env")
    report = build_report(env, external=args.external)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))
    return 1 if report["summary"]["blockers"] else 0


def build_report(env: dict[str, str], *, external: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    cx_port = _port_open("127.0.0.1", 8810)
    hub_port = _port_open("127.0.0.1", 8000)
    checks.append(_check("cx_server", cx_port, "Customer Relations Center is listening on 8810"))
    checks.append(_check("main_dashboard", hub_port, "Marketing OS hub is listening on 8000"))

    health = _safe_get_json("http://127.0.0.1:8810/api/health") if cx_port else None
    integrations = _safe_get_json("http://127.0.0.1:8810/api/integrations/status") if cx_port else None
    checks.append(_check("cx_live_mode", bool(health and health.get("mode") == "live"), "CX_DATA_MODE is live"))

    checks.extend(
        [
            _check("ai_council_enabled", env.get("AI_COUNCIL_ENABLED") == "1", "AI Council is enabled"),
            _check("ai_auto_execute", env.get("AI_COUNCIL_AUTO_EXECUTE") == "1", "AI Council auto execution is enabled"),
            _check("api_fallback_disabled", env.get("AI_COUNCIL_ALLOW_API_FALLBACK") == "0", "Legacy API fallback is disabled"),
            _check("env_ignored", _gitignore_contains(".env"), ".env is ignored by git"),
            _check("env_backup_ignored", _gitignore_contains(".env.*"), "Local env backup files are ignored by git", severity="warn"),
        ]
    )

    checks.extend(
        [
            _check("chatplace_webhook", _is_set(env, "CX_WEBHOOK_SECRET"), "Chatplace webhook can use CX_WEBHOOK_SECRET"),
            _check("public_https_url", env.get("CX_PUBLIC_BASE_URL", "").startswith("https://"), "Public HTTPS base URL is configured for external webhooks"),
            _check("meta_webhook_verify", _is_set(env, "CX_META_VERIFY_TOKEN"), "Meta webhook verify token exists"),
            _check("meta_webhook_signature", _is_set(env, "CX_META_APP_SECRET"), "Meta app secret for webhook signature verification is configured", severity="warn"),
            _check("telegram_alerts_config", _is_set(env, "TELEGRAM_BOT_TOKEN") and _is_set(env, "CX_ALERT_CHAT_ID"), "Telegram alert token/chat are configured"),
            _check("meta_graph_token", _is_set(env, "META_GRAPH_ACCESS_TOKEN") or _is_set(env, "META_ACCESS_TOKEN"), "Meta Graph token exists"),
            _check("meta_assets", _is_set(env, "META_FACEBOOK_PAGE_IDS") or _is_set(env, "META_INSTAGRAM_BUSINESS_IDS"), "Meta Page or Instagram Business IDs are configured"),
            _check("google_reviews", all(_is_set(env, key) for key in ("GOOGLE_BUSINESS_PROFILE_ACCESS_TOKEN", "GOOGLE_BUSINESS_PROFILE_ACCOUNT_ID", "GOOGLE_BUSINESS_PROFILE_LOCATION_IDS")), "Google Business Profile reviews credentials are configured"),
            _check("chatplace_pull", _is_set(env, "CHATPLACE_PULL_URL"), "Optional Chatplace pull URL is configured", severity="warn"),
            _check("auto_sync", _int_env(env, "CX_SYNC_INTERVAL_SECONDS") > 0, "Background pull sync is enabled", severity="warn"),
        ]
    )

    if integrations:
        checks.append(_check("integration_endpoint", True, "Integration status endpoint returned successfully"))
        for name, info in (integrations.get("channels") or {}).items():
            checks.append(
                _check(
                    f"integration_{name}",
                    bool(info.get("configured")),
                    info.get("detail") or name,
                    severity="warn" if name in {"chatplace_pull", "meta_graph_pull", "google_reviews"} else "blocker",
                    extra={"missing": info.get("missing") or []},
                )
            )

    if external:
        checks.extend(_external_checks(env))

    blockers = [c for c in checks if c["status"] == "fail" and c["severity"] == "blocker"]
    warnings = [c for c in checks if c["status"] == "fail" and c["severity"] == "warn"]
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "summary": {
            "blockers": len(blockers),
            "warnings": len(warnings),
            "passed": len([c for c in checks if c["status"] == "pass"]),
        },
        "checks": checks,
        "next_actions": _next_actions(checks),
    }


def _external_checks(env: dict[str, str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if _is_set(env, "TELEGRAM_BOT_TOKEN"):
        token = env["TELEGRAM_BOT_TOKEN"]
        data = _safe_get_json(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
        checks.append(_check("telegram_get_me", bool(data and data.get("ok")), "Telegram bot token responds to getMe", severity="warn"))

    if _is_set(env, "META_ACCESS_TOKEN") or _is_set(env, "META_GRAPH_ACCESS_TOKEN"):
        data = _safe_get_json("http://127.0.0.1:8810/api/sync/meta/discover", timeout=30)
        if not data:
            data = _direct_meta_discovery(env)
        page_count = len((data or {}).get("pages") or [])
        ig_count = len((data or {}).get("instagram_business_accounts") or [])
        checks.append(
            _check(
                "meta_asset_discovery",
                bool(data and data.get("ok") and (page_count or ig_count)),
                "Meta token can discover Pages or Instagram Business accounts",
                extra={"pages": page_count, "instagram_business_accounts": ig_count},
            )
        )
        content = _direct_meta_content_access(env)
        if content:
            checks.append(
                _check(
                    "meta_content_access",
                    bool(content.get("ok")),
                    "Meta token can read configured Page feed and Instagram media surfaces",
                    extra=content,
                )
            )
    return checks


def _direct_meta_discovery(env: dict[str, str]) -> dict | None:
    token = env.get("META_GRAPH_ACCESS_TOKEN") or env.get("META_ACCESS_TOKEN") or ""
    if not token:
        return None
    version = env.get("META_GRAPH_API_VERSION") or env.get("META_API_VERSION") or "v25.0"
    base = f"https://graph.facebook.com/{version}"
    session = requests.Session()
    session.trust_env = False
    try:
        resp = session.get(
            f"{base}/me/accounts",
            params={
                "fields": "id,name,instagram_business_account{id,username,name}",
                "limit": 100,
                "access_token": token,
            },
            timeout=25,
        )
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    payload = resp.json()
    pages = payload.get("data") or []
    instagram_accounts = [
        page["instagram_business_account"]
        for page in pages
        if isinstance(page.get("instagram_business_account"), dict)
    ]
    return {"ok": True, "pages": pages, "instagram_business_accounts": instagram_accounts}


def _direct_meta_content_access(env: dict[str, str]) -> dict | None:
    token = env.get("META_GRAPH_ACCESS_TOKEN") or env.get("META_ACCESS_TOKEN") or ""
    if not token:
        return None
    version = env.get("META_GRAPH_API_VERSION") or env.get("META_API_VERSION") or "v25.0"
    base = f"https://graph.facebook.com/{version}"
    session = requests.Session()
    session.trust_env = False
    page_ids = [part.strip() for part in env.get("META_FACEBOOK_PAGE_IDS", "").split(",") if part.strip()]
    ig_ids = [part.strip() for part in env.get("META_INSTAGRAM_BUSINESS_IDS", "").split(",") if part.strip()]
    rows: list[dict[str, Any]] = []
    for page_id in page_ids:
        page = _meta_get(session, base, page_id, token, {"fields": "access_token"})
        page_token = (page.get("data") or {}).get("access_token") if page.get("ok") else None
        feed = _meta_get(
            session,
            base,
            f"{page_id}/feed",
            page_token or token,
            {"fields": "id,message,created_time", "limit": "1"},
        )
        rows.append(
            {
                "type": "facebook_page",
                "id": page_id,
                "page_token": bool(page_token),
                "feed_ok": bool(feed.get("ok")),
                "error": None if feed.get("ok") else feed.get("error"),
            }
        )
    for ig_id in ig_ids:
        media = _meta_get(
            session,
            base,
            f"{ig_id}/media",
            token,
            {"fields": "id,caption,permalink,timestamp", "limit": "1"},
        )
        rows.append(
            {
                "type": "instagram_business",
                "id": ig_id,
                "media_ok": bool(media.get("ok")),
                "error": None if media.get("ok") else media.get("error"),
            }
        )
    if not rows:
        return None
    return {"ok": all((row.get("feed_ok") or row.get("media_ok")) for row in rows), "checks": rows}


def _meta_get(session: requests.Session, base: str, path: str, token: str, params: dict[str, str]) -> dict:
    request_params = dict(params)
    request_params["access_token"] = token
    try:
        resp = session.get(f"{base}/{path}", params=request_params, timeout=25)
    except requests.RequestException as exc:
        return {"ok": False, "error": type(exc).__name__}
    if resp.ok:
        return {"ok": True, "data": resp.json()}
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else {}
    message = error.get("message") if isinstance(error, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if code:
        message = f"{message or 'Graph error'} (code {code})"
    return {"ok": False, "error": message or f"HTTP {resp.status_code}"}


def _next_actions(checks: list[dict[str, Any]]) -> list[str]:
    failed = {c["name"]: c for c in checks if c["status"] == "fail"}
    actions = []
    if "meta_assets" in failed or "meta_asset_discovery" in failed:
        actions.append("Add Page/Instagram Business IDs and a token with owned social permissions.")
    if "meta_content_access" in failed:
        actions.append("Request/enable Meta Page content and Instagram media/comment access, then regenerate META_GRAPH_ACCESS_TOKEN.")
    if "google_reviews" in failed:
        actions.append("Create/authorize Google Business Profile OAuth access and add account/location IDs.")
    if "chatplace_pull" in failed:
        actions.append("Keep webhook mode, or add CHATPLACE_PULL_URL if Chatplace offers a feed/export endpoint.")
    if "meta_webhook_signature" in failed:
        actions.append("Add CX_META_APP_SECRET before exposing Meta webhook publicly.")
    if "auto_sync" in failed:
        actions.append("Set CX_SYNC_INTERVAL_SECONDS after pull credentials are ready.")
    if "env_backup_ignored" in failed:
        actions.append("Ignore .env backup files or move secret backups outside the workspace.")
    return actions


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "Customer Relations Center readiness audit",
        f"Generated: {report['generated_at']}",
        f"Passed: {report['summary']['passed']} | Warnings: {report['summary']['warnings']} | Blockers: {report['summary']['blockers']}",
        "",
    ]
    for check in report["checks"]:
        mark = "OK" if check["status"] == "pass" else ("WARN" if check["severity"] == "warn" else "BLOCK")
        extra = ""
        if check.get("extra"):
            extra = " " + json.dumps(check["extra"], ensure_ascii=False)
        lines.append(f"[{mark}] {check['name']}: {check['message']}{extra}")
    if report["next_actions"]:
        lines.extend(["", "Next actions:"])
        lines.extend(f"- {item}" for item in report["next_actions"])
    return "\n".join(lines)


def _check(name: str, passed: bool, message: str, *, severity: str = "blocker", extra: dict | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "severity": severity,
        "message": message,
        "extra": extra or {},
    }


def _safe_get_json(url: str, timeout: int = 10) -> dict | None:
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.ok:
            return resp.json()
        return {"ok": False, "status_code": resp.status_code}
    except Exception:
        return None


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


def _is_set(env: dict[str, str], key: str) -> bool:
    return bool(env.get(key, "").strip())


def _int_env(env: dict[str, str], key: str) -> int:
    try:
        return int(env.get(key, "0") or "0")
    except ValueError:
        return 0


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def _gitignore_contains(pattern: str) -> bool:
    path = ROOT / ".gitignore"
    if not path.exists():
        return False
    return pattern in {line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()}


if __name__ == "__main__":
    raise SystemExit(main())
