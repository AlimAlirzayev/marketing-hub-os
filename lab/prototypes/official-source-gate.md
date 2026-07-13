# Official Source Gate

**Status:** do-now

**Score:** 9/10

**Topic:** Official-source gate for model and provider claims

**Goal:** Fail closed on unverified model/provider claims.

**System integration idea:** Fail closed in Agent Radar/provider auditions unless official docs, pricing, model IDs, availability, and terms are checked.

**Acceptance:**
- Provider claims cannot reach router/config changes without official source URLs.
- Pricing, model IDs, availability, data policy, and region limits are rechecked before implementation.
- Reports separate channel claims from verified facts.

**Dependencies:**
- gateway/agent_radar.py
- config/agent_permissions.json
- lab/knowledge

**Risks:**
- provider hallucination
- wrong model IDs
- unexpected API spend

**Next action:** Use this gate before any new model/provider route.

**Evidence:**
- [❎ SpaceXAI Unveils Grok 4.5](https://t.me/perplexity/1039)
- [official source](https://x.ai/news/grok-4-5)
