---
description: Re-verify the capability cascade against the live market — refresh free tiers / daily limits, hunt for newer cheaper providers, and update capabilities.md. Keeps the free-first router from trusting stale prices.
argument-hint: [capability]  (publish | clip | video-gen | image-gen | transcribe | llm | all)  [--apply]
---

# /scout

The market moves weekly — free tiers shrink, new free tools trend, MCPs appear.
`/scout` keeps [capabilities.md](../capabilities.md) honest so the router never
spends on something a newer free provider now covers, and never trusts a free
tier that quietly disappeared.

`$ARGUMENTS` = a capability to scout (default `all`). `--apply` writes the
changes back to `capabilities.md`; without it, you only propose a diff.

## Steps

### 1. Read the registry
Load `capabilities.md`. Collect every row's `verified` date and current free
quota. Flag rows that are **stale** (>30 days) or that a recent run reported
failing with a quota/auth/pricing error.

### 2. Re-verify existing providers
For each flagged row, `WebSearch` the current state — search the provider's own
pricing page + a third-party 2026 breakdown, and reconcile:
- free tier still exist? daily/monthly quota changed? watermark/resolution caps?
- API/MCP still the access path?
Record old → new for anything that moved.

### 3. Hunt for better providers
For each scouted capability, look for something cheaper/better than the current
top free row:
- **Hugging Face**: `hub_repo_search` with `sort: trendingScore`, and
  `space_search` with `mcp: true`, for that capability's task tag. A free
  trending Space that beats the current row is a candidate.
- **Web**: sweep "open source / free / self-hosted <capability> 2026" and
  "<capability> free API daily limit 2026".
Keep only providers that are genuinely free or free-tier'd and accessible from
this locked-down machine (portable / hosted, not native-runtime-dependent).

### 4. Propose the diff
Present, per capability: rows whose quota/price changed, new candidate rows
(with where they'd slot in the cascade), and rows to retire. Be concrete:
provider · tier · free quota · how invoked · source link.

### 5. Apply + re-stamp  (`--apply` only)
Edit `capabilities.md`: update changed rows, insert new providers at the right
cascade position, re-stamp `verified:` dates and the footer. Summarize what
changed in one paragraph.

### 6. Surface it
If the autonomous layer is running, the change summary belongs in the Telegram
morning report — a shrinking free tier the user doesn't know about is exactly
the kind of thing that silently breaks `/publish` or `/post` later.

## Rules
- **Don't invent quotas.** Every number comes from a source you just read; cite
  it. If a tier is ambiguous, say "unverified" rather than guessing.
- **Free + reachable only.** A great tool that needs a native ML runtime is
  useless here (VC++/EDR lockdown) — note it but don't promote it.
- **Propose, then apply.** No silent rewrites of the registry without `--apply`.

## Examples
```
/scout                      # re-verify everything, propose a diff
/scout publish --apply      # refresh the publish cascade and write it back
/scout video-gen            # just hunt for better free video models
```
