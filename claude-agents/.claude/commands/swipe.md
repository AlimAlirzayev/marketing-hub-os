---
description: Pull real, current ad campaigns from Ads of the World into the swipe file and brief the user — grounded creative inspiration on demand (Context7 for creativity)
argument-hint: [industry slug, default insurance]  [--deep <n>]  [--fresh]  [--campaign <slug>]
---

# /swipe

Grounded inspiration on demand. `/idea` invents; `/swipe` shows what the
world's agencies actually shipped — so our ideas are informed thieves, not
accidental copies. Governance: `config/agent_permissions.json` →
`adsworld_swipe`.

## Steps

### 1. Parse `$ARGUMENTS`

- First bare word = industry slug (default `insurance`; any
  adsoftheworld.com industry works — automotive, finance, food…)
- `--deep <n>` also fetch full detail for the newest n campaigns
  (default 5 when the cache is being refreshed)
- `--fresh` force a refetch even if the cache is <7 days old
- `--campaign <slug>` deep-dive one specific campaign instead
- `--grab <slug>` download the campaign film + frames and LOOK at it

### 2. Refresh the swipe file

```powershell
python idea-studio/adsworld.py --industry <slug> --pages 3 --deep 5 [--fresh]
```

Reuses the 7-day cache when fresh (fast, polite to the site). On fetch
failure the errors are printed and recorded in the digest — report them,
never pretend (no-silent-drops).

### 3. Read `idea-studio/swipe_file/adsworld-<industry>.md` and brief

In Azerbaijani, give the user:

- **Nə təzədir** — the 5–8 newest campaigns: brand, country, one-line
  what-they-did (from real descriptions only; cards without detail get
  title+brand+link, nothing invented)
- **Nümunələr arasında naxışlar** — recurring tensions, devices, tones
  (name the creative_dna tradition each pattern echoes, if any)
- **Bizə körpü** — 2–3 concrete "adapt this structure for Xalq Sigorta"
  angles, each tagged with which studio would execute (/idea → /post,
  media_studio, copy-studio)

Every claim traces to a campaign in the digest (link it). The digest is
CANLI/DEMO-labeled — say which. If the user picks an angle, hand off to
`/idea` with the swipe entry as reference.

### 4. Video dive — when a campaign film matters, SEE it

```powershell
python idea-studio/adsworld.py --grab <slug>
```

→ `idea-studio/output/adsworld/<slug>/` gets video.mp4 + frame-N.jpg +
detail.json. **Read the frames and LOOK** (never-say-cant rule: visual
work is judged by eyes, never by its text summary). Report what the
film actually does — color world, casting, framing, device — and how
that confirms or contradicts the written description. This is the same
pipeline that birthed `caring-hand-miniature` from the user's reference
video.

The swipe file refreshes itself: gateway schedule #4 runs `swipe
həftəlik` daily at 10:00; the 7-day cache turns that into a weekly
fetch. Manual runs are only needed for `--fresh`, other industries, or
grabs.

## Rules

- **Steal like an artist: structure and craft, never the execution.**
  Direct copying of a campaign into a deliverable is a KILL.
- **Never fabricate a campaign, brand, credit, or result.** Only what the
  swipe file / site actually says.
- **Think all industries** — insurance is home, but cross-industry theft
  is often the best theft; suggest a second industry when relevant.
