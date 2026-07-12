"""Ad-platform MCP connectors — the system's own hands on the ad platforms.

Built on gateway/mcp_client.py. Every server here came out of our OWN research lab
(see SHARED_CONTEXT § "Radar — open findings"): Meta Ads (official, 2026-04-29),
TikTok Ads, AdRoll, Canva. This is the lab's knowledge turned into capability.

WHY TOKENS, NOT A BROWSER LOGIN: Meta's OAuth metadata advertises only
`authorization_code` + `refresh_token` (no `client_credentials`), so a token cannot be
minted machine-to-machine. Meta's own answer for always-on server use is a **System
User token** (Business Manager → System user → Generate token), which never expires and
is sent as a plain bearer. That token is scoped (ads_management/ads_read/...) and
revocable — strictly safer than automating a Facebook password login, which would mean
holding the owner's master credential and logging in from a datacenter IP.

SECURITY (the system's #1 non-negotiable): tools that spend money or change live
campaigns (create/update/delete/pause/resume/budget/bid/publish) are classified WRITE and
are REFUSED unless the caller passes approved=True — which only the human-checkpoint path
(Telegram /approve, panel approval) is allowed to do. Reads are free.

Tokens never live in git: put them in .env via the existing owner-only Telegram
`/setkey META_ADS_TOKEN <token>` flow.

CLI:
    python3 -m gateway.ad_mcp status              # readiness of every connector
    python3 -m gateway.ad_mcp tools meta          # list the platform's tools
    python3 -m gateway.ad_mcp call meta <tool> '<json>'   # read-only unless --approve
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gateway.mcp_client import McpAuthError, McpClient, McpError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# Every entry here is a finding the research lab surfaced and we turned into capability.
REGISTRY: dict[str, dict[str, str]] = {
    "meta": {
        "url": "https://mcp.facebook.com/ads",
        "token_env": "META_ADS_TOKEN",
        "label": "Meta Ads (Facebook/Instagram) — official MCP, open beta 2026-04-29",
        "token_how": "Business Manager → System users → Generate token "
                     "(scopes: ads_management, ads_read, business_management)",
    },
    "tiktok": {
        "url": "https://mcp.tiktok.com/ads",
        "token_env": "TIKTOK_ADS_TOKEN",
        "label": "TikTok Ads — MCP server (lab finding 2026-06-19)",
        "token_how": "TikTok Ads Manager → Developer → access token",
    },
    "adroll": {
        "url": "https://mcp.adroll.com",
        "token_env": "ADROLL_TOKEN",
        "label": "AdRoll — MCP open beta (lab finding 2026-06-06)",
        "token_how": "AdRoll dashboard → API access",
    },
    "canva": {
        "url": "https://mcp.canva.com",
        "token_env": "CANVA_TOKEN",
        "label": "Canva — brand-kit MCP connector (lab finding 2026-06-16)",
        "token_how": "Canva developer portal → connect app",
    },
}

# A tool that can spend money or mutate a live campaign. Refused without a human checkpoint.
WRITE_MARKERS = (
    "create", "update", "delete", "remove", "pause", "resume", "activate", "archive",
    "budget", "bid", "launch", "publish", "upload", "duplicate", "set_", "edit",
)


def is_write_tool(name: str) -> bool:
    n = (name or "").lower()
    return any(m in n for m in WRITE_MARKERS)


def _env() -> dict[str, str]:
    """Read .env (never committed) then let real environment override."""
    data: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip().strip('"').strip("'")
    data.update({k: v for k, v in os.environ.items() if k in
                 {c["token_env"] for c in REGISTRY.values()}})
    return data


def token_for(platform: str) -> str:
    cfg = REGISTRY[platform]
    return _env().get(cfg["token_env"], "")


def client_for(platform: str) -> McpClient:
    if platform not in REGISTRY:
        raise McpError(f"unknown platform {platform!r} — known: {', '.join(REGISTRY)}")
    cfg = REGISTRY[platform]
    return McpClient(cfg["url"], token_for(platform))


def status(platform: str | None = None) -> list[dict[str, Any]]:
    """Readiness per connector: is a token present, and does the server answer?"""
    out = []
    for name in ([platform] if platform else list(REGISTRY)):
        cfg = REGISTRY[name]
        row: dict[str, Any] = {"platform": name, "label": cfg["label"],
                               "url": cfg["url"], "token_env": cfg["token_env"]}
        tok = token_for(name)
        row["has_token"] = bool(tok)
        if not tok:
            row["state"] = "needs-token"
            row["next_step"] = (f"owner mints it: {cfg['token_how']}, then Telegram: "
                                f"/setkey {cfg['token_env']} <token>")
            out.append(row)
            continue
        try:
            tools = client_for(name).list_tools()
            row["state"] = "live"
            row["tools"] = len(tools)
            row["write_tools"] = sum(1 for t in tools if is_write_tool(t.get("name", "")))
        except McpAuthError as e:
            row["state"] = "bad-token"
            row["detail"] = f"{e} (scopes: {e.scopes})"
        except McpError as e:
            row["state"] = "error"
            row["detail"] = str(e)
        out.append(row)
    return out


def list_tools(platform: str) -> list[dict[str, Any]]:
    return client_for(platform).list_tools()


def call(platform: str, tool: str, arguments: dict[str, Any] | None = None,
         *, approved: bool = False) -> Any:
    """Call a tool. WRITE tools require approved=True — the human-checkpoint path only.

    Never let an LLM set approved=True on its own: it must come from an owner-authed
    approval (Telegram /approve N, panel approval), same as every other risky action.
    """
    if is_write_tool(tool) and not approved:
        raise PermissionError(
            f"'{tool}' on {platform} is a WRITE action (it can change or spend a live "
            f"ad budget). It requires a human checkpoint — park it for /approve; "
            f"never auto-execute."
        )
    return client_for(platform).call_tool(tool, arguments or {})


def _main(argv: list[str]) -> int:
    if not argv or argv[0] == "status":
        print(json.dumps(status(argv[1] if len(argv) > 1 else None),
                         ensure_ascii=False, indent=2))
        return 0
    try:
        if argv[0] == "tools" and len(argv) > 1:
            for t in list_tools(argv[1]):
                flag = "WRITE" if is_write_tool(t.get("name", "")) else "read"
                print(f"[{flag}] {t.get('name')}: {(t.get('description') or '')[:80]}")
        elif argv[0] == "call" and len(argv) > 2:
            approved = "--approve" in argv
            args = json.loads(argv[3]) if len(argv) > 3 and argv[3] != "--approve" else {}
            print(json.dumps(call(argv[1], argv[2], args, approved=approved),
                             ensure_ascii=False, indent=2))
        else:
            print(__doc__)
            return 1
    except PermissionError as e:
        print(f"BLOCKED (checkpoint): {e}")
        return 4
    except McpAuthError as e:
        print(f"AUTH: {e}\n  scopes: {e.scopes}")
        return 2
    except McpError as e:
        print(f"ERROR: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
