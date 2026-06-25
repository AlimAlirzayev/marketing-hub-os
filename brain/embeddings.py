"""Optional embedding accelerator for recall.

Embeddings make recall *semantically* aware ("car insurance" finds "KASKO"), but
the Gemini free tier is tight and flaky (see gateway/README), so the brain must
never *depend* on them. This module:

  - is OFF by default (set ``BRAIN_EMBEDDINGS=1`` to enable),
  - caches every vector to ``data/memory/.embeddings.json`` keyed by content hash,
    so an entry is embedded once and reused forever,
  - degrades silently to ``None`` on any error (no key, rate limit, offline),
    letting recall fall back to pure keyword scoring.

The cache is keyed by a hash of the text, so editing an entry re-embeds only that
entry, and the keyword layer keeps working even if this whole file no-ops.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from .store import STORE_DIR

_CACHE_FILE = STORE_DIR / ".embeddings.json"
_MODEL = os.getenv("BRAIN_EMBED_MODEL", "text-embedding-004")

_cache: dict[str, list[float]] | None = None


def enabled() -> bool:
    return os.getenv("BRAIN_EMBEDDINGS", "0").lower() in {"1", "true", "yes", "on"}


def _load_cache() -> dict[str, list[float]]:
    global _cache
    if _cache is not None:
        return _cache
    if _CACHE_FILE.exists():
        try:
            _cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    else:
        _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def embed(text: str, *, use_cache: bool = True) -> list[float] | None:
    """Return a vector for ``text``, or ``None`` if embeddings are unavailable.

    Never raises -- a failure here just means recall uses keywords only.
    """
    if not enabled():
        return None
    key = _key(text)
    cache = _load_cache()
    if use_cache and key in cache:
        return cache[key]
    api_key = _api_key()
    if not api_key:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        resp = client.models.embed_content(model=_MODEL, contents=text)
        vec = list(resp.embeddings[0].values)
    except Exception:
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
