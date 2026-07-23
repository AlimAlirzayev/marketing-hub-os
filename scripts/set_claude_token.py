#!/usr/bin/env python3
"""Install / refresh a Claude Code OAuth token for one rotation account, securely.

Run ON the box that hosts the bot (the VPS):
    python3 scripts/set_claude_token.py [account-name]

The token is typed at a HIDDEN prompt — never echoed, never in shell history or logs.
It is written into data/private_context/claude_accounts.json for the named account
(default: the one flagged "primary", else "account-1"), its cooldown cleared, then
verified with one tiny real call. The token value itself is never printed.

Get a token first, on a machine logged into the desired Claude account:
    claude setup-token
"""
from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gateway import claude_bridge as cb  # noqa: E402


def _pick(accts: list[dict], want: str | None) -> int | None:
    if want:
        for i, a in enumerate(accts):
            if a.get("name") == want:
                return i
        return None
    for i, a in enumerate(accts):
        if a.get("primary"):
            return i
    for i, a in enumerate(accts):
        if a.get("name") == "account-1":
            return i
    return 0 if accts else None


def main() -> int:
    want = sys.argv[1] if len(sys.argv) > 1 else None
    data = cb._load_accounts()
    accts = data.setdefault("accounts", [])
    idx = _pick(accts, want)
    if idx is None:
        if not want:
            print("No accounts found and no name given. "
                  "Usage: set_claude_token.py <account-name>")
            return 2
        accts.append({"name": want, "token": "", "cooldown_until": 0})
        idx = len(accts) - 1
    name = accts[idx].get("name")

    print(f"Installing a token for account: {name}")
    tok = getpass.getpass("Paste the Claude token (hidden), then Enter: ").strip()
    if not tok:
        print("Empty token — aborted.")
        return 1
    accts[idx]["token"] = tok
    accts[idx]["cooldown_until"] = 0
    cb._save_accounts(data)
    print("Saved to the accounts store. Verifying with one tiny call…")

    env = os.environ.copy()
    env["RAMIN_NO_HOOKS"] = "1"
    env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(k, None)
    try:
        p = subprocess.run(
            ["claude", "-p", "--output-format", "json",
             "--model", "claude-haiku-4-5-20251001", "--permission-mode", "default"],
            input="say OK", capture_output=True, text=True, timeout=45,
            env=env, encoding="utf-8", errors="replace")
        d = json.loads((p.stdout or "{}").strip() or "{}")
        res = (d.get("result") or "")[:120]
        if not d.get("is_error"):
            print(f"✅ {name}: the token WORKS — reply: {res[:40]}")
            print("   The bot will use this account (Opus 4.8 tier) on the next turn.")
        elif "weekly" in res.lower() or "session limit" in res.lower() \
                or "hit your" in res.lower():
            print(f"⚠️ {name}: the token AUTHENTICATES, but this account is currently "
                  f"capped ({res}). It will resume automatically when the cap resets — "
                  "no further action needed.")
        else:
            print(f"❌ {name}: token rejected (status {d.get('api_error_status')}): {res}")
            print("   Re-run `claude setup-token` on the right account and try again.")
    except Exception as e:  # noqa: BLE001
        print(f"verify error (token saved anyway): {str(e)[:140]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
