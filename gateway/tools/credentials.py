"""Governed credential-acquisition capability for the autonomous gateway.

The gateway's own browser deliberately REFUSES login/credential flows (the
security prime directive blocks secret exposure). This capability fills that gap
*safely* by delegating to the standalone `doit` agent, which drives the operator's
own browser session to fetch an API key and write it to `.env`.

Guarantees that keep this inside the prime directive:
  * allowlisted providers only (see security.evaluate_credential_acquisition),
  * OFF by default — needs explicit operator approval (GATEWAY_ALLOW_CREDENTIALS=1),
  * never silent: doit requires a one-time interactive browser login,
  * the raw key is NEVER returned — only a masked confirmation. The secret lands
    in `.env`, not in any chat reply, Telegram message, or job artifact.

Every decision is audited via security.audit_event (redacted).
"""

from __future__ import annotations

import os

from .. import security

PROVIDERS = ("rapidapi",)


def _approved_by_env() -> bool:
    return os.getenv("GATEWAY_ALLOW_CREDENTIALS", "0").casefold() in {"1", "true", "yes", "on"}


def _checkpoint_message(provider: str, decision: security.SecurityDecision) -> str:
    return (
        "**Checkpoint — kredensial əldə etmə təsdiq tələb edir.**\n\n"
        f"Provider: `{provider}`\n\n"
        f"{decision.reason}\n\n"
        "Bu, fonda səssiz işləmir (bir dəfəlik brauzer login lazımdır). İcazə üçün:\n"
        "1. `.env`-də `GATEWAY_ALLOW_CREDENTIALS=1` təyin et, **və ya**\n"
        f"2. birbaşa işə sal:  `.venv\\Scripts\\python -m doit {provider}`\n\n"
        "Açar `.env`-ə yazılacaq və heç bir yerdə ifşa olunmayacaq."
    )


def acquire(provider: str, *, approved: bool | None = None, headless: bool = False) -> str:
    """Acquire a provider key (governed). Returns a human message, never the raw key."""
    provider = (provider or "").strip().lower()
    decision = security.evaluate_credential_acquisition(provider)
    security.audit_event("credential_acquisition", decision, {"provider": provider})

    if decision.category == "unknown_credential_provider":
        return security.format_blocked_message(decision)  # hard block, no override

    # checkpoint is satisfiable by explicit caller approval OR the operator env flag
    ok = approved if approved is not None else _approved_by_env()
    if not ok:
        return _checkpoint_message(provider, decision)

    try:
        import doit
    except Exception as exc:  # noqa: BLE001
        return f"doit yüklənə bilmədi: {security.redact(str(exc))}"

    res = doit.acquire(provider, headless=headless)
    if res.get("ok"):
        try:
            from .. import sense
            sense.emit("credential", f"{res['env_var']} acquired", {"provider": provider})
        except Exception:
            pass
        return (
            f"**Uğur:** `{res['env_var']}` .env-ə {res.get('action', 'yazıldı')} "
            f"(maskalı: {res.get('key_preview', '***')}). Açar ifşa olunmur."
        )
    return f"Kredensial əldə olunmadı: {security.redact(str(res.get('error', 'naməlum')))}"


def acquire_api_credential(provider: str) -> str:
    """Acquire an API key for an allowlisted provider via the doit agent, store it in .env.

    Use ONLY when a task cannot proceed without a provider API key (e.g. "rapidapi").
    Returns a masked confirmation, or a checkpoint asking for explicit operator
    approval. Never returns the raw key.
    """
    return acquire(provider)
