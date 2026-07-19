"""Studio Crew — CrewAI hierarchical orchestration over the live studios (PRODUCTION).

Runs under the ISOLATED .venv-crew so CrewAI's ~900 MB of deps NEVER touch the main
.venv. The live executor invokes this as a subprocess (like the swipe / council
rails) and captures the deliverable from stdout — so the production runtime never
imports crewai. This is the "reinforce, don't fragment" boundary: our studios +
hard shell stay the moat; CrewAI is only the manager/delegation engine on top.

Safety, layered (a slow/dead studio must never spiral a run — the 10.5-min failure
mode we measured on 2026-07-18):
  * gateway.studio_api hard shell — 127.0.0.1 only, GET + safe POST, risky blocked,
    responses scrubbed, short per-call timeout (STUDIO_API_TIMEOUT, default 20s).
  * per-run CircuitBreaker — a studio that fails/times out is skipped for the rest
    of the run (no repeated waits on a known-bad studio).
  * Deadline — a wall-clock budget; once passed, studio calls short-circuit so the
    crew winds down instead of hanging.
  * The executor wraps this whole subprocess in a hard timeout as the final backstop.

Free-first: runs on Gemini 2.5 Flash (GEMINI_API_KEY). Goal on argv; the finished
deliverable is printed between the BEGIN/END markers so the executor can extract it
from CrewAI's noisier stdout.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/opt/marketing-hub-os")

from gateway._bootstrap import load_env  # noqa: E402

load_env()

from crewai import Agent, Task, Crew, Process
from crewai.tools import tool

from gateway import studio_api

RESULT_BEGIN = "<<<CREW_RESULT_BEGIN>>>"
RESULT_END = "<<<CREW_RESULT_END>>>"

if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

from crewai import BaseLLM

_FALLBACK_MODEL = "gemini/gemini-2.5-flash"  # QUALITY fallback (operator: quality > free)
# Per-run brain state/telemetry. NOT on the LLM class: BaseLLM is pydantic, and
# class-level attrs there turn into FieldInfo/PrivateAttr descriptors (always
# truthy, not incrementable) — reading/mutating them on the class silently breaks.
_BRAIN_STATE = {"claude_down": False, "claude": 0, "fallback": 0, "claude_fails": 0}


class ClaudeSubscriptionLLM(BaseLLM):
    """The crew workers think on the operator Claude SUBSCRIPTION (2026-07-19
    directive: the subscription must carry the load, not a daily-billed API).
    Each call goes through gateway.claude_bridge (stdlib-only, importable from
    this isolated venv): strongest model first, laddering down + 3-account
    rotation. Only when EVERY Claude rung is capped does it fall to the QUALITY
    fallback (Gemini flash via litellm) — order unchanged, Groq stays the
    last-resort floor inside the wider router, never promoted here."""


    @staticmethod
    def _flatten(messages) -> tuple[str | None, str]:
        if isinstance(messages, str):
            return None, messages
        sys_parts, convo = [], []
        for m in messages or []:
            role = (m.get("role") or "user") if isinstance(m, dict) else "user"
            content = m.get("content", "") if isinstance(m, dict) else str(m)
            if isinstance(content, list):  # multi-part content blocks
                content = "\n".join(
                    c.get("text", "") if isinstance(c, dict) else str(c) for c in content
                )
            if role == "system":
                sys_parts.append(str(content))
            else:
                convo.append(f"{role.upper()}: {content}")
        return ("\n\n".join(sys_parts) or None), "\n\n".join(convo)

    def call(self, messages, tools=None, callbacks=None, available_functions=None,
             from_task=None, from_agent=None, response_model=None):
        system, prompt = self._flatten(messages)
        if not _BRAIN_STATE["claude_down"]:
            try:
                from gateway import claude_bridge
                if claude_bridge.is_available():
                    text, _model = claude_bridge.complete(
                        prompt, system=system,
                        timeout=int(os.getenv("CREW_CLAUDE_TIMEOUT", "120")))
                    if text and text.strip():
                        _BRAIN_STATE["claude"] += 1
                        _BRAIN_STATE["claude_fails"] = 0
                        return text.strip()
            except Exception as exc:
                low = str(exc).lower()
                capped = any(c in low for c in
                             ("cap", "limit", "quota", "429", "credit", "exceeded"))
                _BRAIN_STATE["claude_fails"] += 1
                # Latch OFF Claude only on a genuine cap, or after 2 repeated
                # slow/failed calls — one slow step must not abandon the
                # subscription for the whole run.
                if capped or _BRAIN_STATE["claude_fails"] >= 2:
                    _BRAIN_STATE["claude_down"] = True
        import litellm
        litellm.drop_params = True
        litellm.suppress_debug_info = True
        msgs = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
        resp = litellm.completion(model=_FALLBACK_MODEL, messages=msgs, temperature=0.3)
        _BRAIN_STATE["fallback"] += 1
        return (resp.choices[0].message.content or "").strip()


def _make_llm():
    """CREW_MODEL env pins an explicit litellm model (testing/override); the
    default is the Claude subscription."""
    pin = os.getenv("CREW_MODEL", "").strip()
    if pin:
        return pin
    return ClaudeSubscriptionLLM(model="claude-code/subscription")


_LLM = _make_llm()


# --- operational safety: circuit-breaker + deadline ----------------------
class _Deadline:
    def __init__(self, seconds: float):
        self.until = time.monotonic() + seconds

    def passed(self) -> bool:
        return time.monotonic() >= self.until


class _Breaker:
    def __init__(self, max_fails: int = 1):
        self.max_fails = max_fails
        self._fails: dict[str, int] = {}

    def is_open(self, studio: str) -> bool:
        return self._fails.get(studio, 0) >= self.max_fails

    def record(self, studio: str, ok: bool) -> None:
        self._fails[studio] = 0 if ok else self._fails.get(studio, 0) + 1


_DEADLINE = _Deadline(float(os.getenv("CREW_DEADLINE_SECONDS", "300")))
_BREAKER = _Breaker(max_fails=1)


def _safe_studio_call(studio: str, path: str) -> str:
    if _DEADLINE.passed():
        return f"[deadline exceeded] skipped {studio}{path} — task time budget spent"
    if _BREAKER.is_open(studio):
        return f"[circuit open] {studio} skipped — it already failed/timed out this run"
    res = studio_api.call_studio_api(studio, path, method="GET")
    _BREAKER.record(studio, ok=res.startswith("HTTP 2"))
    return res


# --- studio tools (generic; studios discovered, not hardcoded) -----------
@tool("list_studios")
def list_studios() -> str:
    """List every studio the crew can call: key, purpose, port. Call this first to
    discover capabilities, then use call_studio with a studio key."""
    return studio_api.list_studios()


@tool("call_studio")
def call_studio(studio: str, path: str) -> str:
    """Call a studio's live local API (GET, 127.0.0.1 only) through the safety shell.
    studio = a key from list_studios (e.g. 'ads','cx','seo','price','influencer',
    'atelier','ga4'). path = endpoint, e.g. '/api/report' or '/openapi.json' to
    discover a studio's endpoints. Pass query params inline: '/api/hunt?q=...'. If a
    call returns a 'missing field'/422 error, read it and retry with the needed
    param. A studio that fails once is skipped for the rest of the run."""
    return _safe_studio_call(studio, path)


def build_crew(goal: str) -> Crew:
    data = Agent(
        role="Studio Data Mütəxəssisi",
        goal="Tapşırığa uyğun studioları list_studios ilə tap, call_studio ilə CANLI "
             "data çək (lazım olsa /openapi.json ilə endpointləri kəşf et, xəta olsa "
             "parametr əlavə edib yenidən cəhd et). Yalnız 200 cavabdan gələn rəqəmləri işlət.",
        backstory="Sən canlı studio API-larından etibarlı data çıxaran data mütəxəssisisən.",
        tools=[list_studios, call_studio],
        llm=_LLM,
        allow_delegation=False,
        verbose=False,
    )
    strategist = Agent(
        role="Marketinq Strateqi",
        goal="Data mütəxəssisinin çıxardığı CANLI dataya söykənərək konkret, əsaslı "
             "tövsiyə/məzmun hazırla. Uydurma rəqəm işlətmə; data yoxdursa boşluğu dürüst qeyd et.",
        backstory="Sən datadan strategiya və məzmun çıxaran təcrübəli strateqsən.",
        tools=[list_studios, call_studio],
        llm=_LLM,
        allow_delegation=False,
        verbose=False,
    )
    task = Task(
        description=(
            f"{goal}\n\nHər iddia canlı studio datasına söykənsin. Data yoxdursa, "
            "dürüstcə boşluğu qeyd et, uydurma."
        ),
        expected_output="Azərbaycan dilində vahid, studio datasına əsaslı deliverable.",
    )
    manager = Agent(
        role="Kampaniya Meneceri",
        goal="Komandanı idarə et, hər mütəxəssisi öz işinə yönəlt, nəticələri "
             "birləşdirib yekun deliverable ver.",
        backstory="Sən mürəkkəb marketinq işlərini idarə edən təcrübəli menecersən.",
        llm=_LLM,
        allow_delegation=True,
        verbose=False,
    )
    return Crew(
        agents=[data, strategist],
        tasks=[task],
        manager_agent=manager,
        process=Process.hierarchical,
        verbose=False,
    )


def run(goal: str) -> str:
    try:
        result = build_crew(goal).kickoff()
        stats = "[workers: claude={} fallback={}]".format(
            _BRAIN_STATE["claude"], _BRAIN_STATE["fallback"])
        return f"{str(result).strip()}\n\n{stats}"
    except Exception as exc:  # never crash the caller; report honestly
        return f"[crew error] {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    goal = " ".join(sys.argv[1:]).strip()
    out = run(goal) if goal else "[crew error] no goal provided"
    print(RESULT_BEGIN)
    print(out)
    print(RESULT_END)
