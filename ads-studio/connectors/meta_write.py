"""Meta Marketing API — the WRITE half, behind a human checkpoint.

`connectors/meta.py` is a mature read-only adapter (insights, campaigns, segments)
with retry/backoff, error classification and token redaction. It has no POST verb,
so the system could *see* the ad account but never *act* on it. This module adds
exactly that missing verb, reusing meta.py's plumbing rather than forking it.

SAFETY — this drives a LIVE ad account with real spend:
  * Two-step by design: `propose()` returns a plain-language plan (with the CURRENT
    value read back from Meta, so the human sees what actually changes); `execute()`
    refuses to run unless `approved=True`. An LLM must never set that flag — it comes
    only from the owner-authed checkpoint (Telegram /approve N, panel approval), the
    same gate every other risky action uses.
  * Only REVERSIBLE operations exist here: pause, resume, set_daily_budget.
    No create, no delete — an agent must not be able to conjure or destroy campaigns.
  * Budget changes are bounded (BUDGET_MIN/MAX minor units) so a fat-fingered or
    hallucinated number cannot set a five-figure daily spend.

CLI (read + dry-run only; execution requires the checkpoint):
    python3 -m connectors.meta_write campaigns
    python3 -m connectors.meta_write propose pause <campaign_id>
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any

import requests

from config import META_ACCESS_TOKEN, META_API_VERSION

from .meta import (
    _BASE,
    _MAX_RETRIES,
    _TIMEOUT,
    _acc,
    _backoff,
    _parse_error,
    _retry_after,
    _sanitize,
    _session,
    MetaNotConfigured,
)

# A daily budget is in the account currency's MINOR unit (cents). Bounds exist so a
# bad number cannot become a catastrophic spend: 1.00 .. 1000.00 in account currency.
BUDGET_MIN = 100
BUDGET_MAX = 100_000

PAUSED = "PAUSED"
ACTIVE = "ACTIVE"

# Which object types we are willing to touch at all.
LEVELS = {"campaign", "adset", "ad"}


class WriteBlocked(PermissionError):
    """A write was attempted without an owner-authed approval."""


def _post(node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to a Graph node with meta.py's retry/error discipline (which is GET-only)."""
    if not META_ACCESS_TOKEN:
        raise MetaNotConfigured("META_ACCESS_TOKEN not set")
    url = f"{_BASE}/{META_API_VERSION}/{node_id}"
    data = {**payload, "access_token": META_ACCESS_TOKEN}
    last_msg = "Meta write failed"
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = _session.post(url, data=data, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            last_msg = _sanitize(str(exc))
            if attempt < _MAX_RETRIES:
                time.sleep(_backoff(attempt))
                continue
            raise type(exc)(last_msg) from None
        if resp.ok:
            return resp.json()
        msg, retryable = _parse_error(resp)
        last_msg = msg
        if retryable and attempt < _MAX_RETRIES:
            time.sleep(_retry_after(resp, attempt))
            continue
        raise requests.HTTPError(msg) from None
    raise requests.HTTPError(last_msg) from None


def _read_node(node_id: str, fields: str) -> dict[str, Any]:
    """Read an object's current state — so a proposal can show what really changes."""
    from .meta import _request
    return _request(f"{_BASE}/{META_API_VERSION}/{node_id}",
                    {"fields": fields, "access_token": META_ACCESS_TOKEN})


def list_campaigns(account_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    """Live campaigns with their status and budget — the operator's picking list."""
    from .meta import _request
    acc = _acc(account_id)
    data = _request(
        f"{_BASE}/{META_API_VERSION}/{acc}/campaigns",
        {"fields": "id,name,status,effective_status,daily_budget,lifetime_budget,objective",
         "limit": limit, "access_token": META_ACCESS_TOKEN},
    )
    return data.get("data", [])


def list_adsets(account_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """Live ad sets with their status and budget — the real budget lever on
    accounts without Campaign Budget Optimization (read-only)."""
    from .meta import _request
    acc = _acc(account_id)
    data = _request(
        f"{_BASE}/{META_API_VERSION}/{acc}/adsets",
        {"fields": "id,name,campaign_id,status,effective_status,daily_budget,lifetime_budget",
         "limit": limit, "access_token": META_ACCESS_TOKEN},
    )
    return data.get("data", [])


# ---------- step 1: propose (safe, read-only) ----------
def propose(op: str, node_id: str, *, level: str = "campaign",
            daily_budget: int | None = None) -> dict[str, Any]:
    """Build a checkpoint-ready plan. Reads the CURRENT value; changes nothing."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {sorted(LEVELS)}")
    if op not in {"pause", "resume", "set_daily_budget"}:
        raise ValueError(f"unsupported op {op!r} (only reversible ops are allowed)")

    current = _read_node(node_id, "id,name,status,effective_status,daily_budget")
    plan: dict[str, Any] = {
        "op": op,
        "level": level,
        "node_id": node_id,
        "name": current.get("name", "?"),
        "current_status": current.get("effective_status") or current.get("status"),
        "current_daily_budget": current.get("daily_budget"),
        "requires_approval": True,
    }

    if op == "pause":
        plan["change"] = {"status": PAUSED}
        plan["human"] = f"PAUSE {level} “{plan['name']}” (now {plan['current_status']})"
    elif op == "resume":
        plan["change"] = {"status": ACTIVE}
        plan["human"] = f"RESUME {level} “{plan['name']}” (now {plan['current_status']})"
    else:
        if daily_budget is None:
            raise ValueError("set_daily_budget requires daily_budget (minor units)")
        if not (BUDGET_MIN <= int(daily_budget) <= BUDGET_MAX):
            raise ValueError(
                f"daily_budget {daily_budget} outside the safety bounds "
                f"[{BUDGET_MIN}, {BUDGET_MAX}] minor units — refusing.")
        plan["change"] = {"daily_budget": int(daily_budget)}
        was = plan["current_daily_budget"]
        plan["human"] = (f"SET DAILY BUDGET of {level} “{plan['name']}” "
                         f"from {was} to {daily_budget} (minor units)")
    return plan


# ---------- step 2: execute (requires the human checkpoint) ----------
def execute(plan: dict[str, Any], *, approved: bool = False) -> dict[str, Any]:
    """Apply a plan from propose(). Refuses unless the OWNER approved it.

    `approved=True` must originate from the owner-authed checkpoint path only
    (Telegram /approve N, panel approval). Never let a model pass this itself.
    """
    if not approved:
        raise WriteBlocked(
            f"{plan.get('human', plan.get('op'))} — this changes a LIVE ad account "
            f"with real spend. It requires a human checkpoint: park it for /approve.")
    change = plan.get("change") or {}
    if not change:
        raise ValueError("plan has no change to apply")
    result = _post(plan["node_id"], change)
    return {"applied": True, "node_id": plan["node_id"], "change": change,
            "human": plan.get("human"), "meta_response": result}


def _main(argv: list[str]) -> int:
    try:
        if not argv or argv[0] == "campaigns":
            for c in list_campaigns():
                print(f"{c['id']}  {c.get('effective_status','?'):12} "
                      f"budget={c.get('daily_budget','-'):>8}  {c.get('name','')[:50]}")
        elif argv[0] == "propose" and len(argv) >= 3:
            budget = int(argv[3]) if len(argv) > 3 else None
            print(json.dumps(propose(argv[1], argv[2], daily_budget=budget),
                             ensure_ascii=False, indent=2))
        else:
            print(__doc__)
            return 1
    except MetaNotConfigured as e:
        print(f"NOT CONFIGURED: {e}")
        return 2
    except WriteBlocked as e:
        print(f"BLOCKED (checkpoint): {e}")
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
