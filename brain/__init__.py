"""RAMIN OS — Knowledge Core (the system's institutional memory & learning loop).

The idea: the valuable things we decide, learn, and get right should not evaporate
when a session ends. They are captured as plain markdown (the source of truth),
made retrievable, and fed back into future work -- so the operator, the agent, and
the system all get a little stronger every day.

Public API (stable):
    remember(title, body, ...)      -> Entry      # capture a piece of knowledge
    recall(query, k=5)              -> list[Hit]  # find relevant past knowledge
    recall_block(query)             -> str        # ready-to-inject prompt context
    reflect(task, result)           -> list[Entry]# distill a job into lessons (pending)
    all_entries() / get(id) / stats()

Everything is dependency-light and degrades gracefully when the LLM/embedding
free tier is unavailable. See brain/README.md.
"""

from __future__ import annotations

from . import blackboard
from .blackboard import assemble_context, observe
from .capture import distill, reflect
from .retrieval import Hit, recall, recall_block
from .store import (
    Entry,
    all_entries,
    approve_pending,
    delete,
    get,
    list_pending,
    rebuild_index_file,
    reject_pending,
    remember,
    save,
    stats,
)

__all__ = [
    "Entry",
    "Hit",
    "blackboard",
    "assemble_context",
    "observe",
    "remember",
    "recall",
    "recall_block",
    "reflect",
    "distill",
    "all_entries",
    "get",
    "save",
    "delete",
    "stats",
    "list_pending",
    "approve_pending",
    "reject_pending",
    "rebuild_index_file",
]
