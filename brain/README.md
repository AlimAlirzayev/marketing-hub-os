# RAMIN OS — Knowledge Core (`brain/`)

The system's institutional memory and **learning loop**. The valuable things we
decide, learn, and get right should not evaporate when a session ends. They are
captured as plain markdown, made retrievable, and fed back into future work — so
the operator, the agent, and the system all get a little stronger every day.

This is the system-level counterpart to the assistant's own per-conversation
memory: here the **whole OS** accumulates knowledge that any part (the autonomous
gateway, the council, a future session) can stand on.

## Design principles

1. **Markdown is the source of truth.** Every entry is one human-readable file in
   `data/memory/<id>.md` with a small frontmatter header. Nothing is ever locked
   in a binary blob; everything is greppable, git-trackable, and hand-editable.
2. **Embeddings are only an accelerator.** Semantic search (Gemini
   `text-embedding-004`) is an *optional* rerank layer that must degrade to
   keyword search when the free tier is unavailable. Off by default
   (`BRAIN_EMBEDDINGS=1` to enable). The Gemini free tier is too flaky to depend
   on — recall works offline, instantly, with zero API calls.
3. **The brain never fabricates itself full.** Auto-distilled lessons land in a
   **pending review queue** (`data/memory/_pending/`), never straight into the
   trusted store. A human (or `brain review approve`) promotes the good ones.
4. **It can never break a job.** Every gateway integration is guarded and
   returns a safe empty value on any error. A learning feature must not take down
   task execution.

## The loop

```
        ┌──────────────── RECALL (before) ────────────────┐
 task → │ pull relevant past decisions/lessons/playbooks  │ → injected into the
        │ (keyword + optional embeddings)                 │   execution prompt
        └─────────────────────────────────────────────────┘
                              │
                          execution
                              │
        ┌──────────────── REFLECT (after) ────────────────┐
 result→│ LLM distills 0–3 reusable lessons               │ → data/memory/_pending/
        │ (only if BRAIN_REFLECT on)                      │   (await human approval)
        └─────────────────────────────────────────────────┘
                              │
                      review → approve
                              │
                      data/memory/*.md  ──────────────► feeds the next RECALL
```

## Entry types

`decision` · `lesson` · `playbook` · `pattern` · `glossary` · `preference`

Each file:

```markdown
---
id: decision-deliverable-design-bar
type: decision
title: Deliverable design bar: cover + cards + badges + phased section
tags: [deliverables, design, pdf]
source: manual
confidence: high
created: 2026-06-18
updated: 2026-06-18
related: []
---

Report-style deliverables must clear a design bar: cover page, card layout,
status badges, phased-workflow section. … Why: the operator judges quality
visually and a flat table reads as unfinished.
```

## CLI

```powershell
# capture
python -m brain remember "Use headless Edge for PDFs" --type decision --tags pdf,report --body "HTML through headless Edge is the working PDF path."

# recall (keyword, instant, offline)
python -m brain recall "how do we build a report PDF"
python -m brain recall "kasko kampaniya" --block      # the prompt-injection form

# browse
python -m brain list --type decision
python -m brain show decision-deliverable-design-bar
python -m brain stats

# learning review queue
python -m brain review                  # list pending suggestions
python -m brain review approve 1        # promote suggestion #1 into the store
python -m brain review reject 2

# distill a finished gateway job into lessons
python -m brain reflect --job 12

# (re)seed the durable, hard-won learnings
python -m brain.seed
```

## Python API

```python
import brain

brain.remember("title", "body", type="lesson", tags=["x"], confidence="high")
hits  = brain.recall("query", k=5)          # list[Hit] with .entry and .score
block = brain.recall_block("query")         # ready-to-inject markdown, or ""
brain.reflect(task, result)                 # -> pending suggestions (list[Entry])
brain.stats()
```

## Gateway integration

`gateway/knowledge.py` is the thin, guarded bridge:

- **Recall** is injected into the execution prompt on every autonomous job —
  both the direct executor (`gateway/executor.py`) and the council's Codex
  executor (`gateway/council.py`).
- **Reflect** runs in `gateway/worker.py` *after* the result is delivered, so it
  never delays the user, and writes only to the pending queue.

### Env toggles

| Var | Default | Effect |
|---|---|---|
| `BRAIN_RECALL` | `1` (on) | Inject institutional knowledge into execution prompts |
| `BRAIN_REFLECT` | `1` (on) | Auto-distill finished jobs into pending lessons (1 Gemini call/job) |
| `BRAIN_EMBEDDINGS` | `0` (off) | Add semantic rerank on top of keyword recall |
| `BRAIN_EMBED_MODEL` | `text-embedding-004` | Embedding model |
| `BRAIN_REFLECT_MODEL` | `gemini-2.5-flash` | Model used to distill lessons |

Set any to `0` to disable. With everything off, the gateway behaves exactly as
it did before the brain existed.

## Tests

```powershell
python -m unittest tests.test_brain        # 12 tests, no network needed
```

## Roadmap

- [ ] `brain review` UI tab in the hub (approve/reject pending from the browser).
- [ ] Periodic "what did we learn this week" digest from the pending queue.
- [ ] Wire recall into the studios (`/post`, Price Hunter) the same way.
- [ ] Optional embedding warm-up after seeding (`brain.embeddings.warm`).
