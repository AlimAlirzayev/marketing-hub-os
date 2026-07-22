# STRATEGY JOURNAL — future projects, SMART goals, business direction

Git-tracked, travels to both twins. This is the system's **living forward plan**:
what we intend to build/offer next, why, what each is blocked on, and how we measure
progress. Point-in-time decisions live in `decisions.jsonl`; detailed plans live in
`research-lab/knowledge/engineering/`; this file is the durable index over all of it,
so a future session (or the manager loop) starts strategic, not amnesiac.

**How to use / update protocol (keep it smart):**
- Every project is one block with a fixed schema (below). Change **Status** in place;
  never delete — retire to `Done` or `Dropped` with a one-line reason.
- **Disposition** mirrors the champion's frame: `SYSTEM` = the system can build it with
  what we own (reversible, no money/client) → the system may pursue it; `OWNER` = needs
  Alim's account / OAuth / money / a real client → his one step; `BLOCKED` = waiting on a
  named external unblock.
- **Never fabricate business targets.** A revenue/client goal is set by the operator; the
  system fills only capability/readiness goals it can honestly measure. Unknown → leave the
  metric as `⟨operator to set⟩`.
- Append a dated line to **§4 Journal log** whenever a project moves or a decision lands.
- On a real client brief, a project can spawn actual work; without one, it stays a plan
  (no manufactured client content — see `feedback_no_manufactured_motion`).

Cross-refs: `SHARED_CONTEXT.md` (spine + radar), `decisions.jsonl` (history),
`research-lab/knowledge/INDEX.md` (findings), `lab/prototypes/backlog.json` (build proposals).

---

## 1. Strategic thesis (the why)
The differentiator vs the builders we learn from (Doruk Yalçınsoy, Mert Durmazer): **they
demo, we run.** Same architecture — Claude as the orchestrator, everything else a tool via
MCP/CLI/API — but ours is always-on, server-side, security-hard-shelled, memory-backed, and
multi-model-resilient. The strategy is to convert that always-on edge into **sellable service
lines** for Alim's freelance marketing work, financed by free-first infrastructure so the
business never stops when a premium session's tokens run out.

Two engines drive this journal:
- **Capability pull** — close the specific GAPS the lab found vs the reference builders.
- **Market pull** — the radar's open findings (in `SHARED_CONTEXT.md` → Radar) that map to a
  real service Alim can offer AZ clients.

---

## 2. Project pipeline (the backlog)

Schema: **`[ID] Title` · Disposition · Value · Effort · Gate · Refs · Status**

### [P-01] AZ voice phone-agent (inbound qualifier → outbound → per-call report)
- **Disposition:** OWNER (then SYSTEM builds) — **the flagship service line** (Doruk's #1).
- **Value:** high. A phone agent that answers/qualifies AZ calls is a premium, recurring
  service; nobody local runs it always-on.
- **Effort:** medium — voice I/O is already ours; the new parts are telephony + a realtime
  bridge + a report webhook.
- **Gate (OWNER):** (a) ElevenLabs **paid tier** — the single unlock for BOTH nicer Telegram
  TTS and **ElevenLabs Agents** (the phone platform); (b) number/carrier — Twilio pilot vs a
  local AZ **SIP trunk** (Infobip; ~$0.004/min vs Twilio AZ-mobile outbound $0.63/min);
  (c) which **real** client/brand gets the pilot.
- **What the system builds once unblocked:** `gateway/call_agent.py` (ElevenLabs Agents
  custom-LLM WebSocket → `claude_bridge`), hub `/api/call-report` webhook → `jobs.sqlite`
  report card (reuses Morning Signals UX), a versioned "call script" skill.
- **Refs:** `research-lab/knowledge/engineering/2026-07-21_az-voice-phone-agent-plan.md`.
- **Status:** PLANNED. Voice foundation ✅ done+proven (edge-tts free AZ TTS, 2026-07-21).

### [P-02] Lead-gen / CRM agent studio (ICP scoring → personalized outreach → reply sentiment)
- **Disposition:** OWNER (then SYSTEM) — a concrete, sellable workflow (Doruk/Recep pattern).
- **Value:** high. Directly monetizable for AZ e-commerce/service clients.
- **Effort:** medium — browser v2 + brain + a CRM column write.
- **Gate (OWNER):** a real client with a lead list / CRM to run against.
- **Refs:** lab 07-19 study GAP #4.
- **Status:** PLANNED.

### [P-03] Premium AI video / UGC (Higgsfield / SeeDance / Fable-via-MCP)
- **Disposition:** BLOCKED (OWNER re-auth).
- **Value:** medium-high — closes the quality gap vs free-tier mediagen; UGC-agency angle.
- **Effort:** medium (studio wrapper once auth works).
- **Gate:** Higgsfield auth broken + Flora 403 `paid_plan_required` → Alim's re-auth, then
  re-judge SeeDance/Seedance.
- **Refs:** lab 07-19 GAP #2; `skill: generative-content-marketing`.
- **Status:** BLOCKED on re-auth (P3).

### [P-04] GEO / AI-search visibility audits (lead magnet → paid service)
- **Disposition:** OWNER — a free audit that opens a paid door.
- **Value:** medium — timely (Instagram now indexed by Google + a Search Console "Instagram
  property"); a cheap, high-trust first touch for prospects.
- **Effort:** low — connect an existing IG client as a Search Console property, pull query data.
- **Gate (OWNER):** an existing IG client's account access.
- **Refs:** Radar 9/10 (IG-in-Search-Console) + 7/10 (GEO tools mainstream).
- **Status:** PLANNED (owner one-step).

### [P-05] Meta Ads AI co-pilot service (campaign drafting via official Meta MCP)
- **Disposition:** OWNER — pitch "campaign drafting via AI co-pilot" to e-commerce clients.
- **Value:** medium-high.
- **Effort:** low-medium (Meta MCP is official; half-configured on Mac).
- **Gate (OWNER):** Meta OAuth (Alim's step); `meta-ads` MCP needs authorization.
- **Refs:** Radar 8/10 (Meta Ads MCP); `project_ads_studio_finance_radar`.
- **Status:** PLANNED (owner OAuth).

### [P-06] Karpathy skill discipline — finish the maturity model
- **Disposition:** SYSTEM.
- **Value:** medium (compounding — better skills every session).
- **Effort:** low.
- **Gate:** none. Layers 1–4 (learn/structure/eyes/ledger) largely exist; remaining is a
  skill-authoring skill + the explicit think-before/surgical/goal-driven authoring rules.
- **Refs:** decisions.jsonl P1 (skill outcome ledger, 2026-07-20).
- **Status:** PARTIAL.

---

## 3. SMART goals
Specific · Measurable · Achievable · Relevant · Time-bound. Owner column marks who moves it.
Business/revenue rows are the operator's to set — placeholders invite his numbers, not mine.

| # | Goal | Metric (done =) | Owner | Target | Status |
|---|------|-----------------|-------|--------|--------|
| G1 | AZ voice replies reliable & free | synthesize() returns audio, 100% STT round-trip | System | — | ✅ Done 2026-07-21 |
| G2 | Agentic jobs never ship raw error dumps | capped/errored builder → honest reply, no leak | System | — | ✅ Done 2026-07-21 |
| G3 | Phone-agent MVP demoable | 1 live inbound AZ call qualified end-to-end + report card | System | within 1 week of P-01 gate cleared | ⛔ blocked on P-01 gate |
| G4 | Choose phone-agent unlocks | ElevenLabs tier + number/carrier decided | Owner | ⟨operator to set⟩ | ◻ pending |
| G5 | First real pilot client named | one real brief attached to P-01 or P-02 | Owner | ⟨operator to set⟩ | ◻ pending |
| G6 | Revenue / service-line targets | ⟨operator to set⟩ | Owner | ⟨operator to set⟩ | ◻ pending |

---

## 4. Journal log (append-only, newest first)
- **2026-07-21** — Journal created. Reviewed Telegram logs → fixed the job-158 honesty bug
  (`8c53d00`) and the silently-dead AZ TTS (`61ec95f`, free edge-tts). Studied Doruk's
  same-day 4h Claude course; distilled the call-trilogy into P-01. Confirmed AZ voice I/O
  live (G1). Pipeline seeded from the lab 07-19 GAP study + open radar findings.

---

*Maintenance: the manager/champion loop and any planning session should keep §2 statuses and
§3 goals current, append to §4 on movement, and never let this file drift from
`decisions.jsonl`. If a project shrinks to a live capability, retire it to Done with a ref.*
