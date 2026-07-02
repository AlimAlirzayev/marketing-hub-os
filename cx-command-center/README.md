# Customer Relations Center

AI-assisted complaint and feedback center.

It collects complaint-oriented messages from social channels, Chatplace, Google
reviews, website forms and support inboxes into one operational queue. Each
signal is triaged for sentiment, severity, root cause, owner team, SLA and reply
draft.

## Run

```powershell
cd cx-command-center
.\run.ps1
```

Open:

```text
http://127.0.0.1:8810
```

API docs:

```text
http://127.0.0.1:8810/api/docs
```

Docker Compose:

```powershell
docker compose up -d cx-command-center
```

## What the MVP does

- Stores every customer signal in local SQLite.
- Normalizes manual, Chatplace and Google review webhook payloads.
- Runs deterministic complaint triage with optional local/private Hugging Face
  sentiment reinforcement and Gemini refinement.
- Assigns category, risk severity, urgency score, team and SLA deadline.
- Generates an Azerbaijani public/private reply draft.
- Builds a draft-only CX Resolution Agent plan: priority recovery queue,
  redacted evidence, human approval checklist and next-best actions. It never
  sends replies or changes statuses by itself.
- Shows a live dashboard: risk index, priority queue, overdue SLA, root causes,
  channels and grounded AI command answers.
- Supports status changes from the dashboard.
- Shows live integration health and a one-click `Sync` action for pull channels.

## Webhook endpoints

Generic ingestion:

```http
POST /api/ingest
```

Body:

```json
{
  "source": "manual",
  "channel": "instagram_comment",
  "external_id": "ig-comment-123",
  "author_name": "Customer",
  "author_handle": "@customer",
  "text": "3 gündür cavab almıram. Bu necə xidmətdir?",
  "url": "https://instagram.com/p/example"
}
```

Chatplace:

```http
POST /api/webhooks/chatplace
```

Google reviews:

```http
POST /api/webhooks/google-review
```

Meta webhook verification and events:

```http
GET  /api/webhooks/meta?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
POST /api/webhooks/meta
```

Google Reviews pull sync:

```http
POST /api/sync/google-reviews
```

Meta owned-comments pull sync:

```http
POST /api/sync/meta
```

All configured pull connectors:

```http
POST /api/sync/all
```

Integration status:

```http
GET /api/integrations/status
```

Meta Page / Instagram Business discovery:

```http
GET /api/sync/meta/discover
```

CSV export:

```http
GET /api/export.csv?days=30
```

Draft-only resolution agent:

```http
GET /api/resolution-agent/draft?days=7&limit=20
```

If `CX_WEBHOOK_SECRET` is set, send either:

- `X-CX-Token: <CX_WEBHOOK_SECRET>` for simple tools like Chatplace/n8n.
- `X-CX-Signature` as the lowercase hex HMAC-SHA256 of the raw request body.

## Environment

Add these to the repo-root `.env` when ready:

```env
CX_DATA_MODE=demo
CX_ACCOUNT_NAME=Xalq Sigorta
CX_APP_NAME=Customer Relations Center
CX_ACCOUNT_TAGLINE=Complaint radar, AI triage, SLA and customer recovery
CX_WEBHOOK_SECRET=
CX_META_VERIFY_TOKEN=
CX_META_APP_SECRET=
CX_ALERT_CHAT_ID=
CX_AI_ENABLED=true
CX_GEMINI_MODEL=gemini-3.5-flash
CX_AI_TIMEOUT_SECONDS=5
CX_SYNC_INTERVAL_SECONDS=0

CX_HF_SENTIMENT_ENABLED=0
CX_HF_SENTIMENT_ENDPOINT=
CX_HF_SENTIMENT_MODEL=
CX_HF_SENTIMENT_ALLOW_EXTERNAL=0
CX_HF_SENTIMENT_TIMEOUT_SECONDS=4
CX_HF_SENTIMENT_MIN_CONFIDENCE=0.70
CX_HF_SENTIMENT_MAX_CHARS=1200

CHATPLACE_PULL_URL=
CHATPLACE_API_TOKEN=

GOOGLE_BUSINESS_PROFILE_ACCESS_TOKEN=
GOOGLE_BUSINESS_PROFILE_ACCOUNT_ID=
GOOGLE_BUSINESS_PROFILE_LOCATION_IDS=123456789,987654321
GOOGLE_BUSINESS_PROFILE_REVIEW_PAGE_SIZE=50

META_GRAPH_API_VERSION=v25.0
META_GRAPH_ACCESS_TOKEN=
META_FACEBOOK_PAGE_IDS=
META_INSTAGRAM_BUSINESS_IDS=
META_SYNC_POST_LIMIT=10
META_SYNC_MEDIA_LIMIT=10
META_SYNC_COMMENT_LIMIT=50
```

The app reuses `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Without a
key, rule-based triage still works.

The optional Hugging Face sentiment path is deliberately private-first. It
expects a local/private text-classification endpoint that returns HF-style
`label` + `score` rows. It can raise complaint risk when the model sees a strong
negative signal, but it cannot downgrade deterministic rule-based risk.

## Channel connection plan

1. Chatplace: add an External API Request action that POSTs message/comment
   payloads to `/api/webhooks/chatplace`. If Chatplace exposes an export/feed
   URL, set `CHATPLACE_PULL_URL` and use `/api/sync/all`.
2. Google Business Profile: configure the env vars and click `Sync`, or call
   `/api/sync/google-reviews`.
3. Meta webhooks: subscribe Instagram/Facebook comments and messaging events,
   point the callback URL to `/api/webhooks/meta`, and use
   `CX_META_VERIFY_TOKEN` as the verify token in Meta App Dashboard.
4. Meta Graph pull: set `META_FACEBOOK_PAGE_IDS` and/or
   `META_INSTAGRAM_BUSINESS_IDS`, then click `Sync` or call `/api/sync/meta`.
5. Website forms/live chat: POST directly to `/api/ingest`.
6. n8n: schedule review scraping/listening jobs, dedupe by external_id and push
   into the command center.

See [INTEGRATIONS.md](INTEGRATIONS.md) for the production runbook.
See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for the operator
checklist and platform-owner steps.

## Production notes

- Put the app behind HTTPS before connecting Meta webhooks; Meta requires a valid
  TLS certificate for live callbacks.
- Set `CX_META_APP_SECRET` to validate Meta's `X-Hub-Signature-256` header.
- Set `CX_WEBHOOK_SECRET` for internal/n8n/Chatplace HMAC protection.
- Use `CX_ALERT_CHAT_ID` with `TELEGRAM_BOT_TOKEN` to alert critical/high cases.
- Keep public replies human-approved for high-risk public channels.
