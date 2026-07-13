# Marketing Certification Coach

Ramin-OS learning module for marketing certifications. It ranks credible
certifications, builds a mentor roadmap, runs a persistent Journey Engine,
creates original mock tests, and keeps registration, payment, proctored exams,
and public sharing behind explicit human checkpoints.

This is not a certificate brochure. The coach has an inspectable knowledge and
memory layer:

- Source knowledge: `data/certifications.json` plus `data/knowledge/*.md`.
- Local vector index: root `data/certification_coach/vector_index.json`.
- Learner memory: root `data/certification_coach/learner_memory.jsonl`.
- Journey state: root `data/certification_coach/journeys/*.json`.
- Institutional memory: optional recall from the existing Ramin-OS `brain`.
- Semantic rerank: optional, via `brain.embeddings` when `BRAIN_EMBEDDINGS=1`.

## Run

```powershell
python -m uvicorn certification_coach.server:app --port 8880
```

The module is registered in `services.json` as `certcoach`, so it appears in the
hub and starts with `START_MARKETING_OS.ps1`.

## API

- `GET /api/health` - service status.
- `GET /api/catalog` - source-linked certification catalog and ethics policy.
- `POST /api/plan` - profile-based ranked stack and week-by-week mentor plan.
- `POST /api/mock` - original practice questions, not real exam content.
- `POST /api/grade` - mock scoring and rationales.
- `GET /api/journeys` - persistent certification journey list.
- `POST /api/journeys` - start a gated journey for one certification.
- `GET /api/journeys/{journey_id}` - journey state, readiness, stages, blockers.
- `POST /api/journeys/{journey_id}/action` - record safe progress actions.
- `GET /api/knowledge` - knowledge/vector/memory status and sample chunks.
- `POST /api/knowledge/reindex` - rebuild the local vector index.
- `GET /api/search?q=...` - local vector search over certification knowledge.
- `POST /api/ask` - grounded RAG-style mentor answer with evidence snippets.

## Knowledge Architecture

The source of truth stays in human-readable files. The runtime index is
regenerable and local:

```text
certification_coach/data/certifications.json
certification_coach/data/knowledge/*.md
        -> certification_coach.knowledge.rebuild_index()
        -> data/certification_coach/vector_index.json

POST /api/grade
        -> data/certification_coach/learner_memory.jsonl

POST /api/journeys
        -> data/certification_coach/journeys/*.json
        -> source verification + baseline + study + drills + mock gate
        -> weakness repair + portfolio proof + readiness review
        -> human approval before official setup/exam handoff
```

Retrieval is local sparse TF-IDF by default, so it works without an LLM key or
network. If the wider Brain embedding adapter is enabled with a private/local
endpoint, search results get a semantic rerank. If LLM synthesis is unavailable,
`/api/ask` returns extractive evidence snippets instead of pretending.

## Governance

This is an exam-prep coach, not an exam-taking agent.

Allowed:

- study plans, flashcards, mock questions, roadmaps, portfolio proof tasks;
- public official-source verification;
- draft-only certificate sharing copy and approval checklists.

Blocked:

- taking a live certification exam for the user;
- answering or viewing live exam questions;
- collecting exam dumps, screenshots, or private exam content;
- entering credentials, paying, booking, submitting, or posting without human
  approval.

The permission entry is `marketing_certification_coach` in
`config/agent_permissions.json`.

## Journey Engine

The Journey Engine is the "A point to B point" path. A learner selects a
certificate and starts a journey. The system then blocks official exam setup
until these gates are clear:

- current official source verification;
- baseline diagnostic or first original mock;
- required study blocks and scenario drills;
- required mock attempts at the score target;
- weak-topic repair when mocks reveal gaps;
- portfolio proof task;
- readiness review;
- explicit human approval.

After approval, the UI can track official setup, exam day, and certificate
capture, but the human still handles login, payment, booking, identity checks,
live questions, and submission.
