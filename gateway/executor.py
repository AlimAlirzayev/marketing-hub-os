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


# Ads morning pulse rail (gateway/ads_watch.py): the scheduled Meta Ads digest —
# yesterday vs the trailing week, explicit anomaly flags (delivery stop, spend
# spike, CPR spike, CTR collapse). Deterministic arithmetic over Ads Studio's
# own aggregates; zero LLM tokens. Cues stay narrow so ordinary ads questions
# ("reklamlar necə gedir?") keep going to the chat/ads-agent paths.
_ADS_WATCH_CUES = ("reklam nəbzi", "reklam nebzi", "ads səhər", "ads seher",
                   "ads morning pulse", "ads watch", "/adswatch")


def _is_ads_watch(task: str) -> bool:
    low = (task or "").strip().lower()
    return any(cue in low for cue in _ADS_WATCH_CUES)


# Impact Ledger rail (gateway/impact_ledger.py): the monthly "what the OS did for
# Xalq" blended scorecard — business RESULTS (leads/CPA/conversions/SLA, live +
# source-labelled) beside system WORK (deliverables + hours saved from the real
# job queue). The operator's indispensability argument. Cues stay specific so
# ordinary "hesabat" chatter keeps routing to the normal briefing.
_IMPACT_CUES = ("təsir jurnalı", "tesir jurnali", "impact ledger", "təsir hesabatı",
                "tesir hesabati", "xalq təsir", "xalq tesir", "/impact")


def _is_impact_ledger(task: str) -> bool:
    low = (task or "").strip().lower()
    return any(cue in low for cue in _IMPACT_CUES)


# Operations Self-Review rail (gateway/self_review.py): the weekly reliability
# retrospective — how well the OS ran, what broke, brain fallbacks, security —
# with distilled lessons to the brain. Cues stay specific so ordinary chatter
# routes to the normal briefing/advisor, not here.
_SELF_REVIEW_CUES = ("özünü qiymətləndir", "ozunu qiymetlendir", "əməliyyat hesabatı",
                     "emeliyyat hesabati", "self review", "self-review", "/selfreview",
                     "özü-qiymətləndirmə", "ozu-qiymetlendirme")


def _is_self_review(task: str) -> bool:
    low = (task or "").strip().lower()
    return any(cue in low for cue in _SELF_REVIEW_CUES)


# Brain curation rail (brain/curator.py): the scheduled autonomous review of
# the pending lesson queue — the LLM promotes/rejects reflect suggestions and
# the operator gets a digest instead of a queue chore. Cues stay narrow so
# ordinary "dərs" chatter keeps going to the normal paths.
_BRAIN_CURATE_CUES = ("dərs təftişi", "ders teftisi", "beyin təftişi",
                      "beyin teftisi", "brain curate", "/braincurate")


def _is_brain_curate(task: str) -> bool:
    low = (task or "").strip().lower()
    return any(cue in low for cue in _BRAIN_CURATE_CUES)


# SEO mission rail (seo/ engine): the operator asks "why aren't we ranking — find
# it and FIX it, don't just advise". Instead of talking (or asking for a CSV), the
# bot RUNS the real engine — live technical audit (real crawl) + SERP content-gap —
# then the premium brain synthesises an EXECUTION-ready fix pack (root causes +
# paste-ready snippets + first-week plan). Read-only on the target site: it produces
# the pack, never touches the live site (publish/deploy stays a human-approved
# action). Cues stay specific so ordinary chat ("seo nədir?") isn't hijacked.
_SEO_MISSION_CUES = (
    "seo audit", "seo analiz", "seo-sunu", "seo sunu", "seo-nu", "texniki seo",
    "niyə sıralan", "niye siralan", "sıralanmır", "siralanmir", "sıralana bilmir",
    "ön səhifədə çıx", "on sehifede cix", "ön səhifəyə çıx", "on sehifeye cix",
    "axtarışda görün", "axtarisda gorun", "axtarış görünürlüy", "axtaris gorunurluy",
    "search visibility", "ranking", "sıralanma", "siralanma", "/seo",
)


def _is_seo_mission(task: str) -> bool:
    low = (task or "").strip().lower()
    return any(cue in low for cue in _SEO_MISSION_CUES)


_DOMAIN_RE = re.compile(
    r"\b((?:https?://)?(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*"
    r"\.(?:az|com|net|org|edu|info|biz|io|co)(?:/[^\s)]*)?)", re.IGNORECASE)


def _seo_plan(task: str) -> dict:
    """Extract the SEO mission target: the site URL (an explicit domain in the task
    wins — e.g. edudistance.az — else the brand's own site) and up to 2 focus
    keywords. Never raises; falls back to the brand site with no keywords."""
    m = _DOMAIN_RE.search(task or "")
    url = m.group(1) if m else ""
    if not url:
        try:
            from brand import BRAND
            url = BRAND.website or ""
        except Exception:
            url = ""
    keywords: list[str] = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from llm_router import complete_json
        data, _ = complete_json(
            "Bu tapşırıqdan SEO fokusunu çıxar. Yalnız STRICT JSON qaytar: "
            '{{"keywords": ["1-3 əsas axtarış açar sözü/mövzu, Azərbaycanca"]}}. '
            f"Tapşırıq: {task}",
            # smart tier = Claude-first (the brain), free only as the resilience
            # floor — the operator's rule: the brain is Claude, never Gemini by
            # default (it burns metered API quota). Router policy: _claude_first.
            tier="smart", temperature=0.2)
        keywords = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()][:2]
    except Exception:
        keywords = []
    return {"url": url, "keywords": keywords}


def _seo_mission(job: Job, thread: str) -> tuple[str, list[str]]:
    """Run the real SEO engine end-to-end and synthesise an execution-ready
    deliverable. Returns (deliverable_text, extra_artifact_paths). Never raises —
    a synthesis failure still ships the raw live audit (the crawl already ran)."""
    from seo.audit.auditor import audit_url
    from seo.report import audit_report

    plan = _seo_plan(job.task)
    url = plan["url"]
    artifacts: list[str] = []
    if not url:
        return ("SEO missiyası üçün hədəf sayt tapılmadı — tapşırıqda domen göstər "
                "(məs. example.az) və ya BRAND.website təyin et.", artifacts)

    # 1) live technical audit (real crawl; hardened fetch survives apex/SSL quirks)
    result = audit_url(url, with_vitals=True)
    audit_txt = audit_report(result)
    try:
        from seo.render import save_audit_html
        artifacts.append(str(save_audit_html(result)))
    except Exception as exc:  # noqa: BLE001 — the HTML report is a bonus, not the job
        sense.emit("seo", f"audit html render skipped: {exc}")

    # 2) SERP content-gap on the top focus keyword (best-effort, bounded to one kw)
    gap_txt = ""
    kw = plan["keywords"][0] if plan["keywords"] else ""
    if kw:
        try:
            from seo.report import gap_report
            from seo.research.gap import analyze_gap
            gap_txt = gap_report(analyze_gap(kw, top_n=5))
        except Exception as exc:  # noqa: BLE001
            gap_txt = f"(SERP content-gap alınmadı: {exc})"

    # 3) premium synthesis into an EXECUTION-ready deliverable (never mere advice)
    material = (
        f"HƏDƏF SAYT: {result.final_url or url}  ·  SEO BALI: {result.score}/100 "
        f"({result.grade})\n\n=== TEXNİKİ AUDİT (CANLI TARAMA) ===\n{audit_txt}\n\n"
        + (f"=== SERP CONTENT-GAP — “{kw}” ===\n{gap_txt}\n" if gap_txt else "")
    )[:9000]
    synth_system = (
        "Sən icra-yönümlü SEO mühəndisisən. Sənə CANLI audit + SERP gap materialı "
        "verilir. Vəzifən MƏSLƏHƏT vermək DEYİL — yapışdırmağa hazır düzəlişlər "
        "çıxarmaqdır. Materialda olmayan rəqəm/fakt uydurma." + _self_facts()
    )
    prompt = (
        f"Operatorun tapşırığı: {job.task}\n\nCANLI MATERİAL:\n{material}\n\n"
        "Bunun əsasında Azərbaycanca, konkret, İCRA-hazır deliverable ver. Bölmələr:\n"
        "1) NİYƏ SIRALANMIRIQ — audit+gap-dən çıxan 3-5 əsas kök səbəb (yalnız "
        "materialdan, uydurma yox).\n"
        "2) DƏRHAL TƏTBİQ OLUNAN TEXNİKİ DÜZƏLİŞLƏR — hər problem üçün YAPIŞDIRMAĞA "
        "HAZIR kod ver: çatışmayan `<meta viewport>`, JSON-LD schema (Organization + "
        "WebSite, real domen/ada görə), `<link rel=canonical>`, təklif olunan H1 "
        "mətni, Open Graph tag-ləri. Real domeni işlət.\n"
        "3) KONTENT BOŞLUQLARI — gap-dən: hansı mövzu/FAQ səhifələri yaradılmalı.\n"
        "4) İLK 7 GÜN — prioritetli, ölçülə bilən addım siyahısı.\n"
        "Canlı saytda dəyişikliyi ÖZÜN TƏTBİQ ETMƏ — paket insan təsdiqi ilə tətbiq olunur."
    )
    try:
        from . import brain
        text, model = brain.answer(prompt, system=synth_system, prefer="claude", timeout=120)
        if not text or text.startswith("[brain error]"):
            raise RuntimeError(text or "empty synthesis")
        header = (f"🔎 **SEO missiyası — {result.final_url or url}** · "
                  f"bal {result.score}/100 ({result.grade})\n\n")
        note = ("\n\n—\n_İcra-hazır fix paketi ({model}). Canlı saytda tətbiq/deploy "
                "ayrıca addımdır — « tətbiq et » desən, təsdiqlə növbəyə salıram._"
                ).format(model=model)
        return header + text + note, artifacts
    except Exception as exc:  # noqa: BLE001 — never lose the crawl that already ran
        sense.emit("seo", f"seo mission synth failed: {exc}")
        raw = audit_txt + (f"\n\n{gap_txt}" if gap_txt else "")
        return ("🔎 SEO missiyası — sintez alınmadı, canlı audit təhvil verilir:\n\n"
                + raw), artifacts


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
    "checkpoint. "
    "VOICE: talk like a teammate in one natural conversation, never a ticketing "
    "system. Never show internal job numbers (no \"İş #135\", no invented "
    "\"№451\"), never tell the operator to type \"/approve N\", never narrate "
    "pipeline mechanics (\"növbəyə salındı\", \"build xəttinə verildi\", \"ayrıca "
    "mesajla gələcək\"). Do not pretend you did something you did not — if you "
    "cannot actually create/post/build from here, say so plainly instead of "
    "inventing a result. If an action needs a go-ahead, ask one plain hə/yox."
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
    "posts), a 3-persona FAN-OUT for strategy work, and a MULTI-STEP PLANNER that "
    "chains research→content→reason for 'do X then Y' asks.\n"
    "- Crew summon (you are the router): for a HEAVY multi-studio marketing "
    "deliverable run `python3 -m gateway.summon crew \"<goal>\"` — async, the "
    "worker delivers the crew's result to the owner chat as a separate message.\n"
    "- Hands in chat: bridge turns can CALL the live studio APIs through "
    "`python3 -m gateway.studio_api` (read-safe door; spend/post actions still "
    "park at the /approve checkpoint).\n"
    "- Proactive: the supervisor scheduler runs recurring jobs (morning briefing, "
    "ads morning pulse, radar) — gateway/scheduler.py; the research lab feeds the "
    "Radar section of shared memory on its own cron.\n"
    "- Self-healing: a supervisor watchdog thread (gateway/watchdog.py) health-checks "
    "the standing services.json organs; a crashed one is detected, the owner is pinged, "
    "and relaunched automatically (auto-restart is ON by default, circuit-broken after "
    "repeated failures; set WATCHDOG_AUTO_RESTART=0 to pause). Do NOT propose building "
    "service monitoring; it exists.\n"
    "- Impact Ledger (gateway/impact_ledger.py): say 'təsir jurnalı' (or /impact) for "
    "the monthly 'what the OS did for Xalq' scorecard — business RESULTS (leads/CPA/"
    "conversions/complaint-SLA, live + source-labelled CANLI/DEMO/ƏLÇATMAZ) beside "
    "system WORK (real deliverable counts + hours-saved estimate from the job queue). "
    "It also delivers ITSELF (a supervisor thread emits last month's ledger to the "
    "owner once when a new month turns) and renders a report-grade HTML/PDF leadership "
    "document (gateway/impact_render.py, Xalq brand, headless-Edge PDF) beside the "
    "Telegram text. The indispensability argument; numbers are never invented. Do NOT "
    "propose building an impact/ROI report; it exists.\n"
    "- Self-improvement (gateway/self_review.py): a WEEKLY Operations Self-Review grades "
    "the OS's own week from its event log (reliability, service incidents, premium-brain "
    "free-fallbacks, security rejects) and files durable lessons to the brain's review "
    "queue; a supervisor thread delivers it on its own, or say 'özünü qiymətləndir' / "
    "'self review' on demand. This is Pillar 4 (the system learns from itself); do NOT "
    "propose building an ops self-review or reliability retrospective — it exists.\n"
    "- Self-improving memory: after each job the brain distills lessons (reflect), "
    "and a daily autonomous CURATOR (brain/curator.py) reviews that queue itself — "
    "promoting the good ones into long-term memory, dropping the noise — so learning "
    "compounds without anyone approving a queue by hand. Do NOT propose building a "
    "lesson-review feature; it exists.\n"
    "- Interfaces: the Telegram bot, the control panel (port 8890) with a live map, and "
    "Codex — all one shared conversation and memory.\n"
    "- Trello work board: gateway/trello.py connects only the allowlisted Xalq Insurance "
    "board RRlLCaSG. It can read snapshots after local authorization; create/move/update/"
    "comment writes require an exact saved-plan approval code, while deletion, membership, "
    "visibility, and cross-board actions are blocked. Its connection-check runs headlessly, "
    "opens no browser, performs no board write, and saves a secret-free status artifact.\n"
    "- Safety: risky/outward actions (post/send/pay/delete) PARK at a human checkpoint "
    "(/approve N, /reject N).\n"
    "- Marketing data: you have NO live Meta/Google Ads pull unless credentials are "
    "configured — say that plainly rather than inventing numbers.\n"
    "- Google Ads policy audit exists at ads-studio/google_ads_policy_audit.py: it "
    "reads disapproved/limited ad policy topics only when Google Ads credentials are "
    "configured; edits and appeals remain human-approved production actions.\n"
    "- Azerbaijani Google Ads language support cannot be enabled by API or Editor; "
    "ads-studio/google_ads_az_language_request.py converts an Editor export into a "
    "redacted official-support dossier and never bypasses policy.\n"
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


# Injected ONLY into the bridge (headless Claude) chat path. The free-floor
# brains must never see this: they have no shell, and telling a handless brain
# it has hands produces hallucinated "I ran it" answers. The bridge's
# --allowedTools covers exactly this command prefix (gateway/claude_bridge.py).
_BRIDGE_HANDS = (
    "\n\nSERVICE HANDS. You can OPERATE the live studios, not just describe "
    "them, through one governed shell command:\n"
    "  python3 -m gateway.studio_api list\n"
    "  python3 -m gateway.studio_api call <studio> <path> [--method GET|POST] "
    "[--body '<json>']\n"
    "Discover a studio's endpoints first: call <studio> /openapi.json. When the "
    "operator asks for something a studio can answer (reports, SEO audit, "
    "influencer search, price check, complaints, GA4, the morning briefing), "
    "CALL it and answer with the real numbers — never invent data and never "
    "just point at a panel URL. The door is read-safe: registered studios only, "
    "127.0.0.1 only; spend/post/delete paths are blocked and need the /approve "
    "checkpoint. If a call fails, say so honestly instead of guessing."
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
    # Codex only counts as done when it wrote its final-message file. Without
    # it (usage limit, auth error, crash) stdout is just the prompt echo plus an
    # ERROR line -- NOT a deliverable. Returning that would ship raw internal
    # machinery to the operator AND make the caller skip the Claude fallback
    # wired right after us. So raise: let a real builder take over.
    text = ""
    if out_file.exists():
        text = out_file.read_text(encoding="utf-8", errors="replace").strip()
        try:
            out_file.unlink()
        except Exception:
            pass
    if not text:
        tail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"codex produced no final message (rc={proc.returncode}): {tail[-200:]}")
    return text


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


# --- build self-check ------------------------------------------------------
# "Done" used to mean "the builder said done" — nothing ever looked at what was
# on disk. This bounded loop closes that gap: deterministic checks over the job
# workspace (compile/parse/broken local refs — zero LLM tokens), failures fed
# back to the SAME builder for at most _VERIFY_ROUNDS fix rounds, and anything
# still broken is reported HONESTLY in the deliverable instead of being shipped
# silently. Conversational/tool-only jobs leave the workspace empty and are
# skipped — there is nothing on disk to verify.

_VERIFY_ROUNDS = int(os.getenv("VERIFY_MAX_FIX_ROUNDS", "2"))
_VERIFY_FEEDBACK = (
    "VERIFICATION FAILED. An automated check of the workspace found these "
    "problems:\n{problems}\n\nFix them now — edit the files and finish the job. "
    "Do not claim success while any problem remains."
)
_REF_RE = re.compile(r"""(?:href|src)=["']([^"'#?]+)["']""", re.IGNORECASE)
_REF_SKIP = ("http://", "https://", "//", "data:", "mailto:", "tel:", "javascript:")


def _verify_workspace(ws: Path) -> list[str]:
    """Deterministic checks over the built files; [] means verified-or-nothing."""
    import json as _json
    import py_compile

    problems: list[str] = []
    try:
        files = [p for p in sorted(ws.rglob("*"))
                 if p.is_file() and not p.name.startswith(".")]
    except Exception:
        return []
    for p in files:
        rel = str(p.relative_to(ws))
        try:
            if p.stat().st_size == 0:
                problems.append(f"{rel}: file is empty")
                continue
            if p.suffix == ".py":
                py_compile.compile(str(p), doraise=True)
            elif p.suffix == ".json":
                _json.loads(p.read_text(encoding="utf-8", errors="replace"))
            elif p.suffix in (".html", ".htm"):
                html = p.read_text(encoding="utf-8", errors="replace")
                for ref in _REF_RE.findall(html):
                    if ref.startswith(_REF_SKIP):
                        continue
                    target = (ws / ref.lstrip("/")) if ref.startswith("/") else (p.parent / ref)
                    if not target.exists():
                        problems.append(f"{rel}: broken local reference '{ref}'")
        except Exception as exc:
            problems.append(f"{rel}: {exc.__class__.__name__}: {str(exc)[:160]}")
    return problems[:12]


def _verify_note(problems: list[str]) -> str:
    return ("\n\n⚠️ Özünü-yoxlama: bu problemlər düzəlmədən qaldı — nəticəni "
            "yoxlamadan istifadə etmə:\n" + "\n".join(f"- {p}" for p in problems))


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
    """Which brain answers the conversational path. Claude by default (2026-07-19); MIC_BRAIN=free = Gemini via
    the router; 'claude' = real headless Claude Code (this chat on any mic, opt-in
    because it spends subscription quota). See gateway/claude_bridge.py."""
    return os.getenv("MIC_BRAIN", "claude").strip().lower()


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
                grounding = knowledge.augment_system(_self_facts() + _BRIDGE_HANDS, task)
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
    # The 3-persona fan-out runs on generic free-model marketing personas with
    # NO system awareness. When the premium brain (MIC_BRAIN=claude) is on it
    # answers strategy/plan questions itself, grounded in the real system (what
    # we own, the queue, the decisions log) — far better than three generic
    # essays. So fan-out is a FREE-FLOOR enrichment only, never a premium-path
    # detour. (2026-07-18: job #118 "analyze our unfinished work & plan" hit
    # fan-out and returned a 5.5k-char generic marketing essay disconnected
    # from any real work.)
    if _mic_brain() == "claude":
        return False
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
    # Engage ONLY for a genuine multi-lane chain. A single step, or an all-"reason"
    # plan (pure thinking — a strong single _converse handles that just as well), is
    # left to the normal path, so the planner never hijacks a quick chat turn.
    if len(steps) < 2 or all(s["lane"] == "reason" for s in steps):
        return None

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


# --- CrewAI orchestration lane (opt-in, gated) ---------------------------
# A hierarchical CrewAI crew over the studios, for HEAVY multi-studio tasks only.
# Deliberately NOT the default path: OFF unless CREW_ENABLED is set, fires only on
# an explicit summon (so a greeting or a simple question never pays the ~60-120s
# crew tax), sits AFTER the checkpoint (research/draft only, never posts), and runs
# in an ISOLATED venv as a subprocess so crewai's heavy deps never touch this
# runtime. Auto-routing heavy tasks is a later step, once proven live. See
# gateway/studio_crew.py.
_CREW_ENABLED = os.getenv("CREW_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
_CREW_PY = os.getenv(
    "CREW_PY",
    str(Path(__file__).resolve().parent.parent / ".venv-crew" / "bin" / "python"),
)
_CREW_TRIGGERS = ("/crew", "krew:", "crew:", "komanda:")


def _wants_crew(task: str) -> bool:
    """Explicit /crew summon (kept as a power-user override)."""
    if not _CREW_ENABLED:
        return False
    return (task or "").strip().lower().startswith(_CREW_TRIGGERS)


# The crew is the STANDING operational workforce (operator directive 2026-07-19):
# real marketing WORK is run by the CrewAI crew (the workers) with Claude as the
# brain/synthesis on top — not a manual /crew summon. Kept CONSERVATIVE so trivial
# chat and quick fetches never pay the crew tax; a miss still falls through to the
# existing lanes, and a crew failure returns None so the job is answered by
# Claude/plan/council anyway. Auto-route is scoped to operator jobs (telegram/cli)
# so scheduled deliverables keep their proven rails untouched.
_CREW_HEAVY_CUES = (
    "kampaniya", "strategiya", "strateji", "hesabat", "analiz", "audit",
    "təklif", "brief", "büdcə", "rəqib", "rəqabət", "bazar araşdır",
    "kontent plan", "content plan", "reklam strateji", "tam analiz",
    "report", "strategy", "campaign", "proposal", "budget", "competitor",
)


# NEGATIVE guards (2026-07-19, jobs #124/#125): the crew is a marketing
# workforce with NO conversation memory and NO system awareness, so a
# conversational or system-directed turn must never be hijacked by it. A
# greeting-wrapped report ask got "no data, empty report" (the chat brain had
# answered the same ask with real numbers a day earlier), and "analyze our
# unfinished work" (system tasks) came back as a GA4 funnel-abandonment essay.
# These guards fail SAFE: a blocked turn goes to the grounded chat brain,
# which handles deliverable asks well — bias away from the crew.
_CREW_BLOCK_OPENERS = ("salam", "necəsən", "necesen", "hə", "bəli", "beli",
                       "ok", "okey", "oldu", "aha")
_CREW_SYSTEM_WORDS = ("yarımçıq", "yarimciq", "sistem", "növbə", "novbe",
                      "repo", "commit", "server", "bot", "dərs", "ders",
                      "schedule", "cron", "job", "queue", "iş #")


def _is_heavy_operational(task: str) -> bool:
    """Auto-route genuinely heavy, operational multi-studio work to the crew."""
    if not _CREW_ENABLED:
        return False
    if _mic_brain() == "claude":
        # "The model is the router" (2026-07-20): with the premium brain on,
        # the brain itself summons the crew (gateway/summon.py) when a turn
        # deserves it — after 4 keyword misroutes in 3 days, keyword auto-route
        # survives only as the free-floor fallback. Explicit /crew still works.
        return False
    t = (task or "").strip().lower()
    if len(t) < 40:                      # too short to be heavy operational work
        return False
    first = t.split()[0].strip(",.!?;:") if t.split() else ""
    if first in _CREW_BLOCK_OPENERS:     # small talk opener -> conversation
        return False
    if any(w in t for w in _CREW_SYSTEM_WORDS):  # about the SYSTEM, not marketing
        return False
    return any(cue in t for cue in _CREW_HEAVY_CUES)


def _run_crew(task: str, thread: str | None = None) -> str | None:
    """Run the CrewAI crew subprocess (isolated venv) with a hard-timeout backstop.
    Returns the deliverable, or None to fall through to normal handling on any
    failure (missing venv, timeout, or no clean result marker)."""
    goal = task.strip()
    for trig in _CREW_TRIGGERS:
        if goal.lower().startswith(trig):
            goal = goal[len(trig):].strip()
            break
    if not goal or not Path(_CREW_PY).exists():
        return None
    deadline = int(os.getenv("CREW_DEADLINE_SECONDS", "300"))
    try:
        proc = subprocess.run(
            [_CREW_PY, "-m", "gateway.studio_crew", goal],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=deadline + 40,
            cwd=str(Path(__file__).resolve().parent.parent),
            env={**os.environ, "PYTHONIOENCODING": "utf-8",
                 "STUDIO_API_TIMEOUT": os.getenv("STUDIO_API_TIMEOUT", "20"),
                 "CREW_DEADLINE_SECONDS": str(deadline),
                 # Workers on a FAST Claude model (subscription, not billed
                 # Gemini); synthesis keeps the default fable-first ladder in
                 # the main process. Override with CREW_CLAUDE_LADDER.
                 "CLAUDE_CHAT_LADDER": os.getenv(
                     "CREW_CLAUDE_LADDER",
                     "claude-haiku-4-5-20251001,claude-sonnet-5,claude-fable-5"),
                 "CREW_CLAUDE_TIMEOUT": os.getenv("CREW_CLAUDE_TIMEOUT", "150")},
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    out = proc.stdout or ""
    begin, end = "<<<CREW_RESULT_BEGIN>>>", "<<<CREW_RESULT_END>>>"
    if begin not in out or end not in out:
        return None
    raw = out.split(begin, 1)[1].split(end, 1)[0].strip()
    if not raw:
        return None
    # Worker-brain transparency: the crew appends a [workers: ...] stats line —
    # lift it out of the material and surface it in the final label instead.
    worker_stats = ""
    if raw.rsplit("\n", 1)[-1].startswith("[workers:"):
        raw, _, worker_stats = raw.rpartition("\n")
        raw = raw.strip()
    # Claude is the TOP quality layer over the crew gather: turn the crew raw
    # studio research into a polished, grounded deliverable. On any brain failure
    # (all Claude rungs capped AND free down) keep the raw crew text — the heavy
    # work already ran, so a synthesis hiccup must never lose it.
    try:
        from . import brain
        # Ground the synthesis exactly like the chat brain (self-facts + system
        # card + thread memory): the crew workers see only studio data, so the
        # synthesizer must be the layer that knows the system and the ongoing
        # conversation — it can then correct a crew misreading instead of
        # shipping a polished answer to the wrong question (jobs #124/#125).
        synth_system = ("Sən təcrübəli marketinq strateqisən və operatorun danışan "
                        "beynisən; verilən materiala və sistem yaddaşına söykən.")
        try:
            synth_system = knowledge.augment_system(
                synth_system + _self_facts(), goal, thread)
        except Exception:
            pass  # grounding is an upgrade, never a blocker
        polished, model = brain.answer(
            f"Operatorun tapşırığı: {goal}\n\nKomandanın topladığı material:\n"
            f"{raw[:6000]}\n\nBunu operator üçün YEKUN, aydın, yalnız bu materiala "
            "əsaslanan Azərbaycanca deliverable-a çevir. Materialda olmayan rəqəm "
            "uydurma. Əgər material operatorun əsl sualına cavab vermirsə (sual "
            "sistem və ya söhbət haqqındadırsa), bunu açıq de və suala sistem "
            "yaddaşınla düzgün cavab ver.",
            system=synth_system, prefer="claude", timeout=90,
        )
        if polished and not polished.startswith("[brain error]"):
            tag = f" {worker_stats}" if worker_stats else ""
            return f"{polished}\n\n—\n_krew (studiolar){tag} + {model} sintez_"
    except Exception:
        pass
    return raw


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

        # Ads morning pulse rail: deterministic digest + anomaly flags. The
        # schedule row carries source='telegram' + the owner chat id, so the
        # worker delivers it to Telegram like any operator job.
        if _is_ads_watch(job.task):
            from . import ads_watch
            text = ads_watch.report()
            artifact = _save_artifact(job.id, text)
            sense.emit("job", f"#{job.id} ads-watch", {"task": job.task[:80]})
            return {"result": f"_[ads-watch]_\n\n{text}", "artifacts": [artifact]}

        # Impact Ledger rail: the monthly blended Xalq-impact scorecard. Live
        # results are source-labelled (CANLI/DEMO/ƏLÇATMAZ — never invented); the
        # work side is real counts from the durable job queue. Zero LLM tokens.
        if _is_impact_ledger(job.task):
            from . import impact_ledger
            # Collect once → Telegram text + the report-grade HTML/PDF leadership doc.
            text, html_path = impact_ledger.save_report(to_pdf=True)
            if html_path:
                text += f"\n\n📄 Rəhbərlik üçün hesabat: {html_path}"
            artifact = _save_artifact(job.id, text)
            sense.emit("job", f"#{job.id} impact-ledger", {"task": job.task[:80]})
            return {"result": f"_[impact-ledger]_\n\n{text}", "artifacts": [artifact]}

        # Operations Self-Review rail: on-demand weekly reliability retrospective
        # (the supervisor also delivers it weekly on its own). Deterministic counts
        # over the sense event log; zero LLM tokens.
        if _is_self_review(job.task):
            from . import self_review
            text = self_review.report()
            artifact = _save_artifact(job.id, text)
            sense.emit("job", f"#{job.id} self-review", {"task": job.task[:80]})
            return {"result": f"_[self-review]_\n\n{text}", "artifacts": [artifact]}

        # Brain curation rail: the system reviews its own pending lessons and
        # reports the outcome. Schedule row carries source='telegram' + the
        # owner chat id, so the digest lands in Telegram like any operator job.
        if _is_brain_curate(job.task):
            from brain import curator
            text = curator.report()
            artifact = _save_artifact(job.id, text)
            sense.emit("job", f"#{job.id} brain-curate", {"task": job.task[:80]})
            return {"result": f"_[brain-curate]_\n\n{text}", "artifacts": [artifact]}

        # SEO mission rail: "why aren't we ranking — find it and FIX it". Runs the
        # real engine (live crawl audit + SERP content-gap) and returns an
        # execution-ready fix pack, not advice. Read-only on the target site; it
        # never publishes (that stays a human-approved action), so it sits with the
        # other read-only analysis rails ahead of the checkpoint. Must precede the
        # multi-step planner: the operator's ask often contains "sonra" and would
        # otherwise be hijacked into a talk-only research essay.
        if _is_seo_mission(job.task):
            text, extra = _seo_mission(job, thread)
            artifact = _save_artifact(job.id, text)
            sense.emit("job", f"#{job.id} seo-mission", {"task": job.task[:80]})
            return {"result": f"_[seo-mission]_\n\n{text}",
                    "artifacts": [artifact] + extra}

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
                # Speak like a teammate, not a form: the owner just answers "hə"
                # or "yox" and the bot's plain-language checkpoint (gateway/bot.py)
                # maps it to this parked job. The /approve N line is a quiet
                # fallback for when more than one job is waiting, not the ask.
                text = (
                    "Bu, bayıra yönəlik bir əməldir (paylaşım/göndəriş/zəng/deploy), "
                    "ona görə səndən soruşmadan etmirəm.\n\n"
                    f"İstədiyin: {job.task}\n\n"
                    "Göndərim? — **hə** desən edirəm, **yox** desən saxlayıram."
                )
                return {"result": text, "artifacts": [], "needs_approval": True}

        # CrewAI orchestration lane (opt-in): heavy multi-studio work, summoned.
        # OFF by default; fires only on an explicit /crew summon with CREW_ENABLED.
        if _wants_crew(job.task) or (
            _is_heavy_operational(job.task) and job.source in ("telegram", "cli")
        ):
            crew_text = _run_crew(job.task, thread)
            if crew_text:
                artifact = _save_artifact(job.id, crew_text)
                sense.emit("llm", "crew", {"job": job.id, "mode": "crew"})
                return {"result": f"_[crew]_\n\n{crew_text}", "artifacts": [artifact]}
            # crew unavailable/failed -> fall through to normal handling

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
            producer = None  # which builder made the result -> who gets fix rounds
            try:
                resp = chat.send_message(job.task)
                text = resp.text or "Alətlər icra edildi, lakin mətn qaytarılmadı."
                producer = "gemini"
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
                        producer = name
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
            # Bounded self-check: verify the workspace, feed failures back to
            # the builder that produced it, deliver honestly if still broken.
            problems = _verify_workspace(ws)
            for round_no in range(1, _VERIFY_ROUNDS + 1):
                if not problems or producer is None:
                    break
                feedback = _VERIFY_FEEDBACK.format(
                    problems="\n".join(f"- {p}" for p in problems))
                try:
                    if producer == "gemini":
                        resp = chat.send_message(feedback)
                        text = resp.text or text
                    elif producer == "codex":
                        text = _codex_agent(f"{job.task}\n\n{feedback}", ws)
                    else:
                        from . import claude_bridge
                        text = claude_bridge.build(f"{job.task}\n\n{feedback}", ws)
                    label += f"+fix{round_no}"
                except Exception as fix_exc:
                    sense.emit("llm", f"verify fix round {round_no} failed: {fix_exc}")
                    break
                problems = _verify_workspace(ws)
            if problems:
                sense.emit("job", f"#{job.id} verify failed",
                           {"problems": "; ".join(problems)[:200]})
                text += _verify_note(problems)
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
