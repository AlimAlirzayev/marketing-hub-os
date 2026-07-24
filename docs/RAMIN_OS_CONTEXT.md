# RAMIN OS System Context

Generated UTC: 2026-07-24T06:30:15Z

## Mission

Ramin-OS is the unified Xalq Insurance Digital / Marketing OS. Every Codex, Claude Code,
Gemini, automation, script, and module change must improve this one system, not create
a disconnected side project.

## Prime Directives

- Security is the highest law. Prefer a blocked action over an unsafe action.
- Never read, print, copy, upload, or summarize `.env`, `.env.bak`, tokens, cookies, or secrets.
- `services.json` is the single source of truth for service ports and launch metadata.
- Before major work, understand the current system state, relevant module README, and security rules.
- Do not hardcode service lists when the registry can be read.
- Any risky write, send, payment, posting, deletion, or credentialed action needs a checkpoint.
- Keep changes useful to Ramin-OS as a whole: hub, gateway, brain, modules, docs, and tests should stay aligned.

## Current Service Registry

- Port range: [8000, 8999]

| Key | Name | Port | Category | Launch | Target | Health |
|---|---|---:|---|---|---|---|
| hub | Marketing OS Hub | 8000 | Sistem | uvicorn | app:app | /api/status |
| ads | Hesabatlılıq | 8800 | Analitika & Reklam | uvicorn | app:app | /api/health |
| capi | Konversiyalar | 8811 | Analitika & Reklam | uvicorn | web:app | /api/health |
| capi-gw | CAPI Gateway | 8812 | Analitika & Reklam | uvicorn | gateway:app | /healthz |
| ga4 | Vebsayt Analitikası | 8850 | Analitika & Reklam | uvicorn | app:app | /api/health |
| influencer | Influencer Hunter | 8840 | Kəşfiyyat | uvicorn | server:app | /api/health |
| cx | Müştəri Münasibətləri | 8810 | Müştəri | uvicorn | app:app | /api/health |
| atelier | Kreativ Studiya | 8820 | Kontent | uvicorn | atelier.app:app | /api/health |
| price | Qiymət Kəşfiyyatı | 8830 | Kəşfiyyat | uvicorn | server:app | /api/health |
| seo | SEO Studiyası | 8860 | Kontent | uvicorn | seo.server:app | /api/health |
| media_studio | Media Studio | 8870 | Kontent | uvicorn | media_studio.server:app | /api/health |
| certcoach | Sertifikat Mentoru | 8880 | Təlim | uvicorn | certification_coach.server:app | /api/health |
| panel | İş masası | 8890 | İş masası | uvicorn | gateway.panel:app | /api/health |
| rag | Bilik Bazası | 8895 | İş masası | uvicorn | gateway.rag_server:app | /api/health |
| mediagen | Media Generatoru | 8765 | Kontent | uvicorn | mediagen.server:app | /api/health |

## Capability Map

| Capability | Path | Present | Role |
|---|---|---|---|
| Hub / front door | `hub` | yes | Unified Marketing OS entry point, service cards, and port-less capability cards. |
| Service registry | `services.json` | yes | Single source of truth for ports, launchers, capabilities, and hub visibility. |
| Service drift audit | `audit_services.py` | yes | Compares services.json with real listening ports and missing dirs. |
| Security Guard | `gateway/security.py` | yes | Blocks secrets, destructive actions, payments, unsafe URLs, and unknown scripts. |
| Autonomous gateway | `gateway` | yes | Queue, worker, executor, browser tools, AI Council, Telegram delivery path. |
| Knowledge Core | `brain` | yes | Recall and reflect loop with optional private TEI/OpenAI-compatible embeddings. |
| Builder Context Bridge | `scripts/builder_context.py` | yes | Common cold-start card for Codex, Claude Code, Gemini, OpenCode, Copilot, and future governed builders. |
| Bilik Bazası (RAG) | `gateway/rag_server.py` | yes | Corporate knowledge base service: vector search plus source-grounded free-first answers. |
| Daily briefing | `scripts/daily_briefing.py` | yes | Executive CX + Meta + GA4 briefing; served at ads-studio /briefing. |
| Agent Radar | `gateway/agent_radar.py` | yes | Agent governance, sandbox scoring, and automatic Marketing OS scan. |
| Public Signal Radar | `gateway/signal_radar.py` | yes | Read-only public signal intake that source-checks trends into lab notes, prototype backlog, and reports. |
| Agent Permission Manifest | `config/agent_permissions.json` | yes | Fail-closed capability boundaries for internal agents and MCP workflows. |
| Context7 Docs Grounding | `docs/CONTEXT7_GROUNDING.md` | yes | Read-only current documentation layer for external library/API work. |
| Hugging Face Opportunity Radar | `gateway/hf_radar.py` | yes | Governed HF model, MCP, Spaces, and private RAG opportunity scoring. |
| FLORA AI Creative MCP | `gateway/flora_ai.py` | yes | Governed draft-media MCP bridge for FLORA Techniques, assets, and creative generation. |
| Notion Workers | `gateway/notion_workers.py` | yes | Governed Notion Custom Agent tools for draft handoffs and action risk screening. |
| Trello Work Board | `gateway/trello.py` | yes | Allowlisted Xalq Insurance board connector with read snapshots and exact-plan approval for writes. |
| Marketing Certification Coach | `certification_coach` | yes | Ethical certification mentor with source-linked roadmaps, persistent Journey Engine, readiness gates, local vector knowledge index, learner memory, original mock tests, RAG answers, proof tasks, and approval checkpoints. |
| CX Command Center | `cx-command-center` | yes | Customer complaint radar, AI triage, optional private HF sentiment, SLA, and draft-only resolution planning. |
| Ads Studio | `ads-studio` | yes | Meta ads performance reporting and campaign analytics. |
| Conversions API | `meta-capi` | yes | CRM to Meta CAPI and pixel/CAPI gateway. |
| GA4 Studio | `ga4-studio` | yes | Website analytics, sessions, conversion and funnel view. |
| Influencer Hunter | `influencer-hunter` | yes | Creator shortlist, evidence scoring, brand-safety notes, YouTube proof of concept. |
| Price Hunter | `price-hunter` | yes | Competitor pricing and market anomaly monitoring. |
| Creative Studio / Atelier | `atelier` | yes | Brand brain, creative lab, critique, prompt and image workflow. |
| Copy Studio | `copy-studio` | yes | Voice DNA, copy kits, captions, and critique. |
| Publisher | `publisher` | yes | Publish package planning and Postiz/manual routing. |
| Audio Studio | `audio-studio` | yes | Music, SFX, TTS, voice references, and audio generation workflows. |
| Video Studio | `video-studio` | yes | Video editing, Remotion, motion graphics, and clip pipeline. |
| Media Studio / AI UGC Pack | `media_studio` | yes | Directed FLORA video packages plus draft-only AI UGC persona, script, voice, economics, QA, safe resource readiness, browser-run checkpoints, and dry-run handoff. |
| Claude Code control plane | `claude-agents` | yes | Claude subagents, MCP setup, slash command conventions. |

## Agent Governance State

- Best variant: Agent Governance Control Plane, not an open agent marketplace.
- Overall rating: 88/100
- Current recommendation: Agent Governance Control Plane
- Decision: reinforce_current_module
- Phase: P0 - reinforce now
- Automatic job: Daily agent-risk and opportunity scan with a board-level summary.

## Hugging Face Model Governance State

- Best HF path: Private RAG first, HF discovery second, hosted inference last.
- Overall rating: 91/100
- Current recommendation: Private RAG Embedding Layer (TEI + HF embedding models)
- Decision: pilot_now_private_path
- Risk: 24/100

## Operating Loop For AI Agents

1. Read `AGENTS.md`, this file, `SECURITY.md`, and `services.json` before broad changes.
2. Locate the relevant module and its README before editing.
3. Prefer existing patterns and registries over new parallel structures.
4. Make a narrow, testable change; avoid unrelated refactors.
5. Run the smallest meaningful tests, plus wider tests when shared contracts change.
6. Update this context with `python scripts/system_context.py` when the system shape changes.
7. Capture durable lessons through the Brain workflow when a decision should survive the session.

## Useful Commands

```powershell
python scripts/system_context.py
python audit_services.py
python -m gateway.agent_radar autoscan-report
python -m gateway.hf_radar report
python -m gateway.permissions doctor
.\scripts\setup-mcp.ps1
python -m unittest discover -s tests
.\START_MARKETING_OS.ps1
.\STOP_MARKETING_OS.ps1
```

## Coordination Note

Codex work, Claude Code work, and generated automation are all part of the same Ramin-OS
improvement stream. Treat prior work as system context unless it is proven obsolete, and
do not undo another agent's changes without understanding why they were made.
