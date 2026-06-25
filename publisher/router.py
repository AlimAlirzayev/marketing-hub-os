"""Xalq Insurance Digital OS Publisher - the cascade dispatcher.

Routes a publish plan through the free-first cascade from
claude-agents/.claude/capabilities.md → `publish`:

    Postiz (self-hosted, free)  →  manual handoff (always works)

No silent drops: a platform with no live channel, or any Postiz failure, falls
to a labelled manual block instead of vanishing. Returns a per-entry result so
the report is honest about what actually happened.
"""

from __future__ import annotations

from . import manual
from .postiz import Postiz, PostizError


def publish(plan: dict, *, dry_run: bool = False) -> dict:
    """Execute the plan. Returns {provider, results:[...], manual_dir?}."""
    entries = plan["entries"]

    if dry_run:
        folder = manual.write_manual(plan, reason="dry-run (no network contacted)")
        return {
            "provider": "dry-run",
            "manual_dir": str(folder),
            "results": [_res(e, "planned", f"{folder / (e['platform'] + '.txt')}") for e in entries],
        }

    # --- Tier 1: Postiz (free, self-hosted) ------------------------------- #
    try:
        client = Postiz()
        channels = client.list_integrations()
    except PostizError as e:
        folder = manual.write_manual(plan, reason=f"Postiz unavailable: {e}")
        return {
            "provider": "manual",
            "reason": str(e),
            "manual_dir": str(folder),
            "results": [_res(e2, "manual", f"{folder / (e2['platform'] + '.txt')}") for e2 in entries],
        }

    by_provider: dict[str, dict] = {}
    for ch in channels:
        by_provider.setdefault(ch["provider"], ch)   # first channel per provider

    media_obj = None
    if plan.get("media"):
        try:
            media_obj = client.upload(plan["media"])
        except PostizError as e:
            media_obj = None
            plan = {**plan, "_upload_error": str(e)}

    results, unrouted = [], []
    for e in entries:
        ch = by_provider.get(e["provider"])
        if not ch:                                    # channel not connected
            unrouted.append(e)
            results.append(_res(e, "manual", "channel not connected in Postiz"))
            continue
        try:
            resp = client.create_post(
                integration_id=ch["id"], content=e["caption"], media=media_obj,
                provider=e["provider"], post_type=plan["type"], date_iso=e["scheduled_at"],
            )
            state = "posted" if plan["type"] == "now" else "scheduled"
            results.append(_res(e, state, _post_ref(resp)))
        except PostizError as err:
            unrouted.append(e)
            results.append(_res(e, "manual", f"Postiz error: {err}"))

    out = {"provider": "postiz", "results": results}
    if unrouted:                                      # write blocks for the strays
        folder = manual.write_manual(plan, unrouted, reason="not deliverable via Postiz")
        out["manual_dir"] = str(folder)
    return out


def _res(entry: dict, state: str, detail: str) -> dict:
    return {"platform": entry["platform"], "state": state, "detail": detail}


def _post_ref(resp) -> str:
    if isinstance(resp, dict):
        return str(resp.get("id") or resp.get("postId") or resp.get("url") or "ok")
    if isinstance(resp, list) and resp:
        first = resp[0]
        return str(first.get("id") or "ok") if isinstance(first, dict) else "ok"
    return "ok"
