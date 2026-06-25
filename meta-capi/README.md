# Meta CAPI — Server-Side Conversions API for Xalq Sigorta

The sending counterpart to **ads-studio**. Where ads-studio *reads* Meta Ads
performance, this *sends* conversion events (Lead, Purchase, …) straight to a
Meta dataset over the Conversions API (CAPI).

Why it matters:
- **Better optimisation** — Meta's algorithm learns from who actually converts
  (a sent lead, a closed policy), not just browser pixel fires.
- **Signal recovery** — server events survive ad-blockers, iOS ITP and cookie
  loss; paired with the browser Pixel via `event_id` they **deduplicate** so a
  conversion is counted once.
- **Offline → online** — push real CRM policy sales (with premium value) back to
  Meta so ROAS becomes measurable and lookalikes get smarter.

> Pure-Python (`requests` + `hashlib`). No native deps — runs on the locked-down
> corporate machine. Reuses the repo-root `.env` Meta credentials.

## Coverage strategy — which events need a CAPI twin

Sending *everything* through both Pixel and CAPI is the wrong reflex: every
server event costs an API call, needs PII hashing, and — without good
identifiers — can *lower* aggregate match quality. The precondition for any
redundancy is **`event_id` deduplication** (below); then triage by what the
event actually drives:

| Tier | Events | What we do | Where |
|---|---|---|---|
| **1** | Purchase, Lead, key conversions | already redundant — keep it, perfect dedup + match quality | `import_sales.py`, `send_lead`/`send_purchase` |
| **2** | Funnel steps & clicks that feed **optimisation, audiences, lookalikes or a KPI report** | **add a CAPI twin** — this is where ad-blocker loss (10-30%) actually distorts data | **`gateway.py` + `capi-bridge.js`** |
| **3** | Pure UI/diagnostic clicks (scroll, low-value buttons) | leave Pixel-only — CAPI overhead isn't worth it | — |

The original gap this project closed: Tier-1 was solid, but Tier-2 events were
**Pixel-only with no backup**. The gateway below fixes exactly that.

## Datasets (auto-discovered from the ad account)

| Dataset ID | Name | Use |
|---|---|---|
| `897120645527637` | **Xalq Sigorta Pixel** | active website pixel — server dedupes with the browser pixel |
| `522709760646807` | Offline dataset | CRM / offline policy sales (`Purchase` with value) |
| `1883597102119194` | Chat Eventlər Dataseti | chat / Messenger events |
| `8205042349554559` | xalg_sigorta_log (business chats) | chat |

`META_PIXEL_ID` (website) and `META_OFFLINE_DATASET_ID` (CRM) are pre-filled in
`.env`.

## Setup (3 steps)

1. **Token** — the existing `META_ACCESS_TOKEN` is used by default. If it lacks
   permission to post to the dataset, generate a dedicated one in
   **Events Manager → dataset → Settings → Generate access token** and put it in
   `META_CAPI_TOKEN`.
2. **Verify** (sends nothing — confirms access + hashing):
   ```powershell
   .\run.ps1
   ```
3. **Fire a real test event** — grab the code from **Events Manager → Test
   Events**, put it in `META_TEST_EVENT_CODE`, then:
   ```powershell
   .\run.ps1 --send
   ```
   It appears in Test Events within ~1 min and does **not** affect optimisation.
   Clear `META_TEST_EVENT_CODE` when you go to production.

## Sending events from code

```python
import capi

# A website / chat lead (raw PII in — hashing happens automatically):
capi.send_lead(
    email="customer@mail.az", phone="+994501234567",
    first_name="Aysel", last_name="M",
    action_source="website",
    event_source_url="https://xalqsigorta.az/kasko",
    event_id=pixel_event_id,        # match the browser Pixel → dedupe
    content_name="KASKO")

# A closed policy sale from the CRM (goes to the offline dataset, with value):
capi.send_purchase(
    value=480.00, currency="AZN",
    email="customer@mail.az", phone="+994501234567",
    external_id=crm_customer_id,
    content_name="KASKO 1-year", order_id=policy_no,
    action_source="system_generated")
```

## CRM policy sales → Purchase (no developer)

The first wired flow. Export the month's issued policies from the CRM to a CSV
and run the importer — each row becomes a `Purchase` on the offline dataset with
the premium as `value`. The policy number is the dedup key, so re-running the
same export never double-counts.

```powershell
# 1) Preview (hashes PII, sends nothing) — auto-detects Azerbaijani headers:
.\run.ps1   # not used here; use python directly:
.venv\Scripts\python.exe import_sales.py sales.csv

# 2) Send into Test Events first:
.venv\Scripts\python.exe import_sales.py sales.csv --send --test-code TEST12345

# 3) Go live:
.venv\Scripts\python.exe import_sales.py sales.csv --send
```

Columns (Azerbaijani **or** English headers are auto-detected; override anything
with `--map "policy_no=Polis No,premium=Məbləğ"`):

| Required | Optional |
|---|---|
| `policy_no` (Polis No), `premium` (Məbləğ) | currency (Valyuta), product (Məhsul), email, phone (Telefon), first_name (Ad), last_name (Soyad), date (Tarix), external_id (Müştəri ID/FIN) |

See [`sales_template.csv`](sales_template.csv) for the exact shape. More
identifiers per row → higher match rate (Meta matches the hashed email/phone to
the person who saw the ad).

**Where it lands & backdating.** Policy sales go to the **Offline dataset**
(`522…`) with `action_source="physical_store"`, which accepts **backdated**
conversions (~62 days) — what a monthly CRM export needs. (`system_generated`
enforces a strict 7-day window and rejects older rows with
`code 100 / subcode 2804003`; that's why we use `physical_store`.) Verify in
**Events Manager → Offline dataset → Test Events**.

## Real-time funnel events → CAPI Gateway (Tier 2)

The website Pixel fires only in the browser, so ad-blockers / ITP silently drop
the funnel steps and clicks you build audiences and optimise on. The **gateway**
is the Pixel's server-side twin: the page fires every event to **both** the
Pixel and the gateway with **one shared `event_id`**, Meta deduplicates, and the
server copy survives the blockers.

```
Pixel only            ──►  loses ad-blocked events, no backup
Pixel + the gateway   ──►  every event has a CAPI twin, deduped by event_id
```

**1. Run it** (own port, browser-facing; separate from the internal upload panel):

```powershell
.\run_gateway.ps1            # http://localhost:8812  (demo at /demo)
# safe first: set CAPI_GATEWAY_DRY_RUN=1 in the shell → builds+hashes, sends nothing
```

**2. Add to the site** — paste *after* the Meta Pixel base code, then fire events:

```html
<script src="https://YOUR-HOST:8812/capi-bridge.js" data-test="0"></script>
<script>
  capi.track('ViewContent', { content_name: 'KASKO' });
  capi.identify({ email: 'a@b.az', phone: '+994501234567' });  // when known → better match
  capi.track('Lead', { content_name: 'KASKO' });
</script>
```

The bridge generates one `event_id`, fires the Pixel with it (`eventID`), and
`sendBeacon`s the same event to the gateway. The gateway enriches it with the
data only the server reliably has — real **IP**, real **user-agent**,
**`_fbp`/`_fbc`** (read client-side from cookies; `fbc` reconstructed from a
landing `?fbclid=` when no cookie exists yet) — hashes any PII, and posts it to
the **website Pixel dataset** (the dedup target — not the offline one).

**Endpoints:** `POST /collect` · `GET /capi-bridge.js` · `GET /demo` (live,
test-mode funnel) · `GET /stats` (received/sent/failed + recent) · `GET /healthz`.

**Knobs (.env / shell):** `META_TEST_EVENT_CODE` set → everything to Test Events;
`CAPI_GATEWAY_DRY_RUN=1` → send nothing (wiring check);
`CAPI_GATEWAY_ORIGINS=https://a,https://b` → lock CORS to the real site(s).

> ⚠ The browser must call the gateway **directly** (not via a server proxy) so
> the captured IP/UA are the *visitor's*. For same-origin `_fbp/_fbc` cookie
> access, reverse-proxy it under the site domain (e.g. `/capi/`); the bridge also
> sends those cookies in the body, so it works cross-origin too.

Verify with: `.venv\Scripts\python.exe test_capi.py` (22 offline checks).

---

`send_lead` / `send_purchase` accept user identifiers as keyword args
(`email`, `phone`, `first_name`, `last_name`, `city`, `state`, `zip`,
`country`, `gender`, `dob`, `external_id`) plus the pass-through ones
(`client_ip_address`, `client_user_agent`, `fbc`, `fbp`). PII is SHA-256ed with
Meta's normalisation rules; pass-through fields are sent raw, as Meta requires.

## How it's built

```
meta-capi/
├── config.py        datasets, token, test code, retry knobs (from repo .env)
├── capi.py          PII hashing · event builder · hardened POST · send_lead/purchase/custom · build_fbc
├── import_sales.py  CRM CSV/Excel → Purchase events (offline dataset)  [Tier 1, batch]
├── web.py           internal drag-drop upload panel for import_sales (port 8811)
├── gateway.py       real-time CAPI twin of the browser Pixel (port 8812)  [Tier 2]
├── static/capi-bridge.js   drop-in dual-fire snippet (Pixel + CAPI, shared event_id)
├── templates/       conversions.html (upload panel) · bridge_demo.html (live funnel demo)
├── verify_capi.py   3-stage checker (access → dry-run hashing → optional test send)
├── test_capi.py     22 offline unit tests (hashing, fbc, custom event, gateway helpers)
├── run.ps1 / run_web.ps1 / run_gateway.ps1   launchers
└── requirements.txt requests, python-dotenv, fastapi, uvicorn, openpyxl
```

Resilience mirrors the hardened ads-studio connector: pooled session, bounded
retry on rate limits / transient 5xx with backoff + jitter, fast-fail on fatal
errors (expired token 190, permissions), and the access token scrubbed from
every error message.

## Deduplication (important)

For the **same** conversion seen by both the browser Pixel and the server, send
the **same `event_id`** from both. Meta keeps one. Website forms: read the
Pixel's `eventID` and pass it as `event_id`. Server-only events (CRM): a uuid is
generated automatically.

## Next

- Wire `send_lead` into the website/landing form handler and Meta Lead-form
  webhook (the `lead_id` from the form, plus email/phone).
- Wire `send_purchase` into the CRM "policy issued" step (premium as `value`).
- ~~A tiny FastAPI endpoint so non-Python systems can POST a conversion~~ —
  **done**: `gateway.py` + `capi-bridge.js` (Tier 2 real-time twin).
- Embed `capi-bridge.js` on the live site and pick the 2-3 funnel steps that
  actually feed optimisation / audiences to give a CAPI twin (Tier 2 above).
- Optional hardening: shared-secret / rate-limit on `/collect` if the gateway is
  exposed publicly; batch the background sends if event volume grows.
