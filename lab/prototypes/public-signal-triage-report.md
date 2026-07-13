# Public Signal Triage Report

**Status:** prototype-soon

**Score:** 9/10

**Topic:** Public signal triage report

**Goal:** Produce a dated report with claim, source, verification status, module fit, risk controls, and next action.

**System integration idea:** A read-only Signal Radar workflow that writes lab findings and prototype candidates without creating new services.

**Acceptance:**
- Every claim is marked verified, watch, prototype, do-now, or skip.
- Official-source links are attached before provider/workflow recommendations.
- No secrets, private data, customer data, or credentials are read or sent.

**Dependencies:**
- gateway/signal_radar.py
- lab/knowledge
- lab/prototypes

**Risks:**
- hype intake
- stale provider claims
- source spoofing
- service sprawl

**Next action:** Keep the supervisor loop enabled and review output/signal-radar reports.

**Evidence:**
