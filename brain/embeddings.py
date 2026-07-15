"""Optional embedding accelerator for recall.

Embeddings make recall *semantically* aware ("car insurance" finds "KASKO"), but
the brain must never depend on a hosted model. This module:

  - is OFF by default (set ``BRAIN_EMBEDDINGS=1`` to enable recall reranking),
  - supports Gemini plus local/private TEI or OpenAI-compatible embedding
    endpoints,
  - caches every vector to ``data/memory/.embeddings.json`` keyed by provider,
    model, endpoint, and content hash,
  - degrades silently to ``None`` on any error, letting recall fall back to pure
    keyword scoring.

Hosted/external endpoints are blocked by default. For customer or internal data,
use localhost/private TEI, llama.cpp/vLLM/SGLang/Ollama-side adapters, or another
approved private endpoint.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from . import store

# text-embedding-004 was retired by Google (404 as of 2026-07); the GA
# replacement line is gemini-embedding-001 / gemini-embedding-2.
_DEFAULT_GEMINI_MODEL = "gemini-embedding-001"
_DEFAULT_LOCAL_MODEL = "Qwen/Qwen3-Embedding-0.6B"

_cache: dict[str, list[float]] | None = None
_cache_path = None


def enabled() -> bool:
    return os.getenv("BRAIN_EMBEDDINGS", "0").lower() in {"1", "true", "yes", "on"}


def _provider() -> str:
    raw = os.getenv("BRAIN_EMBED_PROVIDER", "auto").strip().lower()
    if raw in {"gemini", "tei", "openai"}:
        return raw
    if raw == "local":
        return "tei"
    endpoint = _endpoint(expand_default=False)
    if endpoint:
        parsed = urlparse(endpoint)
        return "openai" if parsed.path.rstrip("/").endswith("/v1/embeddings") else "tei"
    return "gemini"


def _model() -> str:
    default = _DEFAULT_GEMINI_MODEL if _provider() == "gemini" else _DEFAULT_LOCAL_MODEL
    return os.getenv("BRAIN_EMBED_MODEL", default).strip() or default


def _endpoint(*, expand_default: bool = True) -> str:
    endpoint = os.getenv("BRAIN_EMBED_ENDPOINT", "").strip()
    if endpoint:
        return endpoint
    if not expand_default:
        return ""
    provider = os.getenv("BRAIN_EMBED_PROVIDER", "auto").strip().lower()
    if provider == "openai":
        return "http://127.0.0.1:8080/v1/embeddings"
    if provider in {"tei", "local"}:
        return "http://127.0.0.1:8080/embed"
    return ""


def _timeout() -> float:
    try:
        value = float(os.getenv("BRAIN_EMBED_TIMEOUT_SECONDS", "8"))
    except ValueError:
        value = 8.0
    return max(1.0, min(value, 60.0))


def _allow_external() -> bool:
    return os.getenv("BRAIN_EMBED_ALLOW_EXTERNAL", "0").lower() in {"1", "true", "yes", "on"}


def _cache_file():
    return store.STORE_DIR / ".embeddings.json"


def _load_cache() -> dict[str, list[float]]:
    global _cache, _cache_path
    path = _cache_file()
    if _cache is not None and _cache_path == path:
        return _cache
    _cache_path = path
    if path.exists():
        try:
            _cache = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    else:
        _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    try:
        path = _cache_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _key(text: str) -> str:
    scope = {
        "provider": _provider(),
        "model": _model(),
        "endpoint": _endpoint(expand_default=False),
        "text": text,
    }
    raw = json.dumps(scope, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


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


def _coerce_vector(payload: Any) -> list[float] | None:
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list) and payload["data"]:
            return _coerce_vector(payload["data"][0].get("embedding"))
        if "embedding" in payload:
            return _coerce_vector(payload["embedding"])
        if "embeddings" in payload:
            return _coerce_vector(payload["embeddings"])
        if "vector" in payload:
            return _coerce_vector(payload["vector"])
    if isinstance(payload, list):
        if payload and isinstance(payload[0], list):
            return _coerce_vector(payload[0])
        if all(isinstance(item, (int, float)) for item in payload):
            return [float(item) for item in payload]
    return None


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - endpoint is locally guarded above.
        return json.loads(resp.read().decode("utf-8"))


def _embed_endpoint(text: str) -> list[float] | None:
    endpoint = _endpoint()
    if not endpoint:
        return None
    if not (_allow_external() or _endpoint_is_private(endpoint)):
        return None

    provider = _provider()
    parsed = urlparse(endpoint)
    is_openai_shape = provider == "openai" or parsed.path.rstrip("/").endswith("/v1/embeddings")
    payload = {"model": _model(), "input": text} if is_openai_shape else {"inputs": text}
    headers = {"Content-Type": "application/json"}
    token = os.getenv("BRAIN_EMBED_AUTH_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return _coerce_vector(_post_json(endpoint, payload, headers, _timeout()))
    except Exception:
        return None


def _embed_gemini(text: str) -> list[float] | None:
    api_key = _api_key()
    if not api_key:
        return None
    try:
        from google import genai

        # google-genai prefers the GOOGLE_API_KEY env var even when api_key is
        # passed explicitly — a stale key there silently shadows a fresh
        # GEMINI_API_KEY (observed live 2026-07-15). Hide it for the call.
        shadow = os.environ.pop("GOOGLE_API_KEY", None)
        try:
            client = genai.Client(api_key=api_key)
            resp = client.models.embed_content(model=_model(), contents=text)
        finally:
            if shadow is not None:
                os.environ["GOOGLE_API_KEY"] = shadow
        return [float(v) for v in resp.embeddings[0].values]
    except Exception:
        return None


def provider_info() -> dict[str, Any]:
    """Network-free, secret-free status for operators and tests."""
    endpoint = _endpoint()
    return {
        "enabled": enabled(),
        "provider": _provider(),
        "model": _model(),
        "endpoint": _safe_endpoint(endpoint),
        "endpoint_private": _endpoint_is_private(endpoint) if endpoint else None,
        "external_allowed": _allow_external(),
        "cache_file": str(_cache_file()),
    }


def embed(text: str, *, use_cache: bool = True, require_enabled: bool = True) -> list[float] | None:
    """Return a vector for ``text``, or ``None`` if embeddings are unavailable.

    Never raises -- a failure here just means recall uses keywords only.
    """
    if require_enabled and not enabled():
        return None
    if not text:
        return None
    key = _key(text)
    cache = _load_cache()
    if use_cache and key in cache:
        return cache[key]

    provider = _provider()
    vec = _embed_gemini(text) if provider == "gemini" else _embed_endpoint(text)
    if vec is None:
        return None
    cache[key] = vec
    _save_cache()
    return vec


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def warm(texts: list[str]) -> int:
    """Pre-embed a batch (e.g. after seeding). Returns how many succeeded."""
    if not enabled():
        return 0
    ok = 0
    for t in texts:
        if embed(t) is not None:
            ok += 1
    return ok
