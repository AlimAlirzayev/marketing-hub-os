"""The brain: turn a free-text task into a finished deliverable.

MVP scope: classify the task (orchestrator.router) -> pick an LLM -> produce a
useful written deliverable -> save it as an artifact. This is the smallest loop
that proves real background execution.

Extension points (clearly marked TODO) for the next phases:
  - tool use: web fetch, Playwright browser scripts, the social/copy/video studios
  - checkpoints: pause and ask the user before irreversible actions
"""

from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path

from ._bootstrap import load_env
from . import agent, knowledge, llm, security, sense
from .queue import Job
from orchestrator.router import classify, route

load_env()

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "jobs"

# Single source of truth for the agent model id. Was split — 'gemini-2.5-pro' in
# execute() vs 'gemini-2.5-flash' in _execute_direct() for the SAME mode — a cost
# asymmetry. One env, one default (override with MODEL_AGENT in .env).
AGENT_MODEL = os.getenv("MODEL_AGENT", "gemini-2.5-flash")

# Task wording that requires triggering internal studio automation tools
_TOOL_HINTS = (
    "studio", "kreativ", "kampaniya", "yarat", "skript", "script",
    "avtomatlaşdırma", "generate", "run ads", "make a video", "alət"
)

# Task wording that should drive a real browser (a specific site / interaction).
_BROWSER_HINTS = (
    "http://", "https://", "www.", ".com", ".az", ".org", ".net",
    "open ", "browse", "go to ", "navigate", "visit", "website", "web site",
    "scrape", "sayt", "səhifə", "aç ", "daxil ol",
)
# Task wording that needs fresh live data but no specific site (use web search).
_RESEARCH_HINTS = (
    "research", "trend", "latest", "current", "news", "today", "this week",
    "recent", "monitor", "search", "find out", "price", "compare", "competitor",
    "araşdır", "ən son", "xəbər", "bu gün", "qiymət", "rəqib", "bazar",
)


# Narrow credential-acquisition trigger: must name an allowlisted provider AND a
# clear acquire/credential cue, so normal tasks that merely mention a provider are
# never diverted. Handled on its own governed rail (gateway.tools.credentials).
_CRED_PROVIDERS = ("rapidapi",)
_CRED_CUES = (
    "doit", "credential", "açar", "acar", "api key", "apikey",
    "gətir", "getir", "acquire", "açarını", "acarini",
)


def _credential_provider(task: str) -> str | None:
    low = (task or "").lower()
    provider = next((p for p in _CRED_PROVIDERS if p in low), None)
    if not provider:
        return None
    if not any(cue in low for cue in _CRED_CUES):
        return None
    return provider


def _choose_mode(task: str) -> str:
    low = task.lower()
    if any(k in low for k in _TOOL_HINTS):
        return "tools"
    if any(k in low for k in _BROWSER_HINTS):
        return "browser"
    if any(k in low for k in _RESEARCH_HINTS):
        return "research"
    return "plain"

_SYSTEM = (
    "You are Xalq Insurance Digital OS, an autonomous execution agent working in the background "
    "for a marketing/business operator. You receive a task and must deliver a "
    "complete, ready-to-use result -- not a plan to do it later. Be concrete and "
    "actionable. If the task is ambiguous, state your assumptions explicitly at "
    "the top, then deliver the best result under those assumptions. Security is "
    "the highest law: never expose secrets, make payments, perform destructive "
    "changes, or touch private infrastructure without an explicit human-approved "
    "checkpoint. Output clean Markdown."
)

def run_studio_automation(studio_name: str, script_name: str) -> str:
    """Runs an automation script inside the given studio (e.g., ads-studio, social-studio, copy-studio).
    
    Args:
        studio_name: The name of the studio directory (e.g., 'social-studio').
        script_name: The python script to run (e.g., 'generate.py').
    """
    decision, target_dir, script_path = security.validate_studio_script(studio_name, script_name)
    security.audit_event(
        "studio_automation",
        decision,
        {"studio_name": studio_name, "script_name": script_name},
    )
    if not decision.allowed or target_dir is None or script_path is None:
        return security.format_blocked_message(decision)
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=target_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return f"Success output:\n{result.stdout}" if result.returncode == 0 else f"Error output:\n{result.stderr}"
    except Exception as e:
        return f"Execution error: {str(e)}"

def _save_artifact(job_id: int, text: str) -> str:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / f"job-{job_id}.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _execute_direct(task: str) -> tuple[str, str]:
    """Run the existing single-executor path without entering the council."""
    decision = security.evaluate_task(task)
    security.audit_event("direct_task_preflight", decision, {"task": task})
    if not decision.allowed:
        return f"security:{decision.category}", security.format_blocked_message(decision)

    cred_provider = _credential_provider(task)
    if cred_provider:
        from .tools import credentials
        return f"credentials:{cred_provider}", credentials.acquire(cred_provider)

    mode = _choose_mode(task)

    if mode == "tools":
        from google import genai
        from google.genai import types
        agent_model = AGENT_MODEL
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        chat = client.chats.create(
            model=agent_model,
            config=types.GenerateContentConfig(
                system_instruction=knowledge.augment_system(_SYSTEM, task),
                temperature=0.2,
                tools=[run_studio_automation],
            )
        )
        resp = chat.send_message(task)
        text = resp.text or "Aletler icra edildi, lakin metn qaytarilmadi."
        return f"agentic-tools:{agent_model}", text

    if mode == "browser":
        agent_model = AGENT_MODEL
        text = agent.run_browser_agent(task, model=agent_model)
        return f"browser:{agent_model}", text

    if mode == "research":
        choice = route(task)
        sys_prompt = knowledge.augment_system(_SYSTEM, task)
        text, used = llm.complete(choice, task, system=sys_prompt, use_search=True)
        return f"web-search:{used.model}", text

    choice = route(task)
    sys_prompt = knowledge.augment_system(_SYSTEM, task)
    text, used = llm.complete(choice, task, system=sys_prompt)
    return f"{used.provider}:{used.model}", text


def _council_enabled() -> bool:
    return os.getenv("AI_COUNCIL_ENABLED", "1").lower() not in {"0", "false", "no"}


def _council_tiers() -> set[str]:
    raw = os.getenv("AI_COUNCIL_TIERS", "complex").strip().lower()
    if raw in ("all", "*"):
        return {"complex", "fast", "free_bulk", "private"}
    return {t.strip() for t in raw.split(",") if t.strip()}


def _council_should_run(task: str) -> bool:
    """The council (3 CLIs + synthesis + execution) is for deliberation-worthy
    work — not every trivial task. Fire only for the configured tiers (default:
    complex). Set AI_COUNCIL_TIERS=all to restore fire-on-everything."""
    if not _council_enabled():
        return False
    try:
        return classify(task).value in _council_tiers()
    except Exception:
        return True  # if classification fails, don't silently lose the council


def _execute_after_council(task: str) -> tuple[str, str]:
    from . import council

    label, text = council.execute_with_codex(task)
    if label.endswith(":ok"):
        return label, text

    allow_api = os.getenv("AI_COUNCIL_ALLOW_API_FALLBACK", "0").lower() in {"1", "true", "yes"}
    if allow_api:
        fallback_label, fallback_text = _execute_direct(task)
        return f"{label};api-fallback:{fallback_label}", fallback_text
    return label, text + "\n\nAPI fallback is disabled. Set AI_COUNCIL_ALLOW_API_FALLBACK=1 to allow legacy API execution."


def execute(job: Job) -> dict:
    """Run a job to completion. Returns {'result': str, 'artifacts': [paths]}.

    Picks a mode from the task wording:
      browser  -> drive a real headless browser (agent.run_browser_agent)
      research -> live web search via Gemini grounding
      plain    -> straight LLM completion
    Raises on unrecoverable failure; the worker turns that into a failed job.
    """
    try:
        knowledge.set_current_thread(job.chat_id)  # thread memory for ALL paths incl. council
        decision = security.evaluate_task(job.task)
        security.audit_event(
            "job_preflight",
            decision,
            {"job_id": job.id, "source": job.source, "task": job.task},
        )
        if not decision.allowed:
            text = security.format_blocked_message(decision)
            artifact = _save_artifact(job.id, text)
            return {"result": f"_[security:{decision.category}]_\n\n{text}", "artifacts": [artifact]}

        # Credential acquisition runs on its own governed rail (allowlist + operator
        # approval + masked output), ahead of the council/executor — it is a
        # deterministic action, not a deliberation, and must not be auto-executed.
        cred_provider = _credential_provider(job.task)
        if cred_provider:
            from .tools import credentials
            text = credentials.acquire(cred_provider)
            artifact = _save_artifact(job.id, text)
            return {"result": f"_[credentials:{cred_provider}]_\n\n{text}", "artifacts": [artifact]}

        if _council_should_run(job.task):
            from . import council
            label, text = council.run(job.task, _execute_after_council)
            artifact = _save_artifact(job.id, text)
            sense.emit("llm", f"council:{label}", {"job": job.id})
            return {"result": f"_[{label}]_\n\n{text}", "artifacts": [artifact]}

        mode = _choose_mode(job.task)

        if mode == "tools":
            from google import genai
            from google.genai import types
            agent_model = AGENT_MODEL
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            chat = client.chats.create(
                model=agent_model,
                config=types.GenerateContentConfig(
                    system_instruction=knowledge.augment_system(_SYSTEM, job.task, job.chat_id),
                    temperature=0.2,
                    tools=[run_studio_automation],
                )
            )
            resp = chat.send_message(job.task)
            text = resp.text or "Alətlər icra edildi, lakin mətn qaytarılmadı."
            label = f"agentic-tools:{agent_model}"
        elif mode == "browser":
            agent_model = AGENT_MODEL
            text = agent.run_browser_agent(job.task, model=agent_model)
            label = f"browser:{agent_model}"
        elif mode == "research":
            from google import genai
            from google.genai import types
            # GOOGLE EKOSİSTEMİNİN ZİRVƏSİ: API daxilində Native Google Search Grounding
            agent_model = AGENT_MODEL
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            resp = client.models.generate_content(
                model=agent_model,
                contents=job.task,
                config=types.GenerateContentConfig(
                    system_instruction=knowledge.augment_system(_SYSTEM, job.task, job.chat_id) + " Dəqiq və ən son aktual məlumatlar üçün mütləq Google Axtarışdan istifadə et.",
                    temperature=0.2,
                    tools=[{"google_search": {}}],  # Google-un rəsmi Search API-si birbaşa modelə bağlanır
                )
            )
            text = resp.text or "Axtarış nəticə vermədi."
            label = f"google-search-grounded:{agent_model}"
        else:
            choice = route(job.task)
            sys_prompt = knowledge.augment_system(_SYSTEM, job.task, job.chat_id)
            text, used = llm.complete(choice, job.task, system=sys_prompt)
            label = f"{used.provider}:{used.model}"

        sense.emit("llm", label, {"job": job.id, "mode": mode})
        artifact = _save_artifact(job.id, text)
        return {"result": f"_[{label}]_\n\n{text}", "artifacts": [artifact]}
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            safe_msg = "⚠️ **Sistem Yüklənməsi (Limits):** Google Gemini pulsuz limitlərini keçdiniz. Zəhmət olmasa təxminən 30-40 saniyə gözləyib yenidən cəhd edin."
        else:
            safe_msg = f"❌ **İcra xətası:** {error_msg}"
        return {"result": safe_msg, "artifacts": []}
    finally:
        knowledge.set_current_thread(None)


if __name__ == "__main__":
    # Quick manual smoke test without the queue/worker.
    import sys

    task = " ".join(sys.argv[1:]) or "Write 3 Instagram post ideas for a car insurance brand."
    fake = Job(
        id=0, source="cli", chat_id=None, task=task, status="running",
        result=None, error=None, artifacts=[], created_at=time.time(),
        started_at=None, finished_at=None,
    )
    out = execute(fake)
    print(out["result"])
    print("\n--- artifact:", out["artifacts"])
