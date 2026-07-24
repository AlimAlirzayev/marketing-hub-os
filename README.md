# Xalq Insurance Digital OS — Personal AI Agent Ecosystem

> **4-LLM hybrid + 4-domain agent army** | Zero-budget, full local control.
> Claude + Gemini + Groq + Ollama | Marketing + Business + Developer + Jarvis

## Layout

```
project-root/
├── docker-compose.yml         n8n + Postgres + Redis + Qdrant + OpenWebUI
├── .env                       All API keys (fill from .env.example)
├── n8n/workflows/             280+ free templates, 4 categories
├── jarvis/                    isair/jarvis local voice assistant
├── claude-agents/.claude/     subagents + skills + commands (/post, /publish, /scout)
│   └── capabilities.md        free-first provider cascade (the cost router)
├── mcp-servers/               n8n-mcp, browser-use, filesystem
├── orchestrator/crews/        CrewAI crews (4 domains)
├── social-studio/             brand kits + creative audit for marketing posts
├── atelier/                   marketing cockpit web UI (Creative Lab + Brand Brain)
├── video-studio/              video edit + motion graphics + viral clipper (/clip)
├── audio-studio/              universal music + sfx + voice generator (/sound)
├── publisher/                 auto-publish layer (/publish): Postiz → manual
├── influencer-hunter/         Instagram creator shortlist + evidence scoring
├── brain/                     Knowledge Core: the system's learning loop (recall + reflect)
└── data/                      vector_db, memory (brain entries), logs
```

## Knowledge Core (`brain/`) — the learning loop

So the valuable things we decide, learn, and get right don't evaporate when a
session ends. Every learning is a human-readable markdown file in `data/memory/`
(the source of truth); embeddings are only an optional accelerator on top.

- **Recall** — before every autonomous job, relevant past decisions/lessons are
  injected into the execution prompt (`gateway/executor.py`, `gateway/council.py`).
- **Reflect** — after a job is delivered, an LLM distills reusable lessons into a
  **pending review queue**; a human approves the good ones (no auto-pollution).

```powershell
python -m brain.seed                       # load the durable, hard-won learnings
python -m brain recall "how to build a report PDF"
python -m brain review                     # approve/reject auto-distilled lessons
python -m unittest tests.test_brain        # 12 tests, no network needed
```

See [brain/README.md](brain/README.md). Toggles: `BRAIN_RECALL`, `BRAIN_REFLECT`
(both on by default), `BRAIN_EMBEDDINGS` (off).

## Canonical system context

Ramin-OS changes quickly, so every agent should start from the same live map:

- `AGENTS.md` is the operating charter for Codex, Claude Code, and other agents.
- `docs/USER_VISIBLE_DELIVERY_STANDARD.md` is the mandatory product handoff gate:
  every useful capability must join the unified Hub experience and be proven
  from the user side before it is called complete.
- `CLAUDE.md` is the root Claude Code entry point.
- `docs/RAMIN_OS_CONTEXT.md` is the generated current-state brief.
- `services.json` remains the source of truth for service ports and launch data.

The operator uses one browser entry point: the Hub on port `8000`. Its built-in
sections include **İş masası** (conversation, approvals, results), **Müşahidə**
(live agent/workflow topology), and **Şura** (consultation-only multi-LLM review).
Port `8890` and `/map` remain internal/backward-compatible implementation routes,
not separate products or new front doors.

Refresh the context after any meaningful system-shape change:

```powershell
python scripts\system_context.py
```

## Hugging Face Opportunity Radar

The Desktop HF research is now operationalized as a governed adoption map, not
a loose list of tools. `gateway/hf_radar.py` ranks HF Router, MCP, Spaces,
smolagents/tiny-agents, local open-weight serving, and TEI/RAG by fit, risk,
privacy boundary, and implementation readiness.

```powershell
python -m gateway.hf_radar scan
python -m gateway.hf_radar report
python -m gateway.hf_radar doctor
```

Rule of thumb: hosted HF tools are for public/synthetic PoCs; internal docs,
customer data, claims, and private strategy go through local/self-hosted paths
such as TEI, llama.cpp, vLLM, SGLang, Ollama, or another approved private
endpoint. The Agent Radar dashboard shows the HF opportunity map next to the
agent-governance scan.

The first reinforcement is wired into `brain.embeddings`: Brain recall and the
legacy `gateway.rag` path can use a local/private TEI or OpenAI-compatible
embedding endpoint via `BRAIN_EMBED_PROVIDER` + `BRAIN_EMBED_ENDPOINT`, while
keyword recall remains the default zero-risk fallback.

The second reinforcement is wired into `cx-command-center/sentiment_hf.py`:
Customer Relations Center can use a local/private Hugging Face
text-classification sentiment endpoint as an extra signal. It can raise
complaint risk, but it never weakens deterministic CX rules.

## Context7 docs grounding and agent permissions

Context7 is registered as a read-only MCP documentation layer for current
library/API docs. Use it when changing third-party libraries such as FastAPI,
Streamlit, Playwright, Pydantic, MCP servers, Meta/GA4 SDKs, Qdrant, or HF
serving docs. It is not allowed to receive secrets, customer data, claims,
internal policies, or private strategy.

```powershell
.\scripts\setup-mcp.ps1
python -m gateway.permissions doctor
python -m gateway.permissions report
```

Agent capabilities are governed by `config/agent_permissions.json`. Add or
update a manifest entry before expanding any agent, MCP server, or workflow.
See [docs/CONTEXT7_GROUNDING.md](docs/CONTEXT7_GROUNDING.md).

## Notion Workers

Notion Workers are wired as a governed Notion Custom Agent helper surface, not a
local service. The first worker lives in
`notion-workers/ramin-os-agent-tools` and exposes read-only/draft-only tools for
Ramin-OS action screening and module handoff preparation.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-notion-workers.ps1
python -m gateway.notion_workers doctor
```

Login, deploy, worker secrets, OAuth, real sync triggers, and webhook URLs need
a human checkpoint. See [docs/NOTION_WORKERS.md](docs/NOTION_WORKERS.md).

## Marketing Certification Coach

`certification_coach/` is the governed exam-prep mentor for marketing
certifications. It ranks official-source certification paths, builds a weekly
roadmap, runs a persistent Journey Engine with readiness gates, builds a local
vector knowledge index, stores mock-attempt learner memory, answers grounded
mentor questions, generates original mock questions, and keeps account login,
payment, booking, live exams, and certificate publishing behind human
checkpoints.

```powershell
python -m uvicorn certification_coach.server:app --port 8880
```

The module is registered in `services.json` as `certcoach` and governed by
`config/agent_permissions.json` (`marketing_certification_coach`). It is
strictly a coach; it never takes exams or answers live exam questions.
Runtime knowledge state lives under `data/certification_coach/` and is
regenerable/local.

## Safe API-key rotation

Never paste API keys into chat or Telegram. Use `SECURE_KEY.bat KEY_NAME` on
Windows or `python3 scripts/secure_key.py KEY_NAME` on macOS/Linux. The hidden
local prompt writes the key locally, encrypts it for the twins, verifies upstream
delivery, and every sync re-applies the vault. See `docs/SYNC.md`.

## Setup order

### Step 1: Install Docker Desktop
- https://www.docker.com/products/docker-desktop/
- Make sure WSL2 backend is enabled

### Step 2: Prepare .env
```powershell
Copy-Item .env.example .env
# Edit .env and fill in your keys
```

### Step 3: Start services
```powershell
docker compose up -d
```

Endpoints:
- n8n:       http://localhost:5678
- OpenWebUI: http://localhost:3000
- Qdrant:    http://localhost:6333/dashboard
- Postiz:    http://localhost:5000   (auto-publish; `docker compose up -d postiz`)

### Step 4: Import workflow templates
```powershell
.\scripts\import-templates.ps1
```

### Step 5: Install Ollama (local LLM)
```powershell
# Download: https://ollama.com/download/windows
ollama pull gemma3:4b
ollama pull qwen2.5:7b
```

### Step 6: Install Jarvis
```powershell
# Download Windows release from:
# https://github.com/isair/jarvis/releases
# Extract into project-root/jarvis/
```

### Step 7: Install Claude Code agents & skills
```powershell
.\scripts\install-agents.ps1
.\scripts\setup-mcp.ps1
```

### Step 8: Orchestrator (Python crews)
```powershell
cd orchestrator
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 9: Video Studio (marketing video edit + motion graphics)
```powershell
# Portable Node.js + FFmpeg (winget blocked by Group Policy)
.\scripts\install-video-tools.ps1
pip install -r video-studio\requirements.txt
```
Then, in Claude Code: `/edit-video input/raw.mp4 <brief>`.
See [video-studio/README.md](video-studio/README.md).

### Step 9.1: Audio Studio (universal music + sfx + voice)
```powershell
pip install -r audio-studio\requirements.txt
python audio-studio\audio_studio.py doctor
```
Free Azerbaijani voice-over works immediately (Edge TTS). For music/sfx add a free
ElevenLabs key (10k cr/mo) to `.env` and re-run `scripts\setup-mcp.ps1`. Then use
`/sound music|sfx|tts "<prompt>"`. See [audio-studio/README.md](audio-studio/README.md).

### Step 10: Customer Relations Center
```powershell
cd cx-command-center
.\run.ps1
```
Then open `http://127.0.0.1:8810`.

### Step 10.1: Click-to-open local panels
Use the Desktop shortcuts, or run these files directly:

```powershell
.\Xalq_Insurance_Digital_OS_Ac.bat
.\Xalq_Insurance_Digital_OS_Bagla.bat
```

Agent Terminal tasks are routed through the AI Council by default.
The council uses subscriber-authenticated local CLIs instead of API keys:
Codex CLI, Claude Code CLI, and Gemini CLI via Google OAuth / Code Assist.
Codex synthesizes the joint plan, then Codex CLI performs the final execution.
Legacy API execution is disabled by default and only runs if
`AI_COUNCIL_ALLOW_API_FALLBACK=1`.
Configure it from `.env` with `AI_COUNCIL_ENABLED`,
`AI_COUNCIL_AUTO_EXECUTE`, `AI_COUNCIL_TIMEOUT_SECONDS`, and
`AI_COUNCIL_GEMINI_TIMEOUT_SECONDS`.

### Atelier — Creative Lab + Brand Brain
Atelier (brand-DNA 11-layer prompts + AI vision critique + A/B board) runs as
its own registered service — **Kreativ Studiya**, `http://localhost:8820` —
embedded in the hub like every other studio (`cd atelier; .\run.ps1` or the
START launcher). The old Streamlit `creative_studio.py` tab was retired with
the 8501 monolith (2026-07-13). See [atelier/README.md](atelier/README.md).

### Influencer Hunter — Creator Intelligence
Influencer Hunter is now part of the OS as a FastAPI panel on
`http://localhost:8840`. It takes a campaign brief, searches Instagram creator
evidence through Apify actors, scores candidates on a 0-10 rubric, and returns a
top shortlist with proof links, Reels/post metrics, feedback sentiment and
brand-safety notes.

```powershell
influencer-hunter\run.bat
```

Live Instagram depth needs `APIFY_API_TOKEN`; the actor names are configurable
with `IH_INSTAGRAM_*_ACTOR` variables in `.env`. See
[influencer-hunter/README.md](influencer-hunter/README.md).

## Free LLM API keys

| Provider | URL | Free tier |
|---|---|---|
| Google Gemini 2.0 Flash | https://aistudio.google.com/apikey | 1500 req/day |
| Groq (Llama 3.3 70B)    | https://console.groq.com/keys      | 30 req/min |
| Ollama (local)          | No key needed                       | Unlimited |
| Hugging Face            | https://hf.co/settings/tokens       | Free inference |

## Status

### Skeleton (scaffolding complete)

- [x] Directory layout
- [x] docker-compose.yml
- [x] .env.example
- [x] Scripts skeleton (import-templates, install-agents, install-ollama-models, install-jarvis, setup-mcp, bootstrap)
- [x] claude-agents scaffold (CLAUDE.md, .claude/settings.json, commands)
- [x] Orchestrator scaffold (router.py, 3 crews + jarvis_bridge, requirements.txt)
- [x] Jarvis / mcp-servers / n8n / data folder stubs
- [x] Repo hygiene (.gitignore, .dockerignore)
- [x] Video Studio (render pipeline, Remotion project, /edit-video) — working module
- [x] Social Studio (Xalq Sigorta brand kit + Creative Audit gate)

### Execution (your turn)

- [ ] Start services (`docker compose up -d`)
- [ ] Import workflow templates
- [ ] Install Ollama models
- [ ] Install Jarvis
- [ ] Install Claude Code agents & skills
- [ ] Run orchestrator crews
- [ ] Install Video Studio tools (`scripts\install-video-tools.ps1`)

> Tip: `.\scripts\bootstrap.ps1` runs the install steps in order.
