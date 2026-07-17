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
from . import agent, knowledge, llm, mic, security, sense, skills
from .queue import Job
from .studio_api import call_studio_api, list_studios, generate_media
from orchestrator.router import classify, route

load_env()

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "jobs"
_REPLIES_DIR = Path(__file__).resolve().parent.parent / "output" / "replies"
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent / "workspace"
_WS_RE = re.compile(r"workspace:\s*([^\s)]+)")

# Single source of truth for the agent model id. Was split — 'gemini-2.5-pro' in
# execute() vs 'gemini-2.5-flash' in _execute_direct() for the SAME mode — a cost
# asymmetry. One env, one default (override with MODEL_AGENT in .env).
AGENT_MODEL = os.getenv("MODEL_AGENT", "gemini-2.5-flash")

# Task wording that requires triggering internal studio automation tools.
# NOTE: only ACTION cues belong here, never bare topic nouns. "kampaniya" was
# removed 2026-07-17 — it is a topic word that appears in ordinary questions
# ("kampaniyalar necə gedir?") and was wrongly diverting plain chat turns into
# the build lane (observed on job #95). A real "create a campaign" request still
# routes via its action verb ("yarat"/"generate"/"hazırla").
_TOOL_HINTS = (
    "studio", "kreativ", "yarat", "skript", "script",
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


# AI Radar rail-i (gateway/radar.py): həftəlik dərin brif + gündəlik kritik-nəbz.
# Cues dar saxlanılıb ki, içində təsadüfən "radar" keçən adi tapşırıqlar bura
# düşməsin. "nəbz" sözü QƏSDƏN yoxdur — o, briefing rail-inin cue-sudur.
_RADAR_CUES = ("radar həftəlik", "radar heftelik", "ai radar", "/radar")
_RADAR_PULSE_CUES = ("radar gündəlik", "radar gundelik", "radar pulse")


def _is_radar(task: str) -> bool:
    low = (task or "").strip().lower()
    return low == "radar" or any(cue in low for cue in _RADAR_CUES + _RADAR_PULSE_CUES)


def _is_radar_pulse(task: str) -> bool:
    low = (task or "").strip().lower()
    return any(cue in low for cue in _RADAR_PULSE_CUES)


# Swipe rail-i (idea-studio/adsworld.py): Ads of the World swipe faylının
# təzələnməsi. Schedule hər gün çağırır; 7 günlük keş taktı özü qoruyur —
# fayl təzədirsə skript şəbəkəyə çıxmadan dərhal qayıdır. Deterministik
# skriptdir, LLM/council yoluna düşmür. Cues dar saxlanılıb.
_SWIPE_CUES = ("swipe həftəlik", "swipe heftelik", "adsworld", "/swipe")


def _is_swipe(task: str) -> bool:
    low = (task or "").strip().lower()
    return any(cue in low for cue in _SWIPE_CUES)


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

# The conversational persona for the DEFAULT path — the "one microphone" voice.
# The operator wants every channel (this chat, Telegram, Codex, the panel) to
# feel like the same continuous conversation with one sharp teammate, NOT a
# terse council vote. The blackboard history for MIC_THREAD is injected around
# this, so the model already sees what was said on any other microphone.
_CHAT_SYSTEM = (
    "You are Ramin-OS — ONE system the operator reaches through many microphones "
    "(this chat, Telegram, Codex, the control panel). Whoever writes now has taken "
    "the mic; you keep ONE continuous conversation and memory across all of them, "
    "so nothing is fragmented. Reply like a sharp, senior teammate talking directly "
    "to the operator: concrete, honest, and warm — no corporate filler, no restating "
    "the question. Give the real answer or do the real task. If something needs live "
    "data you don't have, or you're unsure, say so plainly instead of inventing. "
    "Use the conversation history and system memory you are given as shared context. "
    "Speak the operator's language — Azerbaijani in chat — but keep code, configs and "
    "identifiers in English. Security is the highest law: never expose secrets, make "
    "payments, or take irreversible/outward actions without an explicit approved "
    "checkpoint."
)

# The chat brain answers from a prompt, NOT from the repo — so without this it has
# no idea what it actually is. Proven 2026-07-15: on the free floor (every Claude
# account capped) it invented a generic SaaS for itself — "user-analytics-dashboard,
# Auth service, GitLab CI/CD, I use GPT-4o" — none of which exist here. Claude
# reading the repo masks this; the floor has no such luxury. These are the durable
# architectural facts, stated once, so ANY brain on the mic answers grounded.
_SELF_FACTS = (
    "\n\nGROUND TRUTH ABOUT YOURSELF. These are the only facts about what you are. "
    "NEVER invent modules, models, integrations or capabilities beyond this list and "
    "the memory you are given — if asked something outside it, say you'd have to check.\n"
    "- Identity: Ramin-OS, a self-hosted zero-budget MARKETING OS (Xalq Sigorta + "
    "freelance work). You are NOT a generic SaaS: there is no Jira, no GitLab, no Auth "
    "service, no user-analytics dashboard. Never claim otherwise.\n"
    "- Brain: the thinking/command brain is CLAUDE (subscription, 3-account rotation). "
    "Free floor when every account is capped: Gemini 2.5 Pro then Groq. You do NOT use "
    "GPT-4 / OpenAI anywhere.\n"
    "- Hearing: Azerbaijani voice notes are transcribed by ElevenLabs Scribe (best AZ), "
    "falling back to Groq Whisper then Gemini (gateway/voice.py).\n"
    "- Speaking: a voice turn is answered with an AZ voice note via free Google TTS.\n"
    "- Free generative media on the Google AI Studio key: Veo 3.1 (video with audio), "
    "Imagen 4 / Gemini image, and Lyria 3 music — lyria-3-pro-preview can SING, "
    "including Azerbaijani vocals (audio-studio).\n"
    "- Work lanes (gateway/executor.py): chat, agentic TOOLS/build (Claude Code + "
    "Codex), live RESEARCH (Gemini google_search grounding), CONTENT (brand-voiced "
    "posts), and a 3-persona FAN-OUT for strategy work.\n"
    "- Interfaces: the Telegram bot, the control panel (port 8890) with a live map, and "
    "Codex — all one shared conversation and memory.\n"
    "- Safety: risky/outward actions (post/send/pay/delete) PARK at a human checkpoint "
    "(/approve N, /reject N).\n"
    "- Marketing data: you have NO live Meta/Google Ads pull unless credentials are "
    "configured — say that plainly rather than inventing numbers.\n"
    "- Machines: twins — a Windows work PC runs the OS locally, this VPS "
    "(/opt/marketing-hub-os) is the always-on brain; they sync over git."
)


_ADS_FACT_OFF = (
    "- Marketing data: you have NO live Meta/Google Ads pull unless credentials are "
    "configured — say that plainly rather than inventing numbers.\n"
)
_ADS_FACT_ON = (
    "- Marketing data: LIVE Meta Ads access IS configured on this machine "
    "(gateway/ads_agent.py) — real campaign/spend reads are available through the ads "
    "tools. Google Ads and TikTok have NO live credentials — say that plainly rather "
    "than inventing numbers.\n"
)


def _self_facts() -> str:
    """The self-card must stay truthful per-machine: the Meta line flips on live creds."""
    import os

    if os.environ.get("META_ACCESS_TOKEN"):
        return _SELF_FACTS.replace(_ADS_FACT_OFF, _ADS_FACT_ON)
    return _SELF_FACTS

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
            encoding="utf-8", errors="replace",
        )
        return f"Success output:\n{result.stdout}" if result.returncode == 0 else f"Error output:\n{result.stderr}"
    except Exception as e:
        return f"Execution error: {str(e)}"


def scrape_url(url: str, render: bool = False) -> str:
    """Pull clean readable text from a web page or PDF — the system's own
    scraping hand, so a task that needs live page content is done in-house
    (requests-first, auto-escalates to a real browser for JS pages), not by
    guessing. Set render=True to force the browser. Returns title + text.

    Args:
        url: The page or .pdf URL to read.
        render: Force the JS browser path (default False = auto).
    """
    from .tools import extract
    r = extract.scrape(url, render=render or None)
    if not r.get("ok"):
        return f"Oxuna bilmədi: {r.get('error', 'naməlum')}"
    head = f"[{r['method']}] {r.get('title', '')}".strip()
    return f"{head}\n\n{r['text']}"


scrape_url.__annotations__ = {"url": str, "render": bool, "return": str}


def _codex_agent(task: str, workspace: Path, *, timeout: int = 600) -> str:
    """Agentic build via the Codex CLI (authed to the operator's ChatGPT), used
    when the Gemini function-calling agent is unavailable — the Gemini API keys
    are dead, so this is what actually gets 'build me X' work done. Codex runs
    with write access to the JOB WORKSPACE only, and returns its final message."""
    exe = shutil.which("codex")
    if not exe:
        raise RuntimeError("codex CLI not available")
    out_file = workspace / ".codex_last.txt"
    prompt = (
        _SYSTEM + _WORKSPACE_ADDENDUM + skills.relevant(task)
        + f"\n\nTASK: {task}\n\nBuild everything inside the current working "
        "directory. When done, summarise what you built in Azerbaijani."
    )
    args = [exe, "exec", "-C", str(workspace), "--sandbox", "workspace-write",
            "--skip-git-repo-check", "--ephemeral",
            "--output-last-message", str(out_file), prompt]
    proc = subprocess.run(args, cwd=str(workspace), capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="replace")
    text = ""
    if out_file.exists():
        text = out_file.read_text(encoding="utf-8", errors="replace").strip()
        try:
            out_file.unlink()
        except Exception:
            pass
    if not text:
        text = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0 and not text:
        raise RuntimeError(f"codex exec failed: {(proc.stderr or '')[:200]}")
    return text or "Codex icra etdi (mətn qaytarılmadı)."


def _save_artifact(job_id: int, text: str, *, reply: bool = False) -> str:
    """Persist a job's text output.

    A DELIVERABLE is something the system produced on request (a report, a
    council result, a briefing) — it belongs in the front office gallery.
    A conversation turn ("salam, necəsən?") or an operational message
    (blocked-by-security, credential status) is NOT a deliverable; filing it as
    one turned the gallery into a wall of chat noise. Those go to output/replies,
    which the panel's gallery does not scan.
    """
    d = _REPLIES_DIR if reply else _OUTPUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"job-{job_id}.md"
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
                tools=[run_studio_automation, call_studio_api, list_studios, generate_media, scrape_url],
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


def _mic_brain() -> str:
    """Which brain answers the conversational path. 'free' (default) = Gemini via
    the router; 'claude' = real headless Claude Code (this chat on any mic, opt-in
    because it spends subscription quota). See gateway/claude_bridge.py."""
    return os.getenv("MIC_BRAIN", "free").strip().lower()


def _converse(task: str, thread: str) -> tuple[str, str]:
    """Answer one conversational turn. Prefers real Claude Code when MIC_BRAIN=
    claude and the CLI is available; otherwise the free brain with shared history.
    Falls back to free if the bridge errors, so a chat never goes unanswered."""
    capped_note = ""  # set only when the premium brain is capped -> honest downgrade
    if _mic_brain() == "claude":
        try:
            from . import claude_bridge
            if claude_bridge.is_available():
                # Context equality: give the premium brain the SAME grounding the
                # free path gets (self-facts + system card + recalled memory), so
                # Telegram "knows the system" as well as this chat does. The bridge
                # resumes its OWN claude session for turn history, so we inject only
                # identity + long-term memory (thread_id=None -> no turn duplication),
                # not the raw blackboard turns. Before this the bridge answered from
                # a 2-line framing alone and drifted off what the system actually is.
                grounding = knowledge.augment_system(_self_facts(), task)
                primed = f"{grounding}\n\n---\nOPERATORUN MESAJI:\n{task}"
                text, meta = claude_bridge.ask(primed, thread=thread)
                return text, f"chat:claude-code (sid={str(meta.get('session_id'))[:8]})"
        except Exception as exc:  # never let the premium brain break delivery
            sense.emit("llm", f"claude bridge fell back to free: {exc}")
            # Honesty over silence: when every Claude account is capped the answer
            # silently dropped to the weaker free floor and the operator could not
            # tell why the bot "got dumber". Surface it — but only for a real cap,
            # not a transient blip.
            low = str(exc).lower()
            if any(c in low for c in ("cap", "limit", "quota", "429",
                                       "credit", "session limit", "exceeded")):
                capped_note = ("⚠️ Claude hesabları müvəqqəti limitdədir — bu cavab "
                               "pulsuz beyindədir, ona görə daha səthi ola bilər.\n\n")
    # The one-microphone conversation is where quality matters most, so it runs
    # on the SMART cascade (best free model first, Groq floor) rather than the
    # cheap default — a real step up for nuanced Azerbaijani. We force it through
    # llm.complete (the single model seam) with a smart-tier choice, so the
    # router picks the smart cascade while the call site stays mockable/testable.
    from orchestrator.router import ModelChoice
    choice = ModelChoice(provider="gemini", model="gemini-2.5-pro", reason="chat-smart")
    sys_prompt = knowledge.augment_system(_CHAT_SYSTEM + _self_facts(), task, thread)
    text, used = llm.complete(choice, task, system=sys_prompt)
    return capped_note + text, f"chat:{used.provider}:{used.model}"


# --- specialist fan-out --------------------------------------------------
# The one adoptable idea from the 2026-07-10 multi-agent reel research (job 40):
# a strategy-shaped deliverable gets MORE from three cheap specialist passes run
# in PARALLEL — each returning a strict-JSON perspective — merged by one bundler
# into a single document, than from one generalist pass. Scope is deliberately
# narrow: it only upgrades the PLAIN path; chat turns and tools/browser/research
# routing are untouched, and any failure falls back to _converse.

_FANOUT_CUES = (
    "plan", "strategiya", "strateji", "strategy", "təklif", "teklif",
    "proposal", "brief", "konsepsiya", "concept", "positioning",
    "mövqeləndirmə", "ideya ver", "ideyalar",
)
_FANOUT_MIN_WORDS = 5  # a bare "planın nədir?" stays conversational

_SPECIALISTS = (
    ("marketing",
     "You are a senior marketing strategist for {brand}. Judge the task purely "
     "from the marketing angle: audience, channels, hooks, message, and "
     "budget-free growth tactics for the Azerbaijani market."),
    ("product",
     "You are the product/domain specialist for {brand}. Judge the task from "
     "the offer side: what we actually sell, customer objections, trust and "
     "compliance constraints, concrete offer improvements."),
    ("analyst",
     "You are a pragmatic business analyst for {brand}. Judge the task from "
     "the execution side: priorities, measurable KPIs, risks, and what to do "
     "first with near-zero budget."),
)

_SPECIALIST_PROMPT = (
    "TASK: {task}\n\n"
    "Answer ONLY from your specialist angle, in Azerbaijani. Return STRICT "
    'JSON: {{"key_points": [...], "recommendations": [...], "risks": [...]}} '
    "— 3-5 short, concrete items per list. No prose outside the JSON."
)


def _wants_fanout(task: str) -> bool:
    low = (task or "").lower()
    if len(low.split()) < _FANOUT_MIN_WORDS:
        return False
    return any(cue in low for cue in _FANOUT_CUES)


def _fanout_specialist(role: str, persona: str, task: str) -> dict:
    """One branch: persona + task -> schema-validated dict (the LLM seam)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from llm_router import complete_json
    from brand import BRAND
    data, model = complete_json(
        _SPECIALIST_PROMPT.format(task=task),
        system=persona.format(brand=BRAND.name),
        tier="cheap",
        temperature=0.5,
    )
    out = {"role": role, "model": model}
    for key in ("key_points", "recommendations", "risks"):
        vals = data.get(key) or []
        out[key] = [str(v).strip() for v in vals if str(v).strip()][:5]
    return out


def _fanout_deliver(task: str, thread: str) -> tuple[str, str]:
    """Fan the task out to the specialists in parallel, bundle into ONE
    deliverable. Partial branch failures are tolerated; raises only when every
    branch fails (the caller then falls back to _converse)."""
    import json as _json
    from concurrent.futures import ThreadPoolExecutor

    branches, misses = [], []
    with ThreadPoolExecutor(max_workers=len(_SPECIALISTS)) as pool:
        futures = {pool.submit(_fanout_specialist, role, persona, task): role
                   for role, persona in _SPECIALISTS}
        for fut, role in futures.items():
            try:
                branches.append(fut.result(timeout=120))
            except Exception as exc:
                misses.append(role)
                sense.emit("llm", f"fanout branch {role} failed: {exc}")
    if not branches:
        raise RuntimeError("all fan-out branches failed")

    digest = _json.dumps(
        [{k: b[k] for k in ("role", "key_points", "recommendations", "risks")}
         for b in branches],
        ensure_ascii=False, indent=1)
    bundle_prompt = (
        f"TASK: {task}\n\nSPECIALIST BRANCHES (JSON):\n{digest}\n\n"
        "Merge these perspectives into ONE finished deliverable in Azerbaijani "
        "Markdown: a short framing, the unified plan in clear sections, then "
        "'Risklər' and a prioritized 'İlk addımlar' checklist. Resolve "
        "conflicts between branches yourself; never mention the specialists "
        "or this process."
    )
    choice = route(task)
    sys_prompt = knowledge.augment_system(_SYSTEM, task, thread)
    text, used = llm.complete(choice, bundle_prompt, system=sys_prompt)
    label = f"fanout:{len(branches)}x->{used.model}"
    if misses:
        label += f" (down: {','.join(misses)})"
    return text, label


# --- structured content path ----------------------------------------------
# Adoptable idea #2 from the job-40 reel research: a social-post ask should
# yield a SCHEMA, not prose. The schema's headline/subhead/body line-lists are
# shaped to feed social-studio/compose_for_brief.py mechanically, so a text
# deliverable can later become a rendered brand post without re-prompting.
# Same narrow scope as fan-out: only upgrades the PLAIN path ("xəbər..." asks
# still go to research, "kampaniya/yarat..." still go to tools), and any
# failure falls back to _converse.

_CONTENT_CUES = (
    "post", "postu", "postuna", "caption", "linkedin", "instagram",
    "facebook", "sosial media", "social media", "reklam mətni", "reklam metni",
)
_CONTENT_MIN_WORDS = 3

_CONTENT_SCHEMA_PROMPT = (
    "TASK: {task}\n\n"
    "Produce ONE ready-to-publish social post in Azerbaijani for this task. "
    "Return STRICT JSON only:\n"
    '{{"platform": "linkedin|instagram|facebook|story",\n'
    '  "top_tag": "2-4 word kicker",\n'
    '  "headline": ["1-2 short lines"],\n'
    '  "subhead": ["0-2 short lines"],\n'
    '  "body": ["2-5 caption lines/paragraphs"],\n'
    '  "hashtags": ["3-7 tags without #"],\n'
    '  "cta": "one action line",\n'
    '  "image_prompt": "English photographic background prompt matching the '
    'brand photo style; no logos, no text in image"}}\n'
    "No prose outside the JSON."
)

_brand_voice_cache: str | None = None


def _brand_voice() -> str:
    """Condensed brand voice for the content system prompt — the brand_kit's
    brand.md is the single source of truth, so posts stay brand-locked even on
    the free-model path. Missing kit (global brand) degrades gracefully."""
    global _brand_voice_cache
    if _brand_voice_cache is None:
        text = ""
        try:
            from brand import BRAND
            kit = Path(__file__).resolve().parent.parent / BRAND.brand_kit / "brand.md"
            if kit.exists():
                text = kit.read_text(encoding="utf-8")[:1800]
        except Exception:
            text = ""
        _brand_voice_cache = text
    return _brand_voice_cache


def _wants_content(task: str) -> bool:
    low = (task or "").lower()
    if len(low.split()) < _CONTENT_MIN_WORDS:
        return False
    return any(cue in low for cue in _CONTENT_CUES)


def _content_generate(task: str) -> tuple[dict, str]:
    """The LLM seam: task -> raw schema dict + model id (stubbed in tests)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from llm_router import complete_json
    from brand import BRAND
    system = (
        f"You are the social content studio of {BRAND.name}. Write in natural, "
        "warm, trust-led Azerbaijani — no corporate filler, no emoji spam. "
        "Follow the brand voice below strictly.\n\n" + _brand_voice()
    )
    return complete_json(
        _CONTENT_SCHEMA_PROMPT.format(task=task),
        system=system, tier="cheap", temperature=0.6,
    )


def _as_lines(val) -> list[str]:
    if isinstance(val, str):
        val = [val]
    return [str(v).strip() for v in (val or []) if str(v).strip()]


def _render_post(data: dict) -> str:
    """Human preview of the structured post for chat delivery."""
    platform = str(data.get("platform") or "post").strip()
    parts = [f"📱 **{platform.capitalize()} postu**"]
    if data.get("top_tag"):
        parts.append(f"_{str(data['top_tag']).strip()}_")
    if data.get("headline"):
        parts.append("**" + "\n".join(_as_lines(data["headline"])) + "**")
    if data.get("subhead"):
        parts.append("\n".join(_as_lines(data["subhead"])))
    if data.get("body"):
        parts.append("\n\n".join(_as_lines(data["body"])))
    if data.get("cta"):
        parts.append(f"👉 {str(data['cta']).strip()}")
    tags = _as_lines(data.get("hashtags"))
    if tags:
        parts.append(" ".join("#" + t.lstrip("#") for t in tags))
    if data.get("image_prompt"):
        parts.append(
            f"🖼 Şəkil promptu (hazır): {str(data['image_prompt']).strip()}\n"
            "İstəsən yaz: «şəkil yarat: <prompt>» — arxa fonu düzəldim."
        )
    return "\n\n".join(parts)


def _content_deliver(task: str, job_id: int) -> tuple[str, str, str | None]:
    """Structured content path: schema JSON -> (preview text, label, json path).
    The JSON artifact is the machine half — compose_for_brief-shaped — kept
    next to the job's .md artifact."""
    import json as _json
    data, model = _content_generate(task)
    if not (_as_lines(data.get("headline")) or _as_lines(data.get("body"))):
        raise ValueError("content schema came back empty")
    for key in ("headline", "subhead", "body", "hashtags"):
        data[key] = _as_lines(data.get(key))
    json_path: str | None = None
    try:
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = _OUTPUT_DIR / f"job-{job_id}-post.json"
        p.write_text(_json.dumps(data, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        json_path = str(p)
    except Exception:  # the preview must survive an artifact write failure
        json_path = None
    platform = str(data.get("platform") or "post").strip()
    return _render_post(data), f"content:{platform}->{model}", json_path


def _council_enabled() -> bool:
    # OFF by default: the operator wants the single conversational brain (one
    # microphone), not a multi-CLI council vote. Opt back in with
    # AI_COUNCIL_ENABLED=1 for deliberate, deliberation-worthy runs.
    return os.getenv("AI_COUNCIL_ENABLED", "0").lower() in {"1", "true", "yes", "on"}


def _council_tiers() -> set[str]:
    raw = os.getenv("AI_COUNCIL_TIERS", "complex").strip().lower()
    if raw in ("all", "*"):
        return {"complex", "fast", "free_bulk", "private"}
    return {t.strip() for t in raw.split(",") if t.strip()}


# Explicit council triggers. The operator said the council doesn't satisfy, so it
# NEVER fires on its own anymore — one microphone means one conversational brain
# by default. The council is a deliberate tool you summon by name.
_COUNCIL_TRIGGERS = ("/council", "şura:", "shura:", "council:")


def _council_should_run(task: str) -> bool:
    """Council fires ONLY when explicitly summoned (task starts with /council or
    'şura:') AND enabled. No automatic tier-based firing — casual messages always
    stay in the single conversational brain."""
    if not _council_enabled():
        return False
    low = (task or "").strip().lower()
    return any(low.startswith(t) for t in _COUNCIL_TRIGGERS)


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


# ============================ multi-step planner ==============================
# The one real capability gap (2026-07-17): the live path picks ONE lane per
# task. A marketer's real ask is often a CHAIN — "research the latest X, THEN
# draft posts about it". This planner decomposes such a task into ordered steps,
# runs each through an EXISTING lane (research / content / reason), threads each
# result into the next, and synthesises one deliverable. Reinforcement, not a new
# framework: it only orchestrates lanes we already have, and it runs AFTER the
# outward-action checkpoint, so it only ever researches and drafts — never posts.

_PLAN_CUES = ("sonra", "sonrasında", "ardınca", "əvvəlcə", "addım-addım",
              "addım addım", "then", "after that", "afterwards", "növbəti mərhələ",
              "birinci ", "ikinci ", "üçüncü ", "step by step", "və nəticədə",
              "daha sonra", "ondan sonra")


def _wants_plan(task: str) -> bool:
    """Cheap prefilter: only long-ish tasks that read as a sequence get sent to
    the decomposer. A false positive is harmless — the decomposer returns 1 step
    and the planner falls back to normal single-lane handling."""
    low = (task or "").lower()
    if len(low) < 25:
        return False
    return any(cue in low for cue in _PLAN_CUES)


_PLAN_PROMPT = (
    'Break the operator request into an ORDERED list of at most 4 concrete steps. '
    'Each step names exactly ONE lane:\n'
    '  research — needs live/current web facts (trends, news, prices, what is new)\n'
    '  content  — produce a brand-voiced social post / caption\n'
    '  reason   — think, synthesise, compare, plan or write using prior results\n'
    'Return ONLY JSON: {{"steps":[{{"lane":"research|content|reason","goal":"<one concrete instruction>"}}]}}. '
    'If the request is truly a single action, return exactly one step. Keep each '
    'goal specific and written in Azerbaijani.\n\nREQUEST:\n{task}'
)


def _decompose(task: str) -> list[dict]:
    """task -> ordered [{lane, goal}]. Cheap tier: decomposition is mechanical, so
    it must not spend the thinking cap. Returns [] on any problem (caller falls back)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from llm_router import complete_json
    data, _ = complete_json(_PLAN_PROMPT.format(task=task), tier="cheap", temperature=0.3)
    steps: list[dict] = []
    for s in (data.get("steps") or [])[:4]:
        goal = str(s.get("goal") or "").strip()
        lane = str(s.get("lane") or "reason").strip().lower()
        if lane not in ("research", "content", "reason"):
            lane = "reason"
        if goal:
            steps.append({"lane": lane, "goal": goal})
    return steps


def _research_grounded(task: str, thread: str) -> str:
    """Live Google-search-grounded answer. Extracted from execute()'s research
    mode so the planner reuses the exact same lane (single source of truth)."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    resp = client.models.generate_content(
        model=AGENT_MODEL,
        contents=task,
        config=types.GenerateContentConfig(
            system_instruction=knowledge.augment_system(_SYSTEM, task, thread)
            + " Dəqiq və ən son aktual məlumatlar üçün mütləq Google Axtarışdan istifadə et."
            + skills.relevant(task),
            temperature=0.2,
            tools=[{"google_search": {}}],
        ),
    )
    return resp.text or "Axtarış nəticə vermədi."


def _run_step(lane: str, goal: str, context: str, thread: str) -> str:
    """Run one planned step through its existing lane, with prior results as context."""
    prompt = f"{goal}\n\nƏvvəlki addımların nəticələri:\n{context}" if context else goal
    if lane == "research":
        return _research_grounded(goal, thread)  # research needs the raw goal, not the running context
    if lane == "content":
        try:
            data, _m = _content_generate(prompt)
            return _render_post(data)
        except Exception:
            text, _l = _converse(prompt, thread)
            return text
    text, _l = _converse(prompt, thread)  # reason / write / synthesise
    return text


def _plan_and_run(job, thread: str):
    """Decompose a multi-step task, run the lanes in sequence threading each result
    into the next, and synthesise one deliverable. Returns (text, label), or None
    to fall back to single-lane handling (not actually multi-step / decompose failed)."""
    try:
        steps = _decompose(job.task)
    except Exception as exc:  # noqa: BLE001
        sense.emit("llm", f"planner decompose failed: {exc}")
        return None
    if len(steps) < 2:
        return None  # a single step is just the normal path — don't wrap it

    results = []
    context = ""
    for i, step in enumerate(steps, 1):
        try:
            out = _run_step(step["lane"], step["goal"], context, thread)
        except Exception as exc:  # noqa: BLE001 — one bad step must not sink the chain
            out = f"(bu addım alınmadı: {exc})"
        results.append((i, step["goal"], out))
        # Keep the running context bounded so a long chain can't blow the prompt.
        context = (context + f"\n\n[Addım {i} — {step['goal']}]\n{out}").strip()[-6000:]
        sense.emit("llm", f"plan step {i}/{len(steps)} ({step['lane']})", {"job": job.id})

    digest = "\n\n".join(f"### Addım {i} — {goal}\n{out}" for i, goal, out in results)
    synth = (
        f"ƏSAS TAPŞIRIQ: {job.task}\n\nHər addımın nəticəsi aşağıdadır:\n\n{digest}\n\n"
        "Bunları operator üçün BİR bitmiş, aydın Azərbaycan dilində cavaba birləşdir. "
        "Addımların texniki adlarını sadalama; sadəcə yekun, hazır nəticəni təhvil ver."
    )
    try:
        final, _l = _converse(synth, thread)
    except Exception:  # noqa: BLE001 — synthesis is a bonus; the steps already ran
        final = digest
    return final, f"plan:{len(steps)}-addım"


def execute(job: Job) -> dict:
    """Run a job to completion. Returns {'result': str, 'artifacts': [paths]}.

    Picks a mode from the task wording:
      browser  -> drive a real headless browser (agent.run_browser_agent)
      research -> live web search via Gemini grounding
      plain    -> straight LLM completion
    Raises on unrecoverable failure; the worker turns that into a failed job.
    """
    try:
        # One microphone: every channel shares ONE conversation thread, so the
        # brain answers with cross-channel history (delivery still uses chat_id).
        thread = mic.thread_for(job)
        knowledge.set_current_thread(thread)
        decision = security.evaluate_task(job.task)
        security.audit_event(
            "job_preflight",
            decision,
            {"job_id": job.id, "source": job.source, "task": job.task},
        )
        if not decision.allowed:
            text = security.format_blocked_message(decision)
            artifact = _save_artifact(job.id, text, reply=True)
            return {"result": f"_[security:{decision.category}]_\n\n{text}", "artifacts": [artifact]}

        # Credential acquisition runs on its own governed rail (allowlist + operator
        # approval + masked output), ahead of the council/executor — it is a
        # deterministic action, not a deliberation, and must not be auto-executed.
        cred_provider = _credential_provider(job.task)
        if cred_provider:
            from .tools import credentials
            text = credentials.acquire(cred_provider)
            artifact = _save_artifact(job.id, text, reply=True)
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

        # AI Radar rail-i: gündəlik nəbz (yalnız kritik olanda sahibə yazır) və
        # həftəlik dərin brif. Schedule hər gün çağırır; taktı radar özü qoruyur.
        # Telegram-ı radar özü göndərir — schedule mənbəli işlər üçün worker
        # _notify Telegram-a yazmır (yalnız source=="telegram" bildirilir).
        if _is_radar(job.task):
            from . import radar
            text = radar.pulse(send=True) if _is_radar_pulse(job.task) else radar.run(send=True)
            artifact = _save_artifact(job.id, text)
            sense.emit("job", f"#{job.id} radar", {"task": job.task[:80]})
            return {"result": f"_[radar]_\n\n{text}", "artifacts": [artifact]}

        # Swipe rail-i: Ads of the World swipe faylı (idea-studio/adsworld.py).
        # Günlük schedule çağırır; 7 günlük keş həftəlik taktı özü qoruyur.
        if _is_swipe(job.task):
            script = Path(__file__).resolve().parent.parent / "idea-studio" / "adsworld.py"
            proc = subprocess.run(
                [sys.executable, str(script), "--pages", "3", "--deep", "5"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=900, cwd=str(script.parent.parent),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            text = (proc.stdout or "").strip()
            if proc.returncode != 0:
                text += "\n\nSTDERR:\n" + (proc.stderr or "").strip()
            artifact = _save_artifact(job.id, text)
            sense.emit("job", f"#{job.id} swipe", {"task": job.task[:80]})
            return {"result": f"_[swipe]_\n\n{text}", "artifacts": [artifact]}

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

        # Multi-step chain ("research X, then draft Y") -> orchestrate the existing
        # lanes in sequence. Runs AFTER the checkpoint above, so it only researches
        # and drafts. A non-multi-step task returns None here and falls through.
        if _wants_plan(job.task):
            planned = _plan_and_run(job, thread)
            if planned is not None:
                text, label = planned
                artifact = _save_artifact(job.id, text)
                sense.emit("llm", label, {"job": job.id, "mode": "plan"})
                return {"result": f"_[{label}]_\n\n{text}", "artifacts": [artifact]}

        if _council_should_run(job.task):
            from . import council
            label, text = council.run(job.task, _execute_after_council)
            artifact = _save_artifact(job.id, text)
            sense.emit("llm", f"council:{label}", {"job": job.id})
            return {"result": f"_[{label}]_\n\n{text}", "artifacts": [artifact]}

        mode = _choose_mode(job.task)
        bundle = None  # workspace zip, set in tools mode; delivered as a file
        extra_artifacts: list[str] = []  # e.g. the content lane's post JSON

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
                        _SYSTEM + _WORKSPACE_ADDENDUM, job.task, thread)
                    + skills.relevant(job.task),
                    temperature=0.2,
                    tools=[run_studio_automation, call_studio_api, list_studios,
                           generate_media, scrape_url, workspace_agent.run_command,
                           workspace_agent.write_file, workspace_agent.read_file,
                           workspace_agent.request_owner_approval,
                           workspace_agent.publish_site],
                )
            )
            label = f"agentic-tools:{agent_model}"
            try:
                resp = chat.send_message(job.task)
                text = resp.text or "Alətlər icra edildi, lakin mətn qaytarılmadı."
            except Exception as loop_exc:
                # The Gemini function-calling agent is unavailable (its API keys
                # are dead). Hand the SAME workspace to a working builder:
                # Codex (operator's ChatGPT) when its quota is available, else
                # real Claude Code (rotation), which is a first-class builder.
                text = None
                from . import claude_bridge
                for name, fn in (("codex", lambda: _codex_agent(job.task, ws)),
                                 ("claude", lambda: claude_bridge.build(job.task, ws))):
                    try:
                        text = fn()
                        label = f"agentic-tools:{name}"
                        break
                    except Exception as be:
                        sense.emit("llm", f"tools builder {name} unavailable: {be}")
                if text is None:
                    # every builder failed: salvage anything already on disk.
                    built = [str(p.relative_to(ws)) for p in sorted(ws.rglob("*")) if p.is_file()]
                    if not built:
                        raise loop_exc
                    text = (
                        "⚠️ İcra tam bitmədi (" + loop_exc.__class__.__name__ +
                        "), amma bu fayllar iş sahəsində hazırlandı:\n- " +
                        "\n- ".join(built)
                    )
            bundle = _bundle_workspace(job.id, ws)
            if bundle:
                text += f"\n\n📦 İş sahəsi paketi (yüklə): {bundle}"
        elif mode == "browser":
            agent_model = AGENT_MODEL
            text = agent.run_browser_agent(job.task, model=agent_model)
            label = f"browser:{agent_model}"
        elif mode == "research":
            # GOOGLE EKOSİSTEMİNİN ZİRVƏSİ: Native Google Search Grounding, extracted
            # to _research_grounded so the multi-step planner reuses the same lane.
            text = _research_grounded(job.task, thread)
            label = f"google-search-grounded:{AGENT_MODEL}"
        else:
            # The DEFAULT "one microphone" path: a single conversational brain
            # with the full shared history — like talking to the operator's
            # teammate, not a council. Deliverable-shaped tasks first try a
            # structured lane (strategy -> fan-out, social post -> content
            # schema); any failure falls back to conversation.
            text = label = None
            if _wants_fanout(job.task):
                try:
                    text, label = _fanout_deliver(job.task, thread)
                    mode = "fanout"
                except Exception as exc:
                    sense.emit("llm", f"fanout fell back to converse: {exc}")
            elif _wants_content(job.task):
                try:
                    text, label, json_path = _content_deliver(job.task, job.id)
                    mode = "content"
                    if json_path:
                        extra_artifacts.append(json_path)
                except Exception as exc:
                    sense.emit("llm", f"content path fell back to converse: {exc}")
            if text is None:
                text, label = _converse(job.task, thread)

        sense.emit("llm", label, {"job": job.id, "mode": mode})
        # A plain conversational turn is a chat message, not a work product.
        # ("router:" is the same converse path under its older label.)
        artifact = _save_artifact(
            job.id, text, reply=label.startswith(("chat:", "router:")))
        return {"result": f"_[{label}]_\n\n{text}",
                "artifacts": [artifact] + ([bundle] if bundle else [])
                             + extra_artifacts}
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
