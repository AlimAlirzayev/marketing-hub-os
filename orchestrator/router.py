"""Xalq Insurance Digital OS - LLM router.

Picks which of the 4 hybrid LLMs handles a task, based on a coarse task tier:

    complex    -> Claude        (best reasoning / code)
    fast       -> Groq          (low latency, cheap)
    free_bulk  -> Gemini        (free high-volume work)
    private    -> Ollama        (offline, never leaves the machine)

This module is a skeleton: the routing logic is real, but the LLM calls are
stubbed. Wire the real provider clients where marked TODO before execution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class Tier(str, Enum):
    """Coarse task category that maps 1:1 to an LLM provider."""

    COMPLEX = "complex"
    FAST = "fast"
    FREE_BULK = "free_bulk"
    PRIVATE = "private"


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    model: str
    reason: str


# Default model id per tier; overridable via environment.
_TIER_MODELS: dict[Tier, ModelChoice] = {
    Tier.COMPLEX: ModelChoice(
        provider="anthropic",
        model=os.getenv("MODEL_COMPLEX", "claude-sonnet-4-6"),
        reason="complex reasoning / code generation",
    ),
    Tier.FAST: ModelChoice(
        provider="groq",
        model=os.getenv("MODEL_FAST", "llama-3.3-70b-versatile"),
        reason="low-latency, cost-sensitive task",
    ),
    Tier.FREE_BULK: ModelChoice(
        provider="gemini",
        model=os.getenv("MODEL_FREE_BULK", "gemini-3.5-flash"),
        reason="high-volume task on a free tier",
    ),
    Tier.PRIVATE: ModelChoice(
        provider="ollama",
        model=os.getenv("MODEL_PRIVATE", "gemma3:4b"),
        reason="sensitive data must stay on-device",
    ),
}

# Keywords that bump a task into a specific tier. First match wins.
_KEYWORD_TIERS: list[tuple[Tier, tuple[str, ...]]] = [
    (Tier.PRIVATE, ("private", "secret", "confidential", "offline", "personal")),
    (Tier.COMPLEX, ("code", "architecture", "refactor", "debug", "analyze", "strategy")),
    (Tier.FAST, ("classify", "extract", "summarize", "tag", "route")),
    (Tier.FREE_BULK, ("scrape", "bulk", "trend", "research", "monitor")),
]


def classify(task: str) -> Tier:
    """Return the routing tier for a free-text task description."""
    lowered = task.lower()
    for tier, keywords in _KEYWORD_TIERS:
        if any(kw in lowered for kw in keywords):
            return tier
    # Default: prefer the free bulk tier to conserve the paid budget.
    return Tier.FREE_BULK


def route(task: str, tier: Tier | None = None) -> ModelChoice:
    """Resolve a task to a concrete model choice.

    Pass an explicit ``tier`` to override keyword classification.
    """
    resolved = tier or classify(task)
    return _TIER_MODELS[resolved]


def get_llm(choice: ModelChoice):
    """Return an instantiated LangChain chat model for the given choice.

    TODO: wire real provider clients. Each branch currently raises so that
    callers fail loudly until the providers are configured.
    """
    if choice.provider == "anthropic":
        # from langchain_anthropic import ChatAnthropic
        # return ChatAnthropic(model=choice.model)
        raise NotImplementedError("anthropic client not wired yet")
    if choice.provider == "groq":
        # from langchain_groq import ChatGroq
        # return ChatGroq(model=choice.model)
        raise NotImplementedError("groq client not wired yet")
    if choice.provider == "gemini":
        # from langchain_google_genai import ChatGoogleGenerativeAI
        # return ChatGoogleGenerativeAI(model=choice.model)
        raise NotImplementedError("gemini client not wired yet")
    if choice.provider == "ollama":
        # from langchain_ollama import ChatOllama
        # return ChatOllama(model=choice.model, base_url=os.getenv("OLLAMA_BASE_URL"))
        raise NotImplementedError("ollama client not wired yet")
    raise ValueError(f"unknown provider: {choice.provider}")


if __name__ == "__main__":
    samples = [
        "refactor the payment module",
        "scrape this week's marketing trends",
        "classify these 200 leads by ICP fit",
        "summarize my private medical notes",
    ]
    for s in samples:
        c = route(s)
        print(f"{s!r:55} -> {c.provider:10} {c.model:30} ({c.reason})")
