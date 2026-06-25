# GA4 Studio — Website Analytics for Marketing OS

The on-site truth that neither Meta nor Google Ads sees. Where **ads-studio**
reads *paid* performance, this reads *website behaviour* from **Google Analytics
4**: who arrives, from which channel, which pages leak, and which sessions
convert. First piece of the Google-side stack we're adding to Marketing OS.

> Pure-Python (`requests` + `fastapi`). Demo mode needs **no credentials**; live
> mode lazily imports `google-auth` (pure wheels — no grpc / no GA4 SDK) so it
> installs on the locked-down corporate machine. Reuses the repo-root `.env`.

## Run

```powershell
.\run.ps1            # http://localhost:8850
```

Out of the box it runs in **DEMO** mode (clearly badged) with realistic,
deterministic data — so the whole dashboard is reviewable before any Google
setup. The header badge shows **DEMO** (amber) or **CANLI** (green + property id).

## What it shows

- **KPIs** with period-over-period deltas: sessions, users, conversions,
  conversion rate, engagement rate, avg engagement time.
- **Daily trend** (sessions + conversions).
- **Channels** — where traffic comes from *and which converts best* (the budget
  signal).
- **Engagement funnel** — sessions → engaged → conversions, with drop-off.
- **Top pages** — views + avg engagement; low-engagement pages flagged as leaks.
- **Devices & cities**, **automatic insights** (rule-based, every claim ties to a
  number in the report — no fabrication), and an on-demand **Gemini AI summary**.

## Going live (one-time, ~10 min, free)

GA4's Data API is free. Use a **service account** (no user login, no token
expiry):

1. **Google Cloud Console** → create (or pick) a project → **Enable** the
   *Google Analytics Data API*.
2. **IAM & Admin → Service Accounts** → create one → **Keys → Add key → JSON** →
   download the file. Save it somewhere readable (e.g. `ga4-studio/secrets/ga4.json`).
3. **GA4 → Admin → Property Access Management** → add the service-account email
   (looks like `…@….iam.gserviceaccount.com`) with the **Viewer** role.
4. Find the **Property ID** (GA4 → Admin → Property Settings — a number like
   `493xxxxxx`; *not* the `G-XXXX` measurement id).
5. Put both in the repo-root `.env`:

   ```
   GA4_PROPERTY_ID=493xxxxxx
   GA4_SERVICE_ACCOUNT_FILE=C:\Users\a.alirzayev\ramin-os\ga4-studio\secrets\ga4.json
   ```

6. Restart — it auto-detects credentials and flips to **CANLI**. Force a mode any
   time with `GA4_DATA_MODE=demo|live`.

The dashboard's DEMO badge tooltip lists exactly what's missing until then.

## How it's built

```
ga4-studio/
├── config.py              brand, property/auth, demo↔live auto-detect, AZ labels
├── connectors/
│   ├── __init__.py        get_report(start,end) → routes to demo or live
│   ├── demo.py            deterministic synthetic GA4 report (insurance site)
│   └── ga4_live.py        service-account token → Data API runReport (REST)
├── analytics.py           deltas · funnel · honest rule-based insights · Gemini summary
├── app.py                 FastAPI: /api/report · /api/ai · /api/config · /api/health
├── templates/dashboard.html   Tailwind dashboard, DEMO/CANLI badge, SVG trend
├── tests.py               29 offline tests (shape, consistency, determinism, analytics)
├── run.ps1 / requirements.txt
```

Both connectors return the **same report dict**, so the analytics + UI never know
which source is live. Verify: `.venv\Scripts\python.exe tests.py`.

## Where this is heading

GA4 is step 1 of the Google-side stack. Next: a **unified daily briefing**
(Meta + GA4 + organic in one report — the "central brain"), then Search Console
(organic demand) and GTM (deploy Pixel/CAPI/GA4 without a developer). GA4's
conversion totals are also the neutral referee for the Meta Pixel/CAPI dedup work
in `meta-capi/`.
