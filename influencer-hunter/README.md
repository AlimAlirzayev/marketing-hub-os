# Influencer Hunter - AZ creator intelligence agent

Finds and ranks Azerbaijani influencers/bloggers for a campaign brief, with
evidence from Instagram profiles, Reels/posts, comments and engagement signals.

The output is not just a list of names or an analytics table. It is a decision
aid for one concrete question:

> Who should we contact first for this exact campaign brief?

It returns a top shortlist with:

- campaign/creator fit,
- Reels and post proof,
- follower feedback and sentiment,
- engagement quality,
- brand-safety and authenticity checks,
- direct evidence URLs and metrics.

## Pipeline

```text
brief
  -> resolve.py        campaign brief: brand, product, angle, audience, topics
  -> sources*.py       acquisition connector (see Sources)
  -> score.py          0..10 evidence rubric
  -> analyze.py        audience analysis: pandas + LLM Azerbaijani comment sentiment
  -> hunt.py           shortlist + optional LLM verdict
  -> report.py         JSON/Markdown on disk
```

## Sources (acquisition orchestration)

`orchestrate.py` is the acquisition layer: a formal `Connector` contract +
registry with **fan-out** across platforms (parallel) and a **fallback chain**
within a platform (try by priority, stop at the first that returns data, so a
paid provider is not double-spent when a free one answers). Same-`(platform,
handle)` records are merged; cross-platform identities are deliberately *not*
auto-merged (a wrong merge would corrupt the shortlist). Every connector's status
is surfaced honestly — a failing source degrades, it never silently drops.

Pick sources with `source=` (API) / `--source` (CLI) / the **Mənbə** dropdown
(UI): a single name, a comma-separated list, or `all`. All connectors normalize
to the same model, so scoring/analysis/filters/UI are shared.

| Source | Module | Cost / risk | Notes |
|---|---|---|---|
| `instagram` (default) | `sources.py` | Apify credits | hashtag/search/profile/post/comment; on-disk cache |
| `youtube` | `sources_youtube.py` | **free, official, no ban** | YouTube Data API v3: channel/video/**comment** text; `country` is an authoritative local signal |
| `telegram` | `sources_telegram.py` | **free, anonymous, no ban** | public `t.me/s/<channel>` previews: subs, description, posts + views (no login/MTProto) |
| `web` | `sources_web.py` | **free, no credentials** | keyless search + LLM extraction of public AZ creator listicles; discovery feeder |
| `instagram` (fallback) / `tiktok` | `sources_rapidapi.py` | **freemium, one key** | generic RapidAPI multi-host connector; revives Instagram without Apify + adds TikTok; enrichment by handle. Run `rapidapi_probe.py` to see which hosts your key unlocks |

See [PLATFORMS.md](PLATFORMS.md) for the full constraint-filtered map (incl. why X/LinkedIn/Snapchat are deferred).

`analyze.py` runs for any source with comment text: pandas aggregation + bot/dup
detection, plus an optional LLM that returns Azerbaijani audience-sentiment
summaries and themes.

## Run

```powershell
influencer-hunter\run.bat
# or:
cd influencer-hunter
..\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8840
```

Open `http://localhost:8840`.

## CLI

```powershell
cd influencer-hunter
..\.venv\Scripts\python.exe cli.py "Xalq Sigorta üçün səyahət sığortası barədə emosional Instagram Reel canlandıracaq travel blogger lazımdır"
..\.venv\Scripts\python.exe cli.py "Azərbaycanlı travel/lifestyle YouTube creator" --source youtube --top 3
..\.venv\Scripts\python.exe cli.py "travel insurance reel creator" --seed-handles handle1,handle2 --top 3
..\.venv\Scripts\python.exe cli.py "family travel insurance blogger" --json
```

Reports are saved to `influencer-hunter/data/reports/`.

## API

```http
POST /api/hunt
{
  "query": "Xalq Sigorta üçün səyahət sığortası barədə emosional Reel creator lazımdır",
  "top_n": 3,
  "min_score": 0,
  "seed_handles": [],
  "deep_comments": true,
  "verdict": true
}
```

## Configuration

Uses the repo-root `.env`.

| Variable | Role |
|---|---|
| `APIFY_API_TOKEN` | Enables live Instagram discovery and comments |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Brief parsing and final verdict |
| `GROQ_API_KEY` | LLM fallback |
| `IH_INSTAGRAM_HASHTAG_ACTOR` | Default `apify/instagram-hashtag-scraper` |
| `IH_INSTAGRAM_PROFILE_ACTOR` | Default `apify/instagram-profile-scraper` |
| `IH_INSTAGRAM_POST_ACTOR` | Default `apify/instagram-post-scraper` |
| `IH_INSTAGRAM_COMMENT_ACTOR` | Default `apify/instagram-comment-scraper` |
| `IH_APIFY_MAX_RETRIES` | Retries on transient 5xx/timeout Apify errors (default `2`) |
| `IH_DISABLE_CACHE` | `1` to force a fully live run (skip the on-disk actor cache) |
| `IH_CACHE_TTL` | Actor-cache freshness window in seconds (default `21600` = 6h) |
| `RAPIDAPI_KEY` | One RapidAPI key — revives Instagram (no Apify) + adds TikTok via `sources_rapidapi.py`. Probe hosts with `python rapidapi_probe.py` |
| `IH_RAPIDAPI_IG_HOST` / `IH_RAPIDAPI_TT_HOST` | Pin a specific host you subscribed to (else the built-in adapter registry is tried in order) |

Without `APIFY_API_TOKEN`, the module still runs and reports that live Instagram
evidence is unavailable. Seed handles can be entered, but real ranking requires
profile/post/comment data from Apify or a future owned-data connector.

Identical Apify actor calls are cached on disk (`data/cache/`) so repeated and
development runs do not re-scrape or re-spend credits; cache hits are surfaced
honestly in the source-coverage table. Apify calls also run off the event loop,
so the dashboard stays responsive during a scan.

## Scoring Rubric

Weighted total score is 0..10:

- audience fit: 20%
- content/Reels fit: 22%
- engagement quality: 16%
- follower feedback sentiment: 14%
- brand safety: 14%
- authenticity: 9%
- proof density: 5%

This means a creator with a smaller but relevant, responsive audience can beat a
large account with weak engagement or thin proof.

## Result Logic

Read the output in this order:

1. **Decision** - what the system thinks you should do next.
2. **Primary outreach / second option / third option** - the actual creator
   recommendation roles.
3. **Why** - the campaign-specific reasons, not generic influencer stats.
4. **Evidence** - links and metrics you can inspect yourself.
5. **Next checks** - rate card, last 30-day insights, usage rights and manual
   brand-safety review.

Follower count is never the main answer. It is only one supporting signal.

The default shortlist gate is `20,000+` Instagram followers. Accounts below
that threshold, or accounts whose follower count cannot be verified, are moved
to `filtered_out` and shown separately from the recommendation.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the decision pipeline.
