"""Seed the Knowledge Core with the durable learnings we already earned.

These are the hard-won, system-level rules and decisions from many sessions of
work on RAMIN OS -- exactly the things that should never have to be re-learned.
Running this is idempotent: each entry has a fixed id, so re-seeding overwrites
rather than duplicates.

    python -m brain.seed            # write/refresh the seed entries
"""

from __future__ import annotations

from .store import Entry, rebuild_index_file, save

SEED: list[Entry] = [
    Entry(
        id="pref-language-split",
        type="preference",
        title="Language split: chat AZ, code/configs EN, deliverables AZ",
        confidence="high",
        tags=["language", "communication", "deliverables"],
        body=(
            "Speak Azerbaijani with the operator. Write code, configs, identifiers and "
            "internal docs in English. EXCEPTION: user-facing deliverables (reports, "
            "PDFs, captions) are in Azerbaijani because the audience is Azerbaijani."
        ),
    ),
    Entry(
        id="decision-deliverable-design-bar",
        type="decision",
        title="Deliverable design bar: cover + cards + badges + phased section",
        confidence="high",
        tags=["deliverables", "design", "pdf", "report"],
        body=(
            "Report-style deliverables must clear a design bar: a cover page, card "
            "layout, status badges, and a phased-workflow section. Plain tables are "
            "below the bar. The working PDF path is HTML rendered through headless "
            "Edge -- not a Python PDF lib. Why: the operator judges quality visually "
            "and a flat table reads as unfinished."
        ),
    ),
    Entry(
        id="lesson-no-silent-drops",
        type="lesson",
        title="No silent drops when an API errors",
        confidence="high",
        tags=["reliability", "api", "process"],
        body=(
            "Never quietly skip or remove a feature because an API call failed. "
            "Surface the problem and try alternatives BEFORE changing scope. Why: a "
            "silent drop hides a fixable issue and erodes trust in the result."
        ),
    ),
    Entry(
        id="lesson-proactive-completeness",
        type="lesson",
        title="Enumerate the full landscape and self-critique before declaring done",
        confidence="high",
        tags=["process", "quality", "thoroughness"],
        body=(
            "Map the whole landscape and critique your own output before saying it is "
            "finished. Don't make the operator catch obvious gaps. The result should "
            "leave no open question in their mind. Why: catching gaps yourself is the "
            "difference between a draft and a deliverable."
        ),
    ),
    Entry(
        id="lesson-no-fabricated-data",
        type="lesson",
        title="Never invent report numbers; use live sources and label them",
        confidence="high",
        tags=["data", "integrity", "reporting"],
        body=(
            "Never fabricate metrics in a report. Pull real figures (e.g. "
            "scripts/daily_briefing.py for CX + Meta) and label every source as "
            "CANLI / DEMO / ƏLÇATMAZ. Why: one made-up number poisons trust in the "
            "entire deliverable."
        ),
    ),
    Entry(
        id="pref-reach-for-own-tools",
        type="preference",
        title="Reach for our own tools before generic web search",
        confidence="high",
        tags=["tools", "routing", "workflow"],
        body=(
            "When a request lands in a domain one of our tools owns, use that tool "
            "first: AZ price -> Price Hunter; marketing image -> Social Studio; copy "
            "-> Copy Studio; music/voice -> Audio Studio; influencer -> Influencer "
            "Hunter. Generic WebSearch is the fallback, not the first move."
        ),
    ),
    Entry(
        id="decision-environment-constraints",
        type="decision",
        title="Corporate Win11 constraints: portable installs + hosted APIs",
        confidence="high",
        tags=["environment", "windows", "infra"],
        body=(
            "The corporate Windows 11 machine blocks winget and crashes on native ML "
            "runtimes. Standard approach: portable installs (e.g. vendored Node, "
            "FFmpeg) and hosted/free APIs instead of local model runtimes. Why: "
            "anything needing admin or native compilation tends to fail here."
        ),
    ),
    Entry(
        id="decision-gemini-free-tier-reality",
        type="decision",
        title="Gemini free-tier model choice and retry policy",
        confidence="high",
        tags=["gemini", "llm", "rate-limits", "gateway"],
        body=(
            "On this key, gemini-2.0-flash has 0 free quota (regional) -- do not use "
            "it. The 2.5+ models work; the browser/agent loop uses gemini-2.5-flash "
            "via MODEL_AGENT and falls back across models on 429/503. llm.py retries "
            "transient errors with backoff up to ~65s, which is fine for a background "
            "worker. Why: the free tier is tight and flaky; design for survival."
        ),
    ),
    Entry(
        id="decision-council-codex-default",
        type="decision",
        title="AI Council executes via local CLIs; API fallback is off by default",
        confidence="medium",
        tags=["gateway", "council", "execution", "security"],
        body=(
            "Agent Terminal tasks route through the AI Council using "
            "subscriber-authenticated local CLIs (Codex, Claude Code, Gemini via "
            "OAuth), not API keys. Codex synthesizes the plan and performs final "
            "execution. Legacy API execution only runs if "
            "AI_COUNCIL_ALLOW_API_FALLBACK=1. Why: use the paid-subscription CLIs we "
            "already have rather than burning metered API quota."
        ),
    ),
    Entry(
        id="decision-gateway-security-prime-directive",
        type="decision",
        title="Gateway security prime directive: refuse, checkpoint, audit",
        confidence="high",
        tags=["security", "gateway", "autonomy"],
        body=(
            "Security is the highest law in the autonomous gateway. gateway/security.py "
            "blocks secret exposure, destructive actions and payments before tool use; "
            "browser navigation blocks localhost/private/metadata IPs; studio "
            "automation only runs allowlisted scripts. Irreversible actions "
            "(buy/pay/submit/delete; AZ: al/ödə/sifariş/təsdiq/sil) are refused, not "
            "executed. Every allow/block is logged to data/logs/security_audit.jsonl."
        ),
    ),
    Entry(
        id="pattern-studio-layered-architecture",
        type="pattern",
        title="Studios follow a layered kit -> critique -> output pattern",
        confidence="medium",
        tags=["studios", "architecture", "post"],
        body=(
            "Each creative studio is built from ordered layers. Social Studio: "
            "brand_kit, moodboard, prompt_kit, style_dna, render_post, critique, "
            "output. Copy Studio mirrors it: copy_kit, swipe_file, voice_dna, "
            "critique, output. /post runs the visual and copy tracks in parallel with "
            "--style and --voice flags. Reuse this skeleton for new studios."
        ),
    ),
    Entry(
        id="decision-powershell-51-ascii",
        type="decision",
        title="PowerShell 5.1 launch scripts must be ASCII-only",
        confidence="high",
        tags=["powershell", "windows", "scripts", "hub"],
        body=(
            "The hub's START_MARKETING_OS boot scripts must be ASCII-only .ps1 because "
            "Windows PowerShell 5.1 mishandles non-ASCII/BOM content. Keep emoji and "
            "Azerbaijani characters out of .ps1 files; put them in data, not code."
        ),
    ),
    Entry(
        id="glossary-marketing-os-ports",
        type="glossary",
        title="Marketing OS service ports",
        confidence="high",
        tags=["ports", "hub", "services", "reference"],
        body=(
            "Hub portal 8000; Ads Studio 8800; CX Command Center 8810; Meta CAPI 8811; "
            "Atelier 8820; Price Hunter 8830; Influencer Hunter 8840. The hub unifies "
            "them in one sidebar+iframe UI; START_MARKETING_OS.bat boots everything."
        ),
    ),
    Entry(
        id="decision-brain-markdown-source-of-truth",
        type="decision",
        title="Knowledge Core: markdown is truth, embeddings are only an accelerator",
        confidence="high",
        tags=["brain", "memory", "architecture", "learning"],
        body=(
            "The Knowledge Core stores every learning as a human-readable markdown "
            "file (data/memory/) so nothing is ever locked in a blob and everything is "
            "git-trackable and editable. Embeddings are an optional rerank layer "
            "(BRAIN_EMBEDDINGS=1) that must degrade to keyword search when the free "
            "tier is unavailable. Auto-reflected lessons go to a pending review queue, "
            "never straight into the trusted store. Why: durability and trust beat "
            "cleverness; the free tier is too flaky to depend on."
        ),
    ),
]


def run() -> int:
    for entry in SEED:
        save(entry, rebuild_index=False)
    rebuild_index_file()
    print(f"seeded {len(SEED)} entries into the Knowledge Core")
    return len(SEED)


if __name__ == "__main__":
    run()
