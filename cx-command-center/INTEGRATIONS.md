# Customer Relations Center Integration Runbook

This is the live-channel checklist for moving from demo mode to production.

## 1. Public URL

Meta webhooks require HTTPS with a valid certificate. For local testing use a
tunnel, then put its URL into each upstream platform:

```text
https://your-domain.example/api/webhooks/meta
https://your-domain.example/api/webhooks/chatplace
```

## 2. Chatplace

In Chatplace Automation Builder:

1. Add `Action -> External API request`.
2. Method: `POST`.
3. URL: `https://your-domain.example/api/webhooks/chatplace`.
4. Header: `Content-Type: application/json`.
5. Header: `X-CX-Token: <CX_WEBHOOK_SECRET>`.
6. Body: include message/comment text, user, platform/channel, source URL and
   a stable message/comment ID.

Minimum body:

```json
{
  "channel": "instagram_comment",
  "comment": { "id": "comment-id", "text": "Customer text", "url": "https://..." },
  "user": { "name": "Customer", "username": "@customer" },
  "account": { "name": "Brand account" },
  "created_at": "2026-06-08T12:00:00+04:00"
}
```

## 3. Meta Instagram/Facebook

Environment:

```env
CX_META_VERIFY_TOKEN=choose_a_long_random_string
CX_META_APP_SECRET=your_meta_app_secret
META_GRAPH_ACCESS_TOKEN=page_or_system_user_token
META_FACEBOOK_PAGE_IDS=123456789
META_INSTAGRAM_BUSINESS_IDS=17841400000000000
```

Meta App Dashboard:

1. Add Webhooks product.
2. Callback URL: `https://your-domain.example/api/webhooks/meta`.
3. Verify token: same value as `CX_META_VERIFY_TOKEN`.
4. Subscribe to Instagram `comments`, `mentions`, `messages`.
5. Subscribe to Page/Messenger events if Facebook messages/comments are in scope.

The endpoint validates `X-Hub-Signature-256` when `CX_META_APP_SECRET` is set.

For pull sync, first discover assets visible to the token:

```http
GET /api/sync/meta/discover
```

Then add the returned Page IDs to `META_FACEBOOK_PAGE_IDS` and Instagram
Business account IDs to `META_INSTAGRAM_BUSINESS_IDS`.

Manual pull sync:

```http
POST /api/sync/meta
```

## 4. Google Business Profile Reviews

Environment:

```env
GOOGLE_BUSINESS_PROFILE_ACCESS_TOKEN=ya29...
GOOGLE_BUSINESS_PROFILE_ACCOUNT_ID=123456789
GOOGLE_BUSINESS_PROFILE_LOCATION_IDS=111111111,222222222
```

Manual sync:

```http
POST /api/sync/google-reviews
```

All configured pull connectors:

```http
POST /api/sync/all
```

Review reply dry-run:

```http
POST /api/complaints/{id}/reply/google
{ "dry_run": true }
```

Real reply after human approval:

```http
POST /api/complaints/{id}/reply/google
{ "dry_run": false, "message": "Approved public reply" }
```

## 5. Alerts

Environment:

```env
TELEGRAM_BOT_TOKEN=...
CX_ALERT_CHAT_ID=...
```

Only new `critical` and `high` complaints trigger Telegram alerts. Repeated
Google syncs do not re-alert unchanged complaints.

## 6. Daily Operating Rhythm

- Morning: open `/api/report` or dashboard, review overdue and critical queue.
- During day: operators move items to `in_progress`, `waiting_customer`,
  `resolved`, then `closed`.
- Weekly: export `/api/export.csv?days=7` and review top root causes by team.
- Monthly: export `/api/export.csv?days=30` for board-level customer feedback reporting.
