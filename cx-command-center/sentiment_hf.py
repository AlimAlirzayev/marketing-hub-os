"""Optional local/private Hugging Face sentiment signal for CX triage.

This adapter is intentionally conservative:

- off by default;
- only calls localhost/private endpoints unless explicitly allowed;
- never exposes tokens in status or errors;
- returns ``None`` on any problem so the deterministic CX rules stay in charge.

Expected endpoint shape is compatible with common Hugging Face text-classification
outputs, e.g. ``[{"label": "NEGATIVE", "score": 0.98}]`` or nested variants.
"""

from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

import config


@dataclass(frozen=True)
class SentimentSignal:
    sentiment: str
    confidence: float
    label: str
    model: str


def enabled() -> bool:
    return config.HF_SENTIMENT_ENABLED and bool(config.HF_SENTIMENT_ENDPOINT)


def _allow_external() -> bool:
    return config.HF_SENTIMENT_ALLOW_EXTERNAL


def _endpoint_is_private(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").strip(".").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    if any(host.endswith(suffix) for suffix in (".localhost", ".local", ".lan", ".internal", ".intranet")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _safe_endpoint(endpoint: str) -> str:
    if not endpoint:
        return ""
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, "", "", ""))


def status() -> dict[str, Any]:
    endpoint = config.HF_SENTIMENT_ENDPOINT
    return {
        "enabled": enabled(),
        "endpoint": _safe_endpoint(endpoint),
        "endpoint_private": _endpoint_is_private(endpoint) if endpoint else None,
        "external_allowed": _allow_external(),
        "model": config.HF_SENTIMENT_MODEL,
        "min_confidence": config.HF_SENTIMENT_MIN_CONFIDENCE,
    }


def _timeout() -> float:
    return max(1.0, min(float(config.HF_SENTIMENT_TIMEOUT_SECONDS), 30.0))


def _post(text: str) -> Any:
    endpoint = config.HF_SENTIMENT_ENDPOINT
    if not endpoint:
        return None
    if not (_allow_external() or _endpoint_is_private(endpoint)):
        return None

    payload: dict[str, Any] = {"inputs": text}
    if config.HF_SENTIMENT_MODEL:
        payload["model"] = config.HF_SENTIMENT_MODEL
    if config.HF_SENTIMENT_WAIT_FOR_MODEL:
        payload["options"] = {"wait_for_model": True}

    headers = {"Content-Type": "application/json"}
    token = os.getenv("CX_HF_SENTIMENT_AUTH_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(payload).encode("utf-8")
    req = Request(endpoint, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=_timeout()) as resp:  # noqa: S310 - guarded to private by default.
        return json.loads(resp.read().decode("utf-8"))


def _flatten(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            return _flatten(payload["results"])
        if isinstance(payload.get("data"), list):
            return _flatten(payload["data"])
        if "label" in payload:
            return [payload]
    if isinstance(payload, list):
        out: list[dict[str, Any]] = []
        for item in payload:
            out.extend(_flatten(item))
        return out
    return []


def _label_to_sentiment(label: str) -> str | None:
    value = (label or "").strip().lower()
    if not value:
        return None
    if value in {"negative", "neg", "label_0", "1 star", "1", "one"} or "negative" in value:
        return "negative"
    if value in {"neutral", "neu", "label_1", "3 stars", "3", "three"} or "neutral" in value:
        return "neutral"
    if value in {"positive", "pos", "label_2", "5 stars", "5", "five"} or "positive" in value:
        return "positive"
    if "2 stars" in value or value == "2":
        return "negative"
    if "4 stars" in value or value == "4":
        return "positive"
    return None


def _best(payload: Any) -> SentimentSignal | None:
    rows = _flatten(payload)
    best: tuple[float, str, str] | None = None
    for row in rows:
        label = str(row.get("label") or row.get("class") or row.get("sentiment") or "")
        sentiment = _label_to_sentiment(label)
        if not sentiment:
            continue
        try:
            score = float(row.get("score", row.get("confidence", row.get("probability", 0.0))))
        except (TypeError, ValueError):
            score = 0.0
        if best is None or score > best[0]:
            best = (score, sentiment, label)
    if best is None:
        return None
    score, sentiment, label = best
    if score < config.HF_SENTIMENT_MIN_CONFIDENCE:
        return None
    return SentimentSignal(
        sentiment=sentiment,
        confidence=max(0.0, min(score, 1.0)),
        label=label,
        model=config.HF_SENTIMENT_MODEL,
    )


def classify(text: str) -> SentimentSignal | None:
    if not enabled() or not text.strip():
        return None
    try:
        return _best(_post(text[: config.HF_SENTIMENT_MAX_CHARS]))
    except Exception:
        return None
