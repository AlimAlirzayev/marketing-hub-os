# Customer Relations Center Production Readiness

This file is the operator checklist for moving the live dashboard from
"ready to receive data" to "fully connected to production channels".

## Quick Audit

Run this any time:

```powershell
python scripts\audit-cx-readiness.py --external
```

The script does not print secrets. It reports only pass, warn, and blocker
states.

## Current Production Meaning

Ready now:

- Customer Relations Center server and dashboard.
- Local SQLite storage.
- AI triage, category, severity, SLA, reply draft.
- Chatplace webhook endpoint.
- Meta webhook endpoint.
- Telegram alert configuration.
- Manual Sync button and `/api/sync/all`.

Still requiring platform-owner action:

- Meta Page / Instagram Business account IDs and permissions.
- Google Business Profile OAuth token, account ID, and location IDs.
- Optional Chatplace pull feed URL, if Chatplace provides one.

## Meta: Facebook and Instagram Comments

Use this when you want owned Facebook Page comments and Instagram Business media
comments to sync into the dashboard.

1. Open Meta for Developers.
2. Select the app connected to Xalq Sigorta assets.
3. Ensure the app has access to the Facebook Page and Instagram professional
   account.
4. Add or approve permissions for owned comments. Typical required permissions:
   `pages_read_engagement`, `pages_show_list`, `instagram_business_basic`,
   `instagram_business_manage_comments`.
5. Generate a long-lived user/page/system token that can see those assets.
6. Put the token into `.env` as `META_GRAPH_ACCESS_TOKEN`, or keep
   `META_ACCESS_TOKEN` if it is the token with those permissions.
7. Run:

```powershell
Invoke-RestMethod http://127.0.0.1:8810/api/sync/meta/discover
```

8. Copy returned Page IDs into:

```env
META_FACEBOOK_PAGE_IDS=page_id_1,page_id_2
```

9. Copy returned Instagram Business IDs into:

```env
META_INSTAGRAM_BUSINESS_IDS=ig_business_id_1,ig_business_id_2
```

10. Restart the Customer Relations Center and click `Sync`.

If discovery returns zero pages/accounts, the token is not authorized for the
owned social assets. This cannot be solved from local code alone; the business
asset admin must grant access.

## Google Business Profile Reviews

Use this when you want Google reviews to sync and draft replies.

1. Open Google Cloud Console.
2. Enable the Business Profile APIs for the project.
3. Configure OAuth consent.
4. Create OAuth credentials.
5. Authorize with an account that manages the verified Xalq Sigorta Business
   Profile locations.
6. Request the scope:

```text
https://www.googleapis.com/auth/business.manage
```

7. Add these values to `.env`:

```env
GOOGLE_BUSINESS_PROFILE_ACCESS_TOKEN=
GOOGLE_BUSINESS_PROFILE_ACCOUNT_ID=
GOOGLE_BUSINESS_PROFILE_LOCATION_IDS=
```

8. Restart the Customer Relations Center and call:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8810/api/sync/google-reviews
```

## Chatplace

Best path is webhook mode:

1. In Chatplace Automation Builder, add External API request.
2. Method: `POST`.
3. URL: `https://your-public-domain/api/webhooks/chatplace`.
4. Header: `X-CX-Token: <CX_WEBHOOK_SECRET>`.
5. Send message text, user, platform, stable ID, and source URL.

Optional pull mode:

```env
CHATPLACE_PULL_URL=
CHATPLACE_API_TOKEN=
```

Only use pull mode if Chatplace provides a JSON feed/export endpoint.

## Public Webhook Hosting

Meta and Chatplace need a public HTTPS URL. Localhost works only for local
testing. For production use one of these:

- A small VPS.
- Cloudflare Tunnel.
- ngrok for temporary testing.
- Corporate reverse proxy.

For immediate testing without DNS setup, run:

```powershell
.\scripts\start-cx-public-tunnel.ps1
```

This creates a temporary `trycloudflare.com` HTTPS URL and writes it to
`CX_PUBLIC_BASE_URL` in `.env`. The URL changes when the tunnel is restarted.
Stop it with:

```powershell
.\scripts\stop-cx-public-tunnel.ps1
```

Set:

```env
CX_META_APP_SECRET=
```

before exposing Meta webhooks publicly so the app verifies Meta signatures.

Set the public URL that points to this app:

```env
CX_PUBLIC_BASE_URL=https://your-public-domain
```

## Auto Sync

After Meta/Google pull credentials are ready:

```env
CX_SYNC_INTERVAL_SECONDS=300
```

Restart the Customer Relations Center. The dashboard will then pull configured
channels every five minutes.
