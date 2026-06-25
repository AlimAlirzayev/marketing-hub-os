"""Unified free-first LLM router — the 2026 standard, done right.

One OpenAI-compatible gateway (LiteLLM) over many providers, with per-request
routing and automatic fallback. Implements the hybrid 20/80 rule from
claude-agents/.claude/capabilities.md:

    tier="cheap"  → the 80%: scraping, parsing, scoring, first drafts
    tier="smart"  → the 20%: planning, final synthesis

Every entry is tried in order; unconfigured providers (no key) are skipped, and
any provider error falls through to the next — never a hard stop while a working
provider remains. Model ids are env-overridable because they drift; the cascade
shape is what matters.

    from llm_router import complete, complete_json
    text, model = complete("Summarize ...", tier="cheap")
    data, model = complete_json("Return JSON ...", tier="cheap")

CLI:  python llm_router.py --probe        # show configured providers + ping
      python llm_router.py "prompt" [--smart] [--json]
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent
USAGE_LOG = REPO / "data" / "logs" / "llm_usage.jsonl"


class RouterError(RuntimeError):
    """Every provider in the tier failed or none was configured."""


def _load_env() -> None:
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


# (litellm model id, env requirement). requirement: str key, tuple (any-of), or
# "OLLAMA" sentinel (local, needs a base url, no key).
def _cheap() -> list[tuple[str, object]]:
    # Order = best-quality-per-free first. When several providers are free,
    # quality wins (no cost downside); Groq/Cerebras are fast high-throughput
    # fallbacks for when Gemini's daily quota is hit or latency matters.
    gem = os.getenv("LLM_CHEAP_MODEL") or "gemini/gemini-2.5-flash"
    return [
        (gem, ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
        ("groq/llama-3.3-70b-versatile", "GROQ_API_KEY"),
        (os.getenv("LLM_CEREBRAS_MODEL") or "cerebras/llama3.3-70b", "CEREBRAS_API_KEY"),
        (os.getenv("LLM_OPENROUTER_CHEAP") or "openrouter/deepseek/deepseek-chat", "OPENROUTER_API_KEY"),
        ("deepseek/deepseek-chat", "DEEPSEEK_API_KEY"),
        (f"ollama/{os.getenv('OLLAMA_DEFAULT_MODEL', 'qwen2.5:7b')}", "OLLAMA"),
    ]


def _smart() -> list[tuple[str, object]]:
    gem = os.getenv("LLM_SMART_MODEL") or "gemini/gemini-2.5-pro"
    return [
        (gem, ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
        (os.getenv("LLM_OPENROUTER_SMART") or "openrouter/anthropic/claude-3.7-sonnet", "OPENROUTER_API_KEY"),
        ("deepseek/deepseek-reasoner", "DEEPSEEK_API_KEY"),
    ]


def _configured(req: object) -> bool:
    if req == "OLLAMA":
        return bool(os.getenv("OLLAMA_BASE_URL"))
    if isinstance(req, tuple):
        return any(os.getenv(k) for k in req)
    return bool(os.getenv(str(req)))


def _cascade(tier: str) -> list[tuple[str, object]]:
    return _cheap() if tier == "cheap" else _smart()


def available(tier: str = "cheap") -> list[str]:
    """Model ids that are actually configured for this tier (in order)."""
    _load_env()
    return [m for m, req in _cascade(tier) if _configured(req)]


def complete(
    prompt: str,
    *,
    system: str | None = None,
    tier: str = "cheap",
    want_json: bool = False,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> tuple[str, str]:
    """Run the prompt through the tier's cascade. Returns (text, model_used)."""
    _load_env()
    import litellm

    litellm.drop_params = True          # silently drop params a provider lacks
    litellm.suppress_debug_info = True

    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    kwargs: dict = {"temperature": temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if want_json:
        kwargs["response_format"] = {"type": "json_object"}

    tried, errors = [], []
    for model, req in _cascade(tier):
        if not _configured(req):
            continue
        tried.append(model)
        try:
            extra = {}
            if model.startswith("ollama/"):
                extra["api_base"] = os.getenv("OLLAMA_BASE_URL")
            t0 = time.time()
            resp = litellm.completion(model=model, messages=messages, **kwargs, **extra)
            text = (resp.choices[0].message.content or "").strip()
            if text:
                _log_usage(model, tier, resp, (time.time() - t0) * 1000)
                return text, model
            errors.append(f"{model}: empty response")
        except Exception as e:  # noqa: BLE001 — fall through to next provider
            errors.append(f"{model}: {str(e)[:120]}")
            continue

    if not tried:
        raise RouterError(
            f"no provider configured for tier={tier!r}. Set one of: GROQ_API_KEY, "
            "GEMINI_API_KEY, OPENROUTER_API_KEY, DEEPSEEK_API_KEY, CEREBRAS_API_KEY, "
            "or run Ollama."
        )
    raise RouterError(f"all providers failed for tier={tier!r}: " + " | ".join(errors))


def complete_json(prompt: str, **kw) -> tuple[dict, str]:
    """complete() but parse the result as JSON (defensive extraction)."""
    kw["want_json"] = True
    text, model = complete(prompt, **kw)
    try:
        return json.loads(text), model
    except ValueError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0)), model
        raise RouterError(f"{model} did not return JSON: {text[:200]}")


# --------------------------------------------------------------------------- #
# Usage / cost observability (inspired by managed gateways like openmodel.ai —
# but free + local: every served call is logged so we can SEE where tokens and
# money go). Never breaks a call.
# --------------------------------------------------------------------------- #

def _log_usage(model: str, tier: str, resp, latency_ms: float) -> None:
    try:
        usage = getattr(resp, "usage", None)
        pt = int(getattr(usage, "prompt_tokens", 0) or 0)
        ct = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = 0.0
        try:
            import litellm
            cost = float(litellm.completion_cost(completion_response=resp) or 0.0)
        except Exception:
            pass
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": model, "tier": tier,
            "prompt_tokens": pt, "completion_tokens": ct,
            "cost_usd": round(cost, 6), "latency_ms": round(latency_ms),
        }
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass  # observability must never break a completion


def _print_usage() -> int:
    if not USAGE_LOG.exists():
        print("no usage logged yet.")
        return 0
    agg: dict[str, dict] = {}
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        a = agg.setdefault(r["model"], {"n": 0, "pt": 0, "ct": 0, "cost": 0.0, "lat": 0})
        a["n"] += 1
        a["pt"] += r.get("prompt_tokens", 0)
        a["ct"] += r.get("completion_tokens", 0)
        a["cost"] += r.get("cost_usd", 0.0)
        a["lat"] += r.get("latency_ms", 0)
    print(f"{'model':40} {'calls':>6} {'in_tok':>9} {'out_tok':>9} {'cost$':>9} {'avg_ms':>7}")
    for m, a in sorted(agg.items(), key=lambda x: -x[1]["n"]):
        print(f"{m:40} {a['n']:>6} {a['pt']:>9} {a['ct']:>9} {a['cost']:>9.4f} {a['lat'] // max(a['n'], 1):>7}")
    total_cost = sum(a["cost"] for a in agg.values())
    total_calls = sum(a["n"] for a in agg.values())
    print(f"\ntotal est. cost: ${total_cost:.4f} over {total_calls} calls "
          f"(free providers report $0).")
    return 0


def _main(argv: list[str]) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    _load_env()

    if argv and argv[0] == "--usage":
        return _print_usage()

    if not argv or argv[0] == "--probe":
        for tier in ("cheap", "smart"):
            print(f"[{tier}] configured: {', '.join(available(tier)) or '(none)'}")
        if available("cheap"):
            try:
                text, model = complete("Reply with the single word: ok", tier="cheap", max_tokens=5)
                print(f"\nping → {model}: {text!r}")
            except RouterError as e:
                print(f"\nping failed: {e}")
        return 0

    tier = "smart" if "--smart" in argv else "cheap"
    want_json = "--json" in argv
    prompt = " ".join(a for a in argv if not a.startswith("--"))
    try:
        if want_json:
            data, model = complete_json(prompt, tier=tier)
            print(f"[{model}]\n{json.dumps(data, indent=2, ensure_ascii=False)}")
        else:
            text, model = complete(prompt, tier=tier)
            print(f"[{model}]\n{text}")
    except RouterError as e:
        print(f"router: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
