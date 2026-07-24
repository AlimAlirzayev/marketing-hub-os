# Orchestration Map — who plans, who executes, who reviews, where results go

This is the single coordination picture for the Xalq Insurance Digital OS agent
system. It exists to remove one specific confusion: *which agent talks to whom,
from where, who gets which task, and how the result comes back.* If you only read
one file to understand "how the agents work together," read this one.

> **Current authority (supersedes older Council descriptions below):** Since
> 2026-07-20, the production operational path is the Claude conversational brain
> acting as the model-as-router. For heavy multi-studio work it calls
> `gateway.summon`, which asynchronously enters the explicit `/crew` rail and
> runs the isolated production CrewAI workforce in `gateway/studio_crew.py`.
> Studio workers gather live data and Claude synthesizes the operator-facing
> result. `gateway/council.py` remains an explicit-only legacy subscriber-CLI
> consultation tool; it is not the default manager or operational workforce and
> must not be re-enabled or substituted when the operator means the current
> Crew/manager architecture. `orchestrator/crews/` remains obsolete skeleton
> code. The newest `memory/decisions.jsonl` entries and live executor code win
> over stale prose elsewhere in this document.

It does not introduce new machinery. It draws the machinery we already have
(`gateway`, `orchestrator`, `brain`, the CLIs) as one map, and states the rules
that decide where a task goes.

---

## 0. One microphone (the single input rule)

The system is **one entity reached through many microphones**: this Claude Code
chat, Telegram, Codex, the control panel. To stop input fragmenting into per-
channel islands, every channel speaks through one front door — `gateway/mic.py`:

```
chat / Telegram / Codex / panel  ──▶  mic.speak(text, source=…)
                                         │  (one FIFO queue = turn-taking)
                                         ▼
                                   gateway.worker ─▶ executor
                                         │  reads MIC_THREAD history
                                         ▼
                          one continuous conversation + memory
```

- **One conversation thread** (`mic.MIC_THREAD = "main"`): the brain answers with
  the full cross-channel history, so "today you here, tomorrow Telegram, next
  Codex" is literally one continuous conversation — each source just takes the
  mic in its turn. The worker records every turn under this thread, tagged with
  its source.
- **One serialized queue**: the durable job queue (single worker, oldest-first)
  IS the turn-taking — whoever speaks now holds the mic; the next waits.
- **Conversational by default, not a council.** The default path is a single
  strong brain with the shared history + the `_CHAT_SYSTEM` persona, so Telegram
  feels like talking to the operator's teammate here — not a terse multi-CLI
  vote. The council is now **opt-in** (`AI_COUNCIL_ENABLED=1`) for deliberate
  runs only.
- The conversation lives in the per-deployment blackboard (git-ignored), so it
  **never travels** between the two friend-systems — only the ENGINE does. Each
  system keeps its own single microphone.

---

## 1. Two planes (the core mental model)

The system has **two distinct planes**. Most of the past confusion came from
mixing them. Keep them separate.

### Plane A — Control plane (interactive coding harnesses, human in the loop)

These are the IDE/terminal agents *you* drive directly to build and change the OS
itself. They are the "developers."

| Harness | Brain | Role | Cost tier | When |
| --- | --- | --- | --- | --- |
| **Claude Code** (this) | Opus 4.8 | Architect / hard reasoning / final review | 20% premium | Design, tricky logic, last review, anything risky |
| **OpenCode** | free Gemini 2.5-flash (1M ctx) | Bulk builder / refactors / scaffolds / model A-B | 80% free | Token-heavy grunt work, offline (Ollama), model tests |
| **Codex CLI** | subscriber CLI | Repo-discipline engineer | subscription (no API $) | Implementation discipline, repo-wide edits |

These harnesses share a cold-start blackboard through
`scripts/builder_context.py`. After the engine pull, it combines masked live
state, the newest shared decisions, and curated Claude/Codex memory indexes into
the machine-local `data/builder_context.md`. Claude receives it through its
SessionStart hook; other builders run the same command from `AGENTS.md`.
Agent-private memory remains a hint, never a competing authority.

> **Why OpenCode runs on Gemini, not Groq:** OpenCode sends ~42k tokens of system
> prompt + AGENTS.md per turn. Groq free tier caps at 12k tokens/minute → rejected.
> Gemini free (1M context) handles it. Groq stays for single-shot `llm_router`
> calls. See [`OPENCODE.md`](OPENCODE.md).

### Plane B — Runtime plane (the autonomous OS executes tasks by itself)

This is the always-on engine that takes a queued task (from Telegram, the hub, a
schedule) and produces a deliverable **without a human at the keyboard**.

```
task in  ──▶  gateway.queue  ──▶  gateway.supervisor (always-on worker)
                                        │
                                        ▼
                              gateway.executor  ──────────────┐
                                        │                     │
              ┌─────────────────────────┼─────────────┐       │
              ▼                          ▼             ▼       ▼
     orchestrator.router        gateway.council   gateway   brain (recall)
     (classify → tier)          (multi-CLI advice  .llm      inject past
              │                  + synthesis)      │         lessons first
              ▼                          │         ▼
        llm_router.py  ◀─────────────────┴───  one OpenAI-compatible
        (LiteLLM free-first cascade + fallback + usage log)
              │
              ▼
   deliverable ──▶ output/jobs/*.md  ──▶  brain (reflect → review queue)
                                      └──▶ Telegram / hub report
```

**The two planes meet in one place:** both ultimately call models through
`llm_router.py`. That is the single chokepoint for cost, fallback, and logging.

**The human checkpoint (approval rail).** Before executing, every job passes
`security.evaluate_task` (hard blocks: secret exfil, destruction, payments) and
then `security.evaluate_checkpoint` (outward actions: publish/send/call/deploy,
AZ paylaş/göndər/yayımla/zəng). An unapproved outward job **parks** as
`awaiting_approval` and the operator decides — Telegram `/approve N` · `/reject N`
(owner-only) or one click in the control panel. Approval re-queues it with
`approved=1`, which passes the checkpoint. Drafting ("3 post ideyası yaz") never
parks; only acting does.

**The operator's screen** is the Ramin-OS Hub (port 8000), the sole advertised
front door. `gateway/panel.py` remains the registered internal backend on port
8890 and renders inside the Hub as **İş masası**: shared conversation, job/result
previews, approvals, finance, trends and engine state. `gateway.commandcenter`
feeds the Hub's **Müşahidə** view through `/api/flow`; legacy `/map` remains only
for backward compatibility. The Hub's **Şura** view uses
`gateway/council_workspace.py` to collect independent CLI opinions and synthesize
them without calling the legacy auto-execution path. Consultation and execution
are separate operator decisions.

---

## 2. The model gateway — one door for every model call

`llm_router.py` (LiteLLM-backed) is the **only** place model selection should
happen at runtime. Everything funnels through it so we get free-first routing,
automatic fallback, and one usage ledger.

- **Free-first cascade:** Gemini Flash → Groq → Cerebras → OpenRouter → DeepSeek
  → local Ollama. First available wins; on error it falls through.
- **Tiers:** `cheap` (default, bulk) vs `smart` (harder reasoning, still free-first).
- **Grounding exception:** web-search/grounded calls stay Gemini-direct in
  `gateway/llm.py` (LiteLLM can't pass Google grounding through cleanly).
- **Observability:** every successful call and every failed provider attempt is
  appended to `data/logs/llm_usage.jsonl` with model/tier/status, safe error
  taxonomy and latency (never prompts, responses or secrets).

The worker boundary validates every executor return through the strict Pydantic
`gateway.contracts.ExecutionOutcome` contract (`success | partial | failure |
needs_approval`, extra fields forbidden). A provider failure is therefore an
`error` job, is shown honestly in İş masası, and is excluded from conversation
memory, reflection and skill reinforcement. Queue completion/failure is
compare-and-set from `running`, preventing a late worker from overwriting a
terminal state.

Corporate RAG is deliberately local/private by default. Hosted Gemini embeddings
are blocked unless `BRAIN_EMBED_ALLOW_EXTERNAL=1` is explicitly approved; absent
an approved embedding provider the UI/API reports the capability unavailable
instead of silently exporting internal text or pretending retrieval succeeded.

Already wired through the router — verified 2026-06-25, **every plain text
completion in the system**: `gateway/llm.py`, `gateway/executor.py` (default +
research paths), `video-studio/clipper.py`, `scripts/yt_digest.py`,
`ads-studio/analytics/ai.py`, `brain/capture.py` (reflect), `atelier/llm.py`,
`price-hunter/llm.py`, `influencer-hunter/llm.py`, `cx-command-center/triage.py`.
Each tries the router first, then a direct-provider fallback (identical behavior,
better instrumented).

The only model calls that stay **direct do so by design, not as a gap** — the
router is text-completion only and pushing these through it would lose capability:
- **Native tool-calling / function-use:** `gateway/agent.py` (browser agent),
  `gateway/executor.py` `tools` mode (Gemini function-calling loop).
- **Grounded web-search:** `gateway/llm.py` keeps Gemini-direct (Google grounding
  can't pass through LiteLLM cleanly).
- **Non-text generation:** image (`atelier/imagegen.py`, `visual_studio.py`,
  `social-studio/.../run_nano_banana.py`), audio/TTS (`audio-studio/...`,
  `app.py`), embeddings (`brain/embeddings.py`, `gateway/rag.py`).

---

## 3. Current manager/Crew authority and the separate consultation surface

The operational workforce is `Claude brain/model-as-router → gateway.summon →
explicit /crew → gateway.studio_crew (production CrewAI) → live studios →
Claude synthesis`. This is the only current manager/Crew route. It passes work
to the existing studios and returns one synthesized result through the normal
job, approval, artifact and memory rails.

`gateway/council_workspace.py` powers the Hub's visual Şura as a
**consultation-only** workspace: independent Codex, Claude and Gemini notes,
per-member readiness/failure truth, history, then an optional synthesis. It does
not execute the proposed work. `gateway/council.py` is the older explicit-only
subscriber-CLI consultation rail; it is not the operational manager, is never
auto-enabled, and must not replace or reconfigure the current Crew path.

The consultation sequence is:

1. **Consult (parallel):** Codex, Claude Code, and Gemini CLI each return an
   independent note on the task — intent, plan, risks, next action. Each runs in
   its own process with a hard timeout, killed as a tree on Windows so one stuck
   provider never hangs the round.
2. **Synthesize (chair):** one CLI (Codex → Claude → Gemini fallback) merges the
   notes into one decision + execution plan + next action, grounded only in the
   notes and real workspace files (no invented data).
3. **Decide:** the operator may separately send an accepted direction into the
   normal mic/router/Crew execution path.

> **Council quality = model *diversity*, not member count.** The three voices are
> three distinct model families (Codex/GPT, Claude, Gemini) so they catch
> different things. OpenCode is deliberately **not** a 4th member by default: the
> only free model it can reliably run is Gemini (Groq's TPM is too small for its
> context), and a second Gemini-backed voice is redundant — correlated opinions +
> extra latency, no new signal. OpenCode joins the panel **only** when configured
> with a *distinct* free model family (deepseek/qwen via OpenRouter →
> `OPENCODE_COUNCIL_MODEL`, or force with `AI_COUNCIL_OPENCODE=1`). Its real role
> is the free **executor**, below — not padding the advice panel.

Auth discipline: council members use **subscriber CLIs / free keys**, never
silent API billing. `_base_env()` strips paid API keys before each member runs.

This separation prevents advice from silently becoming an action and prevents a
legacy consultation file from being mistaken for the live manager architecture.

---

## 4. Routing rules — who gets which task

| Task shape | Goes to | Why |
| --- | --- | --- |
| Design / architecture / risky / final review | **Claude Code** (you, 20%) | Best reasoning; human checkpoint |
| Bulk edits, scaffolds, refactors, model A-B, offline | **OpenCode** (free) | Cheap tokens, model freedom |
| Repo-wide implementation discipline | **Codex CLI** | Strong executor in this workspace |
| "Which is the strongest answer?" hard call | **Visual Şura** (`council_workspace`, consult + synth) | Diverse advice, no auto-execution |
| A queued autonomous job (Telegram/hub/schedule) | **gateway.executor** | Background, no human |
| Any raw model completion inside code | **`llm_router.complete()`** | Free-first + fallback + log |
| AZ price / image / video / audio / publish | the owning **studio** first | Reach for our own tools, not generic calls |
| Strategy/plan/proposal deliverable (plain path) | **specialist fan-out** (`gateway.executor._fanout_deliver`) | 3 cheap specialist passes in parallel (marketing / product / analyst, strict-JSON) + one bundler beat one generalist pass; falls back to `_converse` on any failure |
| Social-post ask (plain path) | **structured content lane** (`gateway.executor._content_deliver`) | Brand-voiced schema JSON (compose_for_brief-shaped) + human preview + `output/jobs/job-N-post.json` artifact, so a text post can become a rendered brand post without re-prompting; falls back to `_converse` |

Decision discipline: **task difficulty routing is human-decided, not magic.**
No tool auto-escalates to a paid model. We choose the plane; the router chooses
the free model inside it.

---

## 5. Where results and memory live (so nothing is lost)

| What | Where | Lifetime |
| --- | --- | --- |
| Finished job deliverables | `output/jobs/*.md` | persistent (git) |
| Model usage / cost ledger | `data/logs/llm_usage.jsonl` | rolling |
| Institutional memory (lessons) | `brain/` markdown | persistent, recalled before each job (per-machine) |
| **Shared memory (travels via git)** | `memory/` + `shared_memory.py` | the L4 blackboard read first by every session/channel/machine |
| Pending lessons to review | brain reflect → review queue | until accepted |
| Visual Şura consultation notes | council workspace history | persistent consultation record |
| Live system snapshot | `python scripts/system_context.py` | regenerated on shape change |

**The learning loop is mandatory:** before a job, `brain` *recalls* relevant past
lessons; after a job, it *reflects* the outcome into a pending queue. Durable
takeaways are also written to `claude-agents/.claude/capabilities.md` and to the
Claude memory store. A session's insight must never die in chat.

---

## 6. Autonomous spine — LangGraph on top of llm_router (PoC)

`orchestrator/graph.py` is the durable, interruptible agent spine. The 2026-honest
choice: keep the lean **LiteLLM** gateway (`llm_router`) for model calls; use
**LangGraph only** for the part it is genuinely best at — *stateful, resumable,
human-gated* orchestration. (We do **not** rewrite the working router/council into
LangChain LCEL — that abstraction churn is what teams are migrating off.)

The graph: `intake → plan → [risk gate] → (risky) human checkpoint → execute → remember`

- **Checkpointer (SqliteSaver):** every step persists; a run survives crash/restart
  and resumes — the durability token-bound chat sessions lack.
- **`interrupt()`:** before any risky action (post/send/pay/delete/call) the graph
  pauses for human approval, then resumes with `Command(resume="approve")` — this is
  AGENTS.md's "risky actions need checkpoints," enforced in the runtime.
- **Free brain:** planning + execution think through `llm_router` (free models);
  LangGraph only orchestrates.

Verified end-to-end: a safe task runs straight through; a risky task pauses at the
checkpoint and completes only after approval. This is the foundation the autonomous
layer (multi-channel control center + shared memory) builds on. Deps:
`langgraph`, `langgraph-checkpoint-sqlite` (in `orchestrator/requirements.txt`).

## 7. One-line summary

> **Control plane** = the coding agents you drive (Claude = 20% hard, OpenCode =
> 80% free, Codex = discipline). **Runtime plane** = the gateway that runs queued
> tasks by itself. **Both** call models only through `llm_router` (free-first +
> fallback + log). Hard calls may go to the consultation-only **Visual Şura**. Results land in
> `output/jobs`, lessons land in `brain`. No tool spends money without us choosing
> the premium plane on purpose.

Related: [`OPENCODE.md`](OPENCODE.md) ·
[`../claude-agents/.claude/capabilities.md`](../claude-agents/.claude/capabilities.md) ·
[`RAMIN_OS_CONTEXT.md`](RAMIN_OS_CONTEXT.md) · [`../AGENTS.md`](../AGENTS.md)
