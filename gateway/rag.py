"""Retrieval-Augmented Generation (RAG) engine for Xalq Insurance Digital OS.

Uses the Brain embedding adapter to vectorize internal documents. The adapter can
use Gemini, but the preferred reinforcement path is local/private TEI or another
OpenAI-compatible embedding endpoint. If no provider is available, this module
fails clearly while the Brain's keyword recall remains unaffected.
"""

import json
import math
from pathlib import Path
from typing import Any

from brain import embeddings

# Local JSON-based Vector Database for MVP
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "vector_db.json"

def _get_embedding(text: str) -> list[float]:
    """Fetch a vector embedding through the shared Brain adapter."""
    vector = embeddings.embed(text, require_enabled=False)
    if vector is None:
        raise RuntimeError(
            "No embedding provider is available. Configure Gemini credentials or "
            "set BRAIN_EMBED_PROVIDER=tei with a local/private BRAIN_EMBED_ENDPOINT."
        )
    return vector

def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

def load_db() -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db: list[dict[str, Any]]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def add_document(text: str, metadata: dict[str, Any] = None) -> None:
    """Embeds and saves a new document to the knowledge base."""
    db = load_db()
    embedding = _get_embedding(text)
    doc = {"text": text, "metadata": metadata or {}, "embedding": embedding}
    db.append(doc)
    save_db(db)

def search(query: str, top_k: int = 3, threshold: float = 0.4) -> list[dict]:
    """Finds the most relevant documents for a given query."""
    db = load_db()
    if not db: return []
    query_emb = _get_embedding(query)
    results = [{"score": _cosine_similarity(query_emb, doc["embedding"]), **doc} for doc in db]
    valid = [r for r in results if r["score"] >= threshold]
    return sorted(valid, key=lambda x: x["score"], reverse=True)[:top_k]
