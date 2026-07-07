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
import re
import sys
import time
import shutil
import subprocess
from pathlib import Path

from ._bootstrap import load_env
from . import agent, knowledge, llm, security, sense
from .queue import Job
from .studio_api import call_studio_api, list_studios, generate_media
from orchestrator.router import classify, route

load_env()

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "jobs"
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent / "workspace"
_WS_RE = re.compile(r"workspace:\s*([^\s)]+)")

# Single source of truth for the agent model id. Was split — 'gemini-2.5-pro' in
# execute() vs 'gemini-2.5-flash' in _execute_direct() for the SAME mode — a cost
# asymmetry. One env, one default (override with MODEL_AGENT in .env).
AGENT_MODEL = os.getenv("MODEL_AGENT", "gemini-2.5-flash")

# Task wording that requires triggering internal studio automation tools
_TOOL_HINTS = (
    "studio", "kreativ", "kampaniya", "yarat", "skript", "script",
    "avtomatlaşdırma", "generate", "run ads", "make a video", "alət",
    # build/coding intent -> the workspace agent (real hands). Multi-word phrases
    # stay precise so they don't over-trigger on ordinary words.
    "sayt qur", "saytı qur", "sayt hazırla", "veb sayt", "web sayt", "landing",
    "html", "css", "kod yaz", "write code", "build a", "scaffold", "web app",
    "layihə qur", "app qur", "tətbiq qur", "deploy", "publish", "paylaş",
    "məqalə yaz", "article", "video düzəlt", "video hazırla", "[approved-action]",
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


# A system self-report request (the daily "Günaydın hesabatı", an advisor digest,
# a live-status ask). Answered deterministically from the nervous system
# (sense.pulse) + the advisor's grounded findings — no council/essay generation —
# so the scheduled morning job delivers the REAL proactive digest, not a generic
# LLM write-up. Cues are specific enough that ordinary tasks aren't diverted.
_BRIEFING_CUES = (
    "günaydın hesabat", "gunaydin hesabat", "səhər hesabat", "seher hesabat",
    "morning report", "morning briefing", "briefing", "advisor", "məsləhətçi",
    "meslehetci", "sistem hesabat", "system status", "status report",
    "self-report", "pulse", "nəbz", "nebz",
)


def _is_briefing(task: str) -> bool:
    low = (task or "").strip().lower()
    return any(cue in low for cue in _BRIEFING_CUES)


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

# Appended to _SYSTEM only in tools mode, where the agent has real hands
# (workspace_agent: run_command / write_file / read_file / request_owner_approval).
_WORKSPACE_ADDENDUM = (
    "\n\nYOU HAVE HANDS. Beyond the studio tools you can build real deliverables "
    "in a private sandbox workspace using run_command (a shell), write_file and "
    "read_file. Work like an engineer:\n"
    "- Do everything INSIDE the workspace; the rest of the system is read-only, "
    "so build freely without fear.\n"
    "- For ANY website / landing / UI: FIRST author a DESIGN.md design system "
    "(concept + mood, exact HEX palette, type pairing, spacing rhythm, 2-3 "
    "signature motifs, and an explicit ban-list against the generic-AI look — "
    "purple gradients, emoji bullets, glassmorphism, everything-centered), then "
    "build strictly to it. Escape the template look.\n"
    "- Generate images/video/voice with generate_media or the mediagen studio; "
    "write articles/SEO via the seo studio; pull data via call_studio_api.\n"
    "- Actually run the build and check the output before calling it done.\n"
    "- Reversible/build work runs on its own. OUTWARD or irreversible actions "
    "(deploy, publish, post, git push, sending to the internet) will NOT run "
    "automatically: finish the buildable part, then call request_owner_approval "
    "with the exact action so the owner can /approve it.\n"
    "- If the task begins with [approved-action], the owner has ALREADY approved "
    "it — perform exactly that action now with run_command (or publish_site).\n"
    "- To put a finished website online, call publish_site('short-name') — it "
    "goes live at the fleet's public URL. It only works on an approved job, so "
    "build first, then request_owner_approval, then publish_site after /approve.\n"
    "- Finish by summarizing WHAT you built and listing the workspace file paths "
    "you produced, so the owner can review and download them."
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


def _workspace_for(job: Job) -> Path:
    """The sandbox dir for this job. An [approved-action] job reuses the workspace
    named in its task (so the approved step acts on what was already built);
    every other job gets its own job-<id> dir."""
    m = _WS_RE.search(job.task or "")
    if m:
        p = Path(m.group(1)).resolve()
        try:
            p.relative_to(_WORKSPACE_ROOT)
            return p
        except ValueError:
            pass
    return _WORKSPACE_ROOT / f"job-{job.id}"


def _bundle_workspace(job_id: int, ws: Path) -> str | None:
    """Zip the workspace so a built deliverable is downloadable. None if empty."""
    try:
        if not ws.exists() or not any(p.is_file() for p in ws.rglob("*")):
            return None
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = _OUTPUT_DIR / f"job-{job_id}-workspace"
        return shutil.make_archive(str(out), "zip", root_dir=str(ws))
    except Exception:
        return None


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
                tools=[run_studio_automation, call_studio_api, list_studios, generate_media],
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

        # System self-report rail: the proactive digest (live board + advisor's
        # grounded next-steps). Deterministic facts; advisor's optional AI ranking
        # is free-first and degrades to facts-only. This is what the scheduled
        # "Günaydın hesabatı" job delivers to Telegram every morning.
        if _is_briefing(job.task):
            from . import advisor
            board = sense.pulse()
            advice = advisor.brief(use_llm=True)
            text = f"{board}\n\n{advice}"
            artifact = _save_artifact(job.id, text)
            sense.emit("job", f"#{job.id} briefing", {"task": job.task[:80]})
            return {"result": f"_[briefing]_\n\n{text}", "artifacts": [artifact]}

        # The human checkpoint (charter: outward actions never run silently).
        # A publish/send/call/deploy task parks for operator approval; once the
        # operator /approve-s it, the job returns approved=1 and passes through.
        if not job.approved:
            cp = security.evaluate_checkpoint(job.task)
            if not cp.allowed:
                security.audit_event(
                    "job_checkpoint", cp, {"job_id": job.id, "task": job.task}
                )
                sense.emit("job", f"#{job.id} awaiting approval", {"task": job.task[:80]})
                text = (
                    "⏸ **Bu tapşırıq bayıra yönəlik əməl edir** (paylaşım/göndəriş/"
                    "zəng/deploy) və təsdiqini gözləyir.\n\n"
                    f"Tapşırıq: {job.task}\n\n"
                    f"Təsdiq üçün:  /approve {job.id}\n"
                    f"İmtina üçün:  /reject {job.id}"
                )
                return {"result": text, "artifacts": [], "needs_approval": True}

        if _council_should_run(job.task):
            from . import council
            label, text = council.run(job.task, _execute_after_council)
            artifact = _save_artifact(job.id, text)
            sense.emit("llm", f"council:{label}", {"job": job.id})
            return {"result": f"_[{label}]_\n\n{text}", "artifacts": [artifact]}

        mode = _choose_mode(job.task)
        bundle = None  # workspace zip, set in tools mode; delivered as a file

        if mode == "tools":
            from google import genai
            from google.genai import types
            from . import workspace_agent
            agent_model = AGENT_MODEL
            ws = _workspace_for(job)
            workspace_agent.configure(
                job_id=job.id, workspace=ws, chat_id=job.chat_id,
                approved=bool(job.approved),
            )
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            chat = client.chats.create(
                model=agent_model,
                config=types.GenerateContentConfig(
                    system_instruction=knowledge.augment_system(
                        _SYSTEM + _WORKSPACE_ADDENDUM, job.task, job.chat_id),
                    temperature=0.2,
                    tools=[run_studio_automation, call_studio_api, list_studios,
                           generate_media, workspace_agent.run_command,
                           workspace_agent.write_file, workspace_agent.read_file,
                           workspace_agent.request_owner_approval,
                           workspace_agent.publish_site],
                )
            )
            try:
                resp = chat.send_message(job.task)
                text = resp.text or "Alətlər icra edildi, lakin mətn qaytarılmadı."
            except Exception as loop_exc:
                # The agent may have already built real files before a mid-loop
                # failure (e.g. a free-tier quota hit). Never throw that work away.
                built = [str(p.relative_to(ws)) for p in sorted(ws.rglob("*")) if p.is_file()]
                if not built:
                    raise
                text = (
                    "⚠️ İcra tam bitmədi (" + loop_exc.__class__.__name__ +
                    "), amma bu fayllar iş sahəsində hazırlandı:\n- " +
                    "\n- ".join(built)
                )
            bundle = _bundle_workspace(job.id, ws)
            if bundle:
                text += f"\n\n📦 İş sahəsi paketi (yüklə): {bundle}"
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
        return {"result": f"_[{label}]_\n\n{text}",
                "artifacts": [artifact] + ([bundle] if bundle else [])}
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

# Fix PEP563: from __future__ import annotations made these strings -> real types so
# google-genai automatic function-calling can introspect the studio tool.
run_studio_automation.__annotations__ = {"studio_name": str, "script_name": str, "return": str}
