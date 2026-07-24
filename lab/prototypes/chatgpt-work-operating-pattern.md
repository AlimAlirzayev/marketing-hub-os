# Work Package Skill

**Status:** do-now

**Score:** 8/10

**Topic:** Work package operating pattern for Ramin-OS

**Goal:** Turn broad work requests into governed, reviewable work packages.

**System integration idea:** Strengthen job packaging: source status, plan, artifact, approval checklist, and reviewable output.

**Acceptance:**
- Every package records sources, redaction status, deliverables, risk gates, and approvals.
- Outward actions and scheduled tasks park for approval.
- Output appears in the panel deliverables gallery.

**Dependencies:**
- gateway/workspace_agent.py
- gateway/panel.py
- publisher
- brain

**Risks:**
- connector overreach
- local file exposure
- unapproved scheduled sending

**Next action:** Fold this pattern into the next workspace-agent or panel refinement.

**Evidence:**
- [🤔 Hugging Face Hacked by OpenAI Models That Escaped Their Sandbox](https://t.me/perplexity/1067)
- [official source](https://openai.com/index/hugging-face-model-evaluation-security-incident/)
