# Influencer Hunter Architecture

## Original Job To Be Done

When a brand says:

> We need an Azerbaijani influencer/blogger who can perform this exact emotional
> selling proposition as an Instagram Reel.

the tool must answer:

> Contact these 3 creators first, and here is the proof.

The product is not a generic influencer database. It is a campaign-fit decision
engine.

## Decision Pipeline

```text
1. Brief understanding
   brand, product, audience, emotional angle, format, topics, exclusions

2. Market discovery
   Instagram hashtags, search, profile data, recent posts/Reels, comments

3. Eligibility gates
   hard filters before recommendation:
   - minimum followers, default 20,000
   - follower count must be known unless explicitly allowed
   - minimum score if the user sets it

4. Evidence scoring
   soft evaluation:
   - audience/topic fit
   - Reel/storytelling fit
   - engagement quality
   - follower feedback sentiment
   - brand safety
   - authenticity
   - proof density

5. Recommendation framing
   output is written as an outreach decision:
   - Primary outreach
   - Second option
   - Third option
   - Why
   - Evidence links
   - What to verify before signing
```

## Why The 20k Follower Gate Exists

For Xalq Sigorta-style campaigns, the creator should have enough audience reach
to move a mass-market insurance message. Smaller creators can still be valuable,
but they should not appear as final shortlist recommendations unless the user
relaxes the filter.

The current default gate is:

```text
followers >= 20,000
```

Creators below the gate are not deleted. They are moved to `filtered_out`, so
the user can understand what was excluded and why.

## What Counts As Proof

Proof must be inspectable. Useful evidence includes:

- Instagram profile metadata,
- recent Reels/posts,
- captions related to the campaign topic,
- engagement metrics,
- comments and feedback sentiment,
- direct URLs for manual review,
- flags for brand-safety or authenticity concerns.

The system should never invent creator fit. If evidence is missing, the output
must say that evidence is missing.

## Output Contract

Every result should make these clear:

- what question the result answers,
- which filters were active,
- who to contact first,
- why each creator passed,
- what evidence supports it,
- what needs human verification.

Follower count alone is never the answer. It is an eligibility gate and one
reach signal inside a larger recommendation.
