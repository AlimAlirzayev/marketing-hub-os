"""Security guardrails for autonomous gateway execution.

This module is intentionally small and dependency-free. It is the central place
for decisions that must happen before an agent gets tools, a browser, or a
subprocess. The default posture is conservative: block secret exposure,
destructive actions, payment actions, local-network browsing, and unknown
automation scripts.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
AUDIT_LOG = ROOT_DIR / "data" / "logs" / "security_audit.jsonl"


@dataclass
class SecurityDecision:
    allowed: bool
    category: str
    severity: str
    reason: str
    matched_terms: list[str] = field(default_factory=list)


_SECRET_TERMS = (
    "api key",
    "apikey",
    "access token",
    "auth token",
    "bearer",
    "credential",
    "credentials",
    "password",
    "private key",
    "secret",
    ".env",
    "cookie",
    "session",
)

_EXFILTRATION_TERMS = (
    "show",
    "print",
    "display",
    "send",
    "upload",
    "post",
    "share",
    "copy",
    "export",
    "exfiltrate",
    "leak",
    "read out",
    "goster",
    "goster",
    "gonder",
    "paylas",
)

_DESTRUCTIVE_TERMS = (
    "delete all",
    "remove all",
    "wipe",
    "format",
    "drop table",
    "truncate",
    "rm -rf",
    "del /s",
    "erase",
    "destroy",
    "hamisini sil",
    "hamisini temizle",
    "bazani sil",
)

_PAYMENT_TERMS = (
    "buy",
    "pay",
    "purchase",
    "checkout",
    "place order",
    "send money",
    "wire transfer",
    "subscribe",
    "book now",
    "ode",
    "odenis",
    "al",
    "sifaris",
)

_LOCAL_HOSTS = {
    "localhost",
    "0.0.0.0",
    "127.0.0.1",
    "::1",
}

_LOCAL_SUFFIXES = (
    ".localhost",
    ".local",
    ".lan",
    ".internal",
    ".intranet",
)

_ALLOWED_STUDIO_SCRIPTS = {
    "ads-studio": {"create_kasko_display.py", "verify_meta.py"},
    "social-studio": {"compose_for_brief.py", "render_post.py"},
    "copy-studio": set(),
    "video-studio": {"clipper.py", "render.py", "transcribe.py"},
    "price-hunter": {"cli.py", "hunt.py"},
}


def _norm(text: str) -> str:
    # Keep Azerbaijani mojibake out of the policy path by normalizing common
    # ASCII equivalents. The UI may be localized; the safety checks stay stable.
    return (text or "").casefold()


def _matches(text: str, terms: tuple[str, ...] | set[str]) -> list[str]:
    low = _norm(text)
    hits: list[str] = []
    for term in terms:
        needle = _norm(term)
        if len(needle) <= 3 and needle.replace("-", "").isalnum():
            if re.search(rf"\b{re.escape(needle)}\b", low):
                hits.append(term)
        elif needle in low:
            hits.append(term)
    return hits


def redact(text: str | None) -> str:
    """Remove obvious secrets before writing audit records or user messages."""
    if not text:
        return ""
    value = str(text)
    patterns = (
        (r"(?i)authorization\s*[:=]\s*bearer\s+[a-z0-9._\-]+", "Authorization: Bearer [REDACTED]"),
        (r"(?i)bearer\s+[a-z0-9._\-]+", "Bearer [REDACTED]"),
        (r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+", r"\1=[REDACTED]"),
        (r"(?i)authorization\s*[:=]\s*(?!bearer\s+\[redacted\])[^'\"\s]+", "Authorization=[REDACTED]"),
        (r"(?i)(moltbook|sk|xoxb|ghp|ya29)[a-z0-9_\-]{12,}", r"\1[REDACTED]"),
    )
    for pattern, replacement in patterns:
        value = re.sub(pattern, replacement, value)
    return value


def audit_event(event: str, decision: SecurityDecision, context: dict | None = None) -> None:
    """Append a redacted JSONL audit event. Audit logging must never crash jobs."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        safe_context = {}
        for key, value in (context or {}).items():
            safe_context[str(key)] = redact(value if isinstance(value, str) else json.dumps(value, default=str))
        record = {
            "ts": time.time(),
            "event": event,
            "decision": asdict(decision),
            "context": safe_context,
        }
        with AUDIT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        return


def allow(category: str = "allowed", reason: str = "No blocking risk detected.") -> SecurityDecision:
    return SecurityDecision(True, category, "info", reason)


def block(category: str, reason: str, matched_terms: list[str] | None = None) -> SecurityDecision:
    return SecurityDecision(False, category, "high", reason, matched_terms or [])


def checkpoint(category: str, reason: str, matched_terms: list[str] | None = None) -> SecurityDecision:
    """Not allowed yet, but not a hard block either: needs explicit human approval.
    Severity 'checkpoint' tells callers to surface an approval prompt, not a refusal."""
    return SecurityDecision(False, category, "checkpoint", reason, matched_terms or [])


# Acquiring a provider API key is sensitive (it writes a secret to .env), so it is
# gated separately from normal tasks: allowlisted providers only, off by default,
# and never run silently in the background. The key itself is never exposed by the
# caller — only a masked confirmation — so this does not violate the secret-exposure
# rule (the secret lands in .env, not in any chat/artifact).
_CREDENTIAL_PROVIDERS = {"rapidapi"}


def evaluate_credential_acquisition(provider: str) -> SecurityDecision:
    name = (provider or "").strip().casefold()
    if name not in _CREDENTIAL_PROVIDERS:
        return block(
            "unknown_credential_provider",
            "Credential acquisition is only allowed for explicitly allowlisted providers.",
            [provider or "(none)"],
        )
    if os.getenv("GATEWAY_ALLOW_CREDENTIALS", "0").casefold() not in {"1", "true", "yes", "on"}:
        return checkpoint(
            "credential_checkpoint",
            "Credential acquisition needs explicit operator approval (set GATEWAY_ALLOW_CREDENTIALS=1) "
            "and a one-time interactive browser login. It is never run silently in the background.",
        )
    return allow("credential_acquisition", "Provider allowlisted and operator approval present.")


# --- the human checkpoint: outward-facing actions pause for approval --------
#
# The charter: "Risky actions need checkpoints: posting, sending, spending,
# deleting, credentialed browsing, production writes." evaluate_task() above
# hard-blocks the worst (secret exfil, destruction, payments); this classifier
# catches the legitimate-but-outward rest (publish/send/call/deploy) so they
# PARK for operator approval instead of running silently. Tuned so that
# *drafting* ("3 post ideyası yaz") stays free while *acting* ("İnstagramda
# paylaş") pauses. False positives cost one /approve tap; false negatives cost
# an unwanted public action — so ambiguity leans toward the checkpoint.

_CHECKPOINT_TERMS = (
    # strong outward verbs, EN
    "publish", "deploy", "send email", "send a dm", "send dm", "send sms",
    "send message to", "tweet", "broadcast",
    # strong outward verbs, AZ (paylaş = post/share IS the publishing action)
    "paylaş", "paylas", "göndər", "gonder", "yayımla", "yayimla",
    "dərc et", "derc et", "zəng et", "zeng et", "zəng elə", "zeng ele",
)

# "post" alone is ambiguous in EN ("3 post ideas" = drafting) — only these
# phrasings mean actually pushing content out.
_CHECKPOINT_PHRASES = (
    "post to", "post on", "post it", "post this", "post the", "post now",
    "call the customer", "call customer", "call client", "email to", "email the",
)

_INTERNAL_DELIVERY_CUES = (
    "bura", "burda", "buraya", "mene", "mənə", "menim ucun", "mənim üçün",
    "goster", "göstər", "baxim", "baxım", "burada", "here", "show me",
    "send here", "send it here",
)


def evaluate_checkpoint(task: str) -> SecurityDecision:
    """Classify a task that already passed evaluate_task(): does it perform an
    outward-facing action that must wait for operator approval?"""
    low = _norm(task)
    if (
        any(cue in low for cue in _INTERNAL_DELIVERY_CUES)
        and not any(phrase in low for phrase in _CHECKPOINT_PHRASES)
        and "email" not in low
        and "customer" not in low
        and "müştəri" not in low
        and "musteri" not in low
    ):
        return allow("internal_delivery", "Request is to show or attach a draft artifact in the current chat.")

    hits = _matches(task, _CHECKPOINT_TERMS) + _matches(task, _CHECKPOINT_PHRASES)
    if hits:
        return checkpoint(
            "outward_action",
            "Task performs an outward-facing action (publish/send/call/deploy). "
            "It is parked until the operator approves it.",
            hits,
        )
    return allow("task", "No outward-facing action detected.")


def evaluate_task(task: str) -> SecurityDecision:
    """Pre-flight a free-text task before autonomous execution starts."""
    low = _norm(task)
    secret_hits = _matches(low, _SECRET_TERMS)
    exfil_hits = _matches(low, _EXFILTRATION_TERMS)
    if secret_hits and exfil_hits:
        return block(
            "credential_exposure",
            "Task appears to request exposing, copying, or transmitting secrets.",
            secret_hits + exfil_hits,
        )

    destructive_hits = _matches(low, _DESTRUCTIVE_TERMS)
    if destructive_hits:
        return block(
            "destructive_action",
            "Task appears to request broad deletion or irreversible data changes.",
            destructive_hits,
        )

    payment_hits = _matches(low, _PAYMENT_TERMS)
    if payment_hits:
        return block(
            "payment_or_commitment",
            "Autonomous agents cannot make payments, purchases, bookings, or commitments.",
            payment_hits,
        )

    return allow("task", "Task passed security pre-flight.")


def validate_url(url: str) -> SecurityDecision:
    """Reject URLs that could expose local services, metadata, or credentials."""
    parsed = urlparse(url if "://" in url else "https://" + url)
    scheme = parsed.scheme.casefold()
    host = (parsed.hostname or "").casefold().strip(".")

    if scheme not in {"http", "https"}:
        return block("url_scheme", "Only http and https URLs are allowed.", [scheme])
    if not host:
        return block("url_host", "URL has no valid host.")
    if parsed.username or parsed.password:
        return block("url_credentials", "Credentials in URLs are not allowed.")
    if host in _LOCAL_HOSTS or any(host.endswith(suffix) for suffix in _LOCAL_SUFFIXES):
        return block("local_network", "Local or private network hosts are blocked.", [host])

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return allow("url", "URL passed browser safety checks.")

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return block("local_network", "Private, local, reserved, or metadata IPs are blocked.", [host])

    return allow("url", "URL passed browser safety checks.")


def validate_studio_script(studio_name: str, script_name: str) -> tuple[SecurityDecision, Path | None, Path | None]:
    """Allow only known studio scripts and keep paths inside their studio dir."""
    studio = (studio_name or "").strip()
    script = Path(script_name or "").name

    allowed_scripts = _ALLOWED_STUDIO_SCRIPTS.get(studio)
    if allowed_scripts is None:
        return (
            block("unknown_studio", "Unknown studio automation target.", [studio]),
            None,
            None,
        )
    if script not in allowed_scripts:
        return (
            block(
                "unknown_script",
                "Only explicitly allowlisted automation scripts may run.",
                [f"{studio}/{script}"],
            ),
            None,
            None,
        )

    studio_dir = (ROOT_DIR / studio).resolve()
    script_path = (studio_dir / script).resolve()
    try:
        script_path.relative_to(studio_dir)
    except ValueError:
        return (
            block("path_traversal", "Automation script path escaped the studio directory.", [script_name]),
            None,
            None,
        )
    if not script_path.exists():
        return (
            block("missing_script", "Allowlisted automation script does not exist.", [str(script_path)]),
            None,
            None,
        )

    return allow("studio_script", "Automation script is allowlisted."), studio_dir, script_path


def format_blocked_message(decision: SecurityDecision) -> str:
    terms = f"\n\nMatched terms: {', '.join(decision.matched_terms)}" if decision.matched_terms else ""
    return (
        "**Security Guard blocked this action.**\n\n"
        f"Category: `{decision.category}`\n\n"
        f"Reason: {decision.reason}{terms}\n\n"
        "This is intentional: autonomous execution must not expose secrets, "
        "touch private infrastructure, make payments, or perform destructive changes."
    )
