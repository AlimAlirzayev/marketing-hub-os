# Xalq Insurance Digital OS - Orchestrator

> **Note (2026-06-24):** `router.py` is live (used by `gateway/executor.py`). The
> **`crews/` CrewAI skeletons are DEPRECATED** — the live multi-agent layer is
> `gateway/council.py` (a zero-budget subscriber-CLI council). See
> [`crews/DEPRECATED.md`](crews/DEPRECATED.md). Don't build new work on the crews.

The Python control layer that routes tasks across the 4-LLM hybrid (Claude,
Gemini, Groq, Ollama) via `router.py`.

## Layout

```
orchestrator/
├── requirements.txt        Python dependencies
├── .env.example            Copy to .env and fill in
├── router.py               LLM tier router (task -> provider/model)
├── README.md               This file
└── crews/
    ├── __init__.py
    ├── marketing_crew.py    6 agents
    ├── business_crew.py     5 agents
    ├── developer_crew.py    6 agents
    └── jarvis_bridge.py     Voice-intent -> crew dispatcher
```

## Setup

```powershell
cd orchestrator
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Edit .env: add ANTHROPIC_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY
```

## Running

The crews are currently skeletons. `router.get_llm` and the `crew.kickoff()`
calls are stubbed and marked `TODO` - wire the real provider clients before
running in production.

Smoke tests (no LLM calls, just construction):

```powershell
python router.py                       # prints routing decisions
python -m crews.marketing_crew         # builds the marketing crew
python -m crews.business_crew          # builds the business crew
python -m crews.developer_crew         # builds the developer crew
python -m crews.jarvis_bridge          # dispatches a demo voice intent
```

Run `crews` modules with `python -m crews.<name>` from the `orchestrator/`
directory so the `crews` package resolves correctly.

## LLM routing

`router.py` classifies a task into one of four tiers and resolves it to a model:

| Tier        | Provider | Used for                                  |
|-------------|----------|-------------------------------------------|
| `complex`   | Claude   | code, architecture, nuanced copy          |
| `fast`      | Groq     | classification, triage, quick decisions   |
| `free_bulk` | Gemini   | scraping, research, high-volume work      |
| `private`   | Ollama   | sensitive data that must stay on-device   |

Each agent in a crew declares its preferred tier in the module-level
`AGENT_TIERS` dict.
