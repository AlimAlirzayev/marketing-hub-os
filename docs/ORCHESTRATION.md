# Orchestration Map — who plans, who executes, who reviews, where results go

This is the single coordination picture for the Xalq Insurance Digital OS agent
system. It exists to remove one specific confusion: *which agent talks to whom,
from where, who gets which task, and how the result comes back.* If you only read
one file to understand "how the agents work together," read this one.

It does not introduce new machinery. It draws the machinery we already have
(`gateway`, `orchestrator`, `brain`, the CLIs) as one map, and states the rules
that decide where a task goes.

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

**The operator's screen** is `gateway/panel.py` — **İdarəetmə Mərkəzi** (port
8890, registered in `services.json`, embedded in the hub): live pulse, advisor
findings, job queue + result previews, pending approvals with Approve/Reject,
task submission into the queue, one-click engine sync. Renders with zero LLM
tokens — it only reads the gateway's own state.

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
- **Observability:** every call is appended to `data/logs/llm_usage.jsonl`
  (`python llm_router.py --usage` for the daily ledger).

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

## 3. The AI Council — plan / build / review as one synchronous round

`gateway/council.py` is our realized "multi-agent orchestrator" (what Grok called
Planner/Executor/Reviewer). It already does the hard part:

1. **Consult (parallel):** Codex, Claude Code, and Gemini CLI each return an
   independent note on the task — intent, plan, risks, next action. Each runs in
   its own process with a hard timeout, killed as a tree on Windows so one stuck
   provider never hangs the round.
2. **Synthesize (chair):** one CLI (Codex → Claude → Gemini fallback) merges the
   notes into one decision + execution plan + next action, grounded only in the
   notes and real workspace files (no invented data).
3. **Execute:** the normal `gateway.executor` performs the final task.

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

This is why we do **not** build a second parallel orchestrator: the council *is*
the orchestrator. New agents join it as members, per `AGENTS.md` ("do not create
disconnected side tools when an existing module can be reinforced").

---

## 4. Routing rules — who gets which task

| Task shape | Goes to | Why |
| --- | --- | --- |
| Design / architecture / risky / final review | **Claude Code** (you, 20%) | Best reasoning; human checkpoint |
| Bulk edits, scaffolds, refactors, model A-B, offline | **OpenCode** (free) | Cheap tokens, model freedom |
| Repo-wide implementation discipline | **Codex CLI** | Strong executor in this workspace |
| "Which is the strongest answer?" hard call | **Council** (`consult` + synth) | Many models > one |
| A queued autonomous job (Telegram/hub/schedule) | **gateway.executor** | Background, no human |
| Any raw model completion inside code | **`llm_router.complete()`** | Free-first + fallback + log |
| AZ price / image / video / audio / publish | the owning **studio** first | Reach for our own tools, not generic calls |

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
| Council runtime notes | temp runtime dir | ephemeral |
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
> fallback + log). Hard calls go to the **Council**. Results land in
> `output/jobs`, lessons land in `brain`. No tool spends money without us choosing
> the premium plane on purpose.

Related: [`OPENCODE.md`](OPENCODE.md) ·
[`../claude-agents/.claude/capabilities.md`](../claude-agents/.claude/capabilities.md) ·
[`RAMIN_OS_CONTEXT.md`](RAMIN_OS_CONTEXT.md) · [`../AGENTS.md`](../AGENTS.md)
