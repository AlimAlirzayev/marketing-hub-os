# Xalq Insurance Digital OS — Gateway (autonomous background runtime)

The piece that turns Xalq Insurance Digital OS into a real **"throw a task, it executes in the
background, you get the result"** agent — like Manus / Hermes / OpenClaw, but
self-hosted, zero-budget, and firewall-safe.

You are NOT meant to babysit it step by step. You submit a task and walk away;
a worker process executes it in the background and delivers the result.

## How it works

```
front-end          queue                worker
---------          -----                ------
submit.py (CLI) ┐                  ┌─> route (orchestrator.router)
bot.py (Telegram)├─> data/jobs.sqlite ─┤   pick LLM tier
                ┘   queued → running    └─> llm.complete (Gemini live)
                        ↓                       ↓
                    done/error  <───────  save artifact (output/jobs/)
                        ↓
                deliver: Telegram reply (or read from DB for CLI)
```

- **Durable queue** (SQLite, WAL): survives restarts; one writer, many readers.
- **No Docker, no langchain/crewai**: light deps only (`google-genai`,
  `requests`, `python-dotenv`) — safe on the locked-down corporate machine.
- **Telegram = long-poll**: outbound HTTPS only, no open port/webhook/public IP.
  Processed update IDs and queue ingress keys are durable, so restart/replay
  cannot create a second agent run. The typed adapter uses an explicit update
  allowlist, bounded transient retries and Telegram's `retry_after`. Long work
  uses one editable progress card; approval becomes owner-bound native buttons,
  with slash-command fallbacks. The existing `gateway.supervisor` is the
  self-healing daemon that keeps bot, worker, scheduler and health loops alive.

## Security prime directive

Security is the highest law. The gateway has a central guard in
`gateway/security.py` and refuses unsafe autonomous actions before tool use.

- Job pre-flight blocks secret exposure, destructive actions, and payments.
- API-key rotation uses the local hidden-prompt courier (`SECURE_KEY.bat KEY_NAME`
  or `python3 scripts/secure_key.py KEY_NAME`). It writes locally, encrypts,
  pushes, verifies upstream, and leaves a private receipt on receiving twins.
  Telegram `/setkey` and `/setfile` are permanently blocked: deletion after
  receipt cannot undo secret transport through chat history.
- Browser navigation blocks localhost, private IPs, metadata IPs, and URLs with
  embedded credentials.
- Studio automation can only run allowlisted scripts; path traversal and unknown
  scripts are refused.
- Every allow/block decision is redacted and appended to
  `data/logs/security_audit.jsonl`.
- External agents and marketplace tools go through Agent Radar before any
  sandbox trial. Agent Radar records benefit, risk, trust, verdict, and required
  controls in `data/agent_radar/candidates.jsonl`.
- Agent permissions are declared in `config/agent_permissions.json` and checked
  with `python -m gateway.permissions doctor`.
- Context7 is available only as a read-only docs grounding layer for external
  library/API work; never send secrets or customer data to docs tools.
- Safety tests live in `tests/test_security.py` and `tests/test_agent_radar.py`
  and can be run with:

```powershell
python -m unittest discover -s tests
```

## Agent Radar

Agent Radar is the intake layer for Moltbook-style agents, plugin marketplaces,
or any outside automation tool. It is deliberately not an execution layer.
Verdicts are `reject`, `quarantine`, `sandbox_review`, and
`approved_for_sandbox`; there is no production approval verdict.

For daily use, prefer the automatic Marketing OS scan. It compares our current
modules with agent-governance patterns like Agent 365, AI Control Tower,
Agentforce, UiPath, and OWASP guidance, then ranks the safest next agent work.

```powershell
python -m gateway.agent_radar autoscan
python -m gateway.agent_radar autoscan-report

# Optional daily Windows task:
.\schedule_agent_radar.ps1

# Manual intake remains available for one-off candidate checks:
python -m gateway.agent_radar add --name "Support Triage Copilot" --use-case "customer support" --permissions network,database_read --evidence "docs,demo"
python -m gateway.agent_radar report
```

## Hugging Face Opportunity Radar

HF Radar is the Hugging Face-specific intake layer for models, Spaces, MCP
servers, agent frameworks, and private RAG/serving options. It turns the Desktop
HF research into a ranked, auditable adoption map.

```powershell
python -m gateway.hf_radar scan
python -m gateway.hf_radar report
python -m gateway.hf_radar doctor
```

The policy is strict: HF Router, public Spaces, and external MCP tools are only
for public or synthetic prompts. Customer data, claims, policies, internal
documents, and private strategy stay on local/self-hosted paths such as TEI,
llama.cpp, vLLM, SGLang, Ollama, or another approved private endpoint.

The private embedding reinforcement lives in `brain.embeddings`. Brain recall
and `gateway.rag` share that adapter, so one safe provider policy covers both
institutional memory and internal-document RAG.

The CX sentiment reinforcement lives in `cx-command-center/sentiment_hf.py` and
follows the same private-first rule: local/private Hugging Face text
classification can add a risk signal, but public hosted endpoints stay out of
customer-message workflows.

## FLORA AI Creative MCP

FLORA is the governed draft-media MCP bridge for premium creative canvas work:
Technique discovery, approved asset upload, thumbnail grids, motion plates, and
localized creative batches. It is registered in `scripts/setup-mcp.ps1` and
checked by `gateway.flora_ai`.

```powershell
.\scripts\setup-mcp.ps1
python -m gateway.flora_ai doctor
python -m gateway.flora_ai report
```

FLORA is draft-only. Do not send secrets, customer data, claims, payment data,
internal policies, or unredacted private strategy. Check generation cost before
batches, and pass all final media through Video Studio QA plus Publisher dry-run
before any post or schedule action.

## Notion Workers

Notion Workers are governed as a Notion Custom Agent helper surface for
read-only screening and draft handoffs. The local worker project lives in
`notion-workers/ramin-os-agent-tools` and is checked by `gateway.notion_workers`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-notion-workers.ps1
python -m gateway.notion_workers doctor
python -m gateway.notion_workers report
```

Login, deploy, worker secrets, OAuth, real sync triggers, and webhook URL
handling require a human checkpoint. See `docs/NOTION_WORKERS.md`.

## Trello Work Board

The Xalq Insurance board is connected through `gateway.trello`. Reading is
limited to the allowlisted `RRlLCaSG` board. Every create, move, edit, due-date,
or comment write is saved as a reviewable plan and requires that exact plan's
approval code. Deletion and member/visibility changes remain blocked.

```powershell
python -m gateway.trello doctor
python -m gateway.trello report
python -m gateway.trello connection-check
python -m gateway.trello snapshot
```

Authorization is a human checkpoint and credentials stay in the local process
environment or approved secret store. `connection-check` is fully headless,
performs no Trello write, and leaves its secret-free status under
`output/trello/`. See `docs/TRELLO_WORK_BOARD.md`.

## Use it today (CLI, no setup)

```powershell
# 1. submit a task (returns instantly)
python -m gateway.submit "research 3 marketing trends for car insurance, with post ideas"

# 2. run the background worker (keep it running; this IS the background agent)
python -m gateway.worker

# 3. read results
python -m gateway.submit --list
python -m gateway.submit --status 1
```

Results are also saved to `output/jobs/job-<id>.md`.

## Turn on Telegram (message it from your phone)

1. In Telegram, message **@BotFather** → `/newbot` → follow prompts.
2. Put the token in `.env`:  `TELEGRAM_BOT_TOKEN=123456:ABC...`
3. Start the one supervised daemon:
   ```powershell
   python -m gateway.supervisor
   ```
   `START_MARKETING_OS.ps1` starts this daemon automatically and its singleton
   lock prevents duplicate Telegram pollers on the same machine.
4. Message your bot any task. Long work gets a live status card, then the
   finished result replaces that temporary progress flow in the chat.

## LLM config

Routing lives in `orchestrator/router.py` (task → tier → provider). Only Gemini
is wired today (free, key live). Override the model per tier in `.env`:

```
MODEL_FREE_BULK=gemini-3.5-flash   # gemini-2.0-flash has 0 free quota on this key
```

Other providers (anthropic/groq/ollama) fall back to Gemini until credentialed.

## Autonomous browser (replaces screenshot-by-screenshot)

When a task names a website or asks to browse (`http`, `.com`, `.az`, "go to",
"sayt"...), the executor runs `agent.run_browser_agent`: a **manual Gemini
function-calling loop** that drives a real headless Chromium (Playwright). The
model decides each step (open → read → follow links), we execute it and feed the
result back, until it writes the final deliverable. No human watches the steps.

- Tools return **text** (titles, visible text, link lists), never screenshots —
  far cheaper and faster. See `tools/browser.py`.
- **Checkpoint:** irreversible clicks (buy/pay/submit/delete, AZ: al/ödə/sifariş/
  təsdiq/sil) are refused and reported, not executed.
- Tasks with fresh-data words but no specific site ("latest", "trend", "research",
  "araşdır") use Gemini's **google_search grounding** (live web, no extra keys).

Why a manual loop instead of the SDK's automatic function calling: AFC runs
tools on a worker thread, but Playwright's sync API is thread-bound
("greenlet: Cannot switch to a different thread"). We run the loop ourselves in
the main thread.

## Free-tier reality (important)

The Gemini free tier is tight and flaky, so the agent is built to survive it:
- `gemini-2.0-flash*` = **0 free quota** on this key (regional). Don't use it.
- `gemini-3.5-flash` = only **5 requests/min** — too low for a multi-step loop.
- The browser loop uses **`gemini-2.5-flash`** (`MODEL_AGENT`) and falls back
  across models on rate-limit/overload.
- `llm.py` retries `429`/`503`/`overloaded` with backoff (up to ~65s) — fine for
  a background worker.
- For heavier/faster autonomy, wire **Groq** (free, 30 rpm) or local **Ollama**.

## Roadmap (next phases)

- [x] **Autonomous browser**: real headless navigation + extraction, with checkpoints.
- [x] **Governed credential acquisition**: a task naming an allowlisted provider
  (e.g. `doit rapidapi`) routes to `gateway/tools/credentials.py`, which delegates
  to the standalone `doit` agent. The gateway browser refuses login/secret flows by
  design, so this is the safe path: allowlist + operator approval
  (`GATEWAY_ALLOW_CREDENTIALS=1`) + a one-time human browser login. Default is a
  checkpoint; the raw key is never returned (only a masked confirmation) — the
  secret lands in `.env`, not in any reply or artifact.
- [ ] **Voice intake**: transcribe Telegram voice notes via `video-studio/transcribe.py`.
- [ ] **Form actions**: fill + submit with an approval/resume checkpoint (currently read/navigate only).
- [ ] **Studios**: dispatch `/post` (social/copy) and video jobs from a task.
- [ ] **Scheduling**: cron-style recurring jobs (e.g. a daily morning digest).
- [ ] **More providers**: wire Groq (free) and local Ollama for private tasks.
```
