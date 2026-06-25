# Google Ads API — credential setup (one-time)

Ads Studio can **create** Google campaigns programmatically (not just read Meta
reports). Creation uses the official **Google Ads API**. This file is the
checklist for the credentials — the only part a human must do. Once these land
in the repo-root `.env`, `create_kasko_display.py` builds the campaign in
**seconds**, in **PAUSED** state (it never spends until you enable it).

> The slow item is the **developer token approval** (~1 business day). Start it
> first; everything else takes ~20 minutes.

## What you need (6 values → repo-root `.env`)

```env
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_REFRESH_TOKEN=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=   # manager (MCC) id, digits only, no dashes
GOOGLE_ADS_CUSTOMER_ID=         # the Xalq Sigorta account, digits only
```

## Steps (gcloud NOT required — all in two browser tabs)

### Step 1 — Developer token  ← START FIRST (~1 business day approval)
Done in **Google Ads** (not Cloud Console). You need a **Manager (MCC)** account
because only an MCC can hold an API developer token.

1. Open <https://ads.google.com/home/tools/manager-accounts/> → **Create a manager account** (free) if you don't already have one. Sign in with the Google account that owns the Xalq Sigorta Ads account.
2. Link the Xalq Sigorta account: inside the MCC → **Accounts → Performance → "+" → Link existing account** → enter the Xalq Sigorta Customer ID → the Xalq Sigorta owner accepts the link request.
3. In the MCC: **Tools (🔧) → Setup → API Center**. Copy the **developer token**.
4. Click **Apply for Basic access**, fill the 1-page form (describe the use case as: "Internal automation to create/manage our own Display campaigns via the Google Ads API"). Submit. Approval usually arrives next business day.

> While the token is in **Test-account access**, it only works with test accounts — it cannot touch the real Xalq Sigorta account. Everything else below can proceed in parallel; the real launch waits for Basic-access approval.

### Step 2 — Customer IDs (1 minute)
- Top-right of <https://ads.google.com/> shows the **Customer ID** as `xxx-xxx-xxxx`.
- `GOOGLE_ADS_CUSTOMER_ID` = the Xalq Sigorta account id, digits only.
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` = the MCC id (digits only). If there is no MCC, set it equal to the customer id.

### Step 3 — Google Cloud OAuth client (~5 minutes, all in browser)
Use the **same Google account** as the one that owns the Ads access.

1. **Create a project** → <https://console.cloud.google.com/projectcreate> · name it `Xalq Sigorta Ads` → **Create**. Select it in the top dropdown.
2. **Enable the Google Ads API** → <https://console.cloud.google.com/apis/library/googleads.googleapis.com> → **Enable**.
3. **Configure the OAuth consent screen** → <https://console.cloud.google.com/apis/credentials/consent> · User Type **External → Create** · App name `Xalq Sigorta Ads` · user support email + developer email = your Google email · **Save and Continue** through Scopes (no scopes needed here — we ask for `adwords` at runtime) · on **Test users** → **Add Users** → add your own Google email → **Save**.
4. **Create the Desktop OAuth client** → <https://console.cloud.google.com/apis/credentials> · **Create Credentials → OAuth client ID** · Application type **Desktop app** · name `Xalq Sigorta Desktop` · **Create**. Copy the popup's **Client ID** + **Client secret**.

### Step 4 — Put what you have into .env so far
Open the repo-root `.env` and fill what you've collected. Leave the rest empty for now:

```env
GOOGLE_ADS_DEVELOPER_TOKEN=<from Step 1, even if still "test" — it works for the next step>
GOOGLE_ADS_CLIENT_ID=<from Step 3.4>
GOOGLE_ADS_CLIENT_SECRET=<from Step 3.4>
GOOGLE_ADS_LOGIN_CUSTOMER_ID=<MCC id, digits only>
GOOGLE_ADS_CUSTOMER_ID=<Xalq Sigorta id, digits only>
# GOOGLE_ADS_REFRESH_TOKEN will be filled in Step 5
```

### Step 5 — Mint the refresh token (~30 seconds)
```powershell
cd ads-studio
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # one-time
.\.venv\Scripts\python.exe generate_refresh_token.py
```
A browser tab opens → sign in with the same Google account → **Allow** the requested `adwords` scope. The script prints `GOOGLE_ADS_REFRESH_TOKEN=...` — paste it into `.env`.

### Step 6 — Verify auth
```powershell
.\.venv\Scripts\python.exe -c "from connectors.google_ads import build_client; build_client(); print('Google Ads auth OK')"
```
If `Google Ads auth OK` prints, the wiring is correct. You can build campaigns now; whether they go live depends only on **Step 1's Basic-access approval**.

## Then create the KASKO campaign

```powershell
.\.venv\Scripts\python.exe create_kasko_display.py
```

This creates a **PAUSED** Display campaign ($10/day, Azerbaijan, auto-interest
audience, → the Instagram KASKO post). Review it in the Google Ads UI, then
enable it there (or re-run with `--enable` after you approve). Nothing spends
until it is enabled — the checkpoint principle.

## Note on the creative
Responsive Display ads need image assets:
- **Square 1:1** (min 300×300, rec 1200×1200) — the KASKO post image
- **Landscape 1.91:1** (min 600×314, rec 1200×628) — a wide crop of the creative
- **Logo 1:1** (min 128×128) — Xalq Sigorta logo

Put them in `ads-studio/assets/kasko/` as `square.jpg`, `landscape.jpg`,
`logo.png`. The square post image exists; the landscape crop + logo may need to
be exported once. The script tells you exactly which file is missing.
