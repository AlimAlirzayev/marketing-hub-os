"""Meta Conversions API (CAPI) — server-side event sender.

Sends conversion events (Lead, Purchase, CompleteRegistration, …) to a Meta
dataset (Pixel / Offline) over the Graph API. Handles the parts that are easy to
get wrong:

  * SHA-256 hashing of PII with Meta's exact normalisation rules (email, phone,
    name, city, …) — and the pass-through fields that must NOT be hashed
    (client_ip_address, client_user_agent, fbc, fbp).
  * event_id for deduplication against the browser Pixel (same event counted
    once, not twice).
  * test_event_code so events can be verified in Events Manager → Test Events
    without touching optimisation/attribution.
  * Bounded retry on rate limits / transient 5xx, with the access token scrubbed
    out of every error message.

Quick use:
    import capi
    capi.send_lead(
        email="a@b.az", phone="+994501234567",
        event_source_url="https://xalqsigorta.az/kasko",
        action_source="website")

Everything is pure-Python (hashlib, requests) — no native deps.
"""

from __future__ import annotations

import hashlib
import random
import re
import sys
import time
import uuid

import requests

import config

_GRAPH = "https://graph.facebook.com"

# Retry policy (same taxonomy as the hardened ads-studio connector).
_RETRYABLE_CODES = {1, 2, 4, 17, 32, 341, 613}
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}
_FATAL_CODES = {10, 100, 102, 190, 200, 272, 278, 294}

_session = requests.Session()


class CapiNotConfigured(RuntimeError):
    """Raised when a dataset id or access token is missing."""


# ============================================================================
# PII normalisation + hashing  (https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/customer-information-parameters)
# ============================================================================
# Friendly key -> (meta short key, normaliser). Normalised value is SHA-256ed.
def _norm_text(v: str) -> str:
    return v.strip().lower()


def _norm_name(v: str) -> str:
    # Lowercase, drop surrounding whitespace; keep letters (incl. AZ) only.
    return re.sub(r"[^a-zÀ-ɏə]", "", v.strip().lower())


def _norm_zip(v: str) -> str:
    return v.strip().lower().split("-")[0]


def _norm_country(v: str) -> str:
    return v.strip().lower()[:2]


def _norm_gender(v: str) -> str:
    g = v.strip().lower()
    return "f" if g in ("f", "female", "qadın", "qadin") else (
        "m" if g in ("m", "male", "kişi", "kisi") else g[:1])


def _norm_dob(v: str) -> str:
    # Accept YYYY-MM-DD / YYYYMMDD / DD.MM.YYYY -> YYYYMMDD.
    digits = re.sub(r"\D", "", v)
    if len(digits) == 8 and v.count(".") == 2:           # DD.MM.YYYY
        d, m, y = digits[:2], digits[2:4], digits[4:]
        return f"{y}{m}{d}"
    return digits[:8]


def normalize_phone(v: str, default_cc: str | None = None) -> str:
    """Digits only, with country code, no +/leading zeros — Meta's phone rule.

    Bare local Azerbaijani numbers (0xx…, or a 9-digit mobile) get the default
    country code prepended so the hash matches Meta's records.
    """
    cc = default_cc or config.DEFAULT_COUNTRY_CODE
    d = re.sub(r"\D", "", v or "")
    if not d:
        return ""
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("0"):                 # local trunk prefix -> add country code
        d = cc + d[1:]
    elif len(d) == 9 and cc == "994":     # AZ mobile typed without leading 0
        d = cc + d
    return d


# Pass-through identifiers — sent raw, never hashed.
_PASSTHROUGH = {
    "client_ip_address", "client_user_agent", "fbc", "fbp",
    "subscription_id", "fb_login_id", "lead_id",
}

# Friendly alias -> (meta key, normaliser)
_HASHED = {
    "email":       ("em", _norm_text),
    "em":          ("em", _norm_text),
    "phone":       ("ph", normalize_phone),
    "ph":          ("ph", normalize_phone),
    "first_name":  ("fn", _norm_name),
    "fn":          ("fn", _norm_name),
    "last_name":   ("ln", _norm_name),
    "ln":          ("ln", _norm_name),
    "city":        ("ct", lambda v: re.sub(r"[^a-z]", "", _norm_text(v))),
    "ct":          ("ct", lambda v: re.sub(r"[^a-z]", "", _norm_text(v))),
    "state":       ("st", lambda v: re.sub(r"[^a-z]", "", _norm_text(v))),
    "st":          ("st", lambda v: re.sub(r"[^a-z]", "", _norm_text(v))),
    "zip":         ("zp", _norm_zip),
    "zp":          ("zp", _norm_zip),
    "country":     ("country", _norm_country),
    "gender":      ("ge", _norm_gender),
    "ge":          ("ge", _norm_gender),
    "dob":         ("db", _norm_dob),
    "db":          ("db", _norm_dob),
    "external_id": ("external_id", _norm_text),  # CRM id — hashed (recommended)
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _already_hashed(v: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{64}", v or ""))


def hash_user_data(raw: dict) -> dict:
    """Turn friendly user fields into Meta's hashed `user_data` object.

    Accepts both friendly (email, phone, first_name…) and short (em, ph, fn…)
    keys. PII is normalised then SHA-256ed; ip/ua/fbc/fbp/subscription_id pass
    through untouched. Values already SHA-256ed are left as-is (idempotent).
    """
    out: dict = {}
    for key, value in (raw or {}).items():
        if value in (None, ""):
            continue
        if key in _PASSTHROUGH:
            out[key] = value
            continue
        spec = _HASHED.get(key)
        if not spec:
            # Unknown key — pass through so callers can use future fields.
            out[key] = value
            continue
        meta_key, norm = spec
        values = value if isinstance(value, (list, tuple)) else [value]
        hashed = []
        for item in values:
            s = str(item)
            if _already_hashed(s):
                hashed.append(s.lower())
                continue
            n = norm(s)
            if not n:          # junk that normalises to nothing (e.g. "-", "n/a")
                continue
            hashed.append(_sha256(n))
        if hashed:
            out[meta_key] = hashed if len(hashed) > 1 else hashed[0]
    return out


# ============================================================================
# Click-id helper
# ============================================================================
def build_fbc(fbclid: str, click_time_ms: int | None = None) -> str:
    """Build Meta's ``fbc`` parameter from a landing-page ``fbclid`` query value.

    Format: ``fb.1.<unix_ms>.<fbclid>``. Useful when a user arrives from an ad
    click but the browser has not written an ``_fbc`` cookie yet (first
    pageview): reconstructing fbc here recovers the click → big match-quality and
    attribution win. Returns "" for empty input so callers can pass it straight
    into user_data.
    """
    if not fbclid:
        return ""
    ts = int(click_time_ms if click_time_ms is not None else time.time() * 1000)
    return f"fb.1.{ts}.{fbclid}"


# ============================================================================
# Event building
# ============================================================================
def build_event(event_name: str, *,
                event_time: int | None = None,
                action_source: str = "website",
                user_data: dict | None = None,
                custom_data: dict | None = None,
                event_id: str | None = None,
                event_source_url: str | None = None,
                opt_out: bool | None = None,
                already_hashed: bool = False) -> dict:
    """Assemble one CAPI event object.

    ``event_id`` should equal the browser Pixel's eventID for the same action so
    Meta deduplicates; for server-only events a uuid is generated.
    ``already_hashed=True`` skips hashing (caller passes pre-hashed user_data).
    """
    ud = (user_data or {}) if already_hashed else hash_user_data(user_data or {})
    event: dict = {
        "event_name": event_name,
        "event_time": int(event_time or time.time()),
        "action_source": action_source,
        "event_id": event_id or uuid.uuid4().hex,
        "user_data": ud,
    }
    if event_source_url:
        event["event_source_url"] = event_source_url
    if custom_data:
        event["custom_data"] = custom_data
    if opt_out is not None:
        event["opt_out"] = opt_out
    return event


# ============================================================================
# Sending (hardened POST)
# ============================================================================
def _sanitize(text: str, token: str) -> str:
    return text.replace(token, "<REDACTED>") if token and token in text else text


def _backoff(attempt: int) -> float:
    return min(0.5 * (2 ** attempt) + random.uniform(0, 0.5), 30.0)


def _parse_error(resp: requests.Response, token: str) -> tuple[str, bool]:
    code = None
    is_transient = False
    try:
        err = resp.json().get("error", {})
        code = err.get("code")
        is_transient = bool(err.get("is_transient"))
        detail = (f" type={err.get('type')} code={code}"
                  f" subcode={err.get('error_subcode')} msg={err.get('message')}")
    except Exception:
        detail = " body=" + (resp.text or "")[:300]
    retryable = (code not in _FATAL_CODES) and (
        resp.status_code in _RETRYABLE_HTTP or is_transient
        or code in _RETRYABLE_CODES
        or (isinstance(code, int) and 80000 <= code <= 89999))
    msg = _sanitize(f"{resp.status_code} {resp.reason} for "
                    f"{resp.url.split('?')[0]}{detail}", token)
    return msg, retryable


def _post(url: str, token: str, payload: dict) -> dict:
    """POST with bounded retry on throttle/5xx; token scrubbed from errors."""
    last = "CAPI request failed"
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            resp = _session.post(url, params={"access_token": token},
                                 json=payload, timeout=config.TIMEOUT)
        except requests.RequestException as exc:
            last = _sanitize(str(exc), token)
            if attempt < config.MAX_RETRIES:
                time.sleep(_backoff(attempt))
                continue
            raise type(exc)(last) from None
        if resp.ok:
            return resp.json()
        msg, retryable = _parse_error(resp, token)
        last = msg
        if retryable and attempt < config.MAX_RETRIES:
            wait = _backoff(attempt)
            print(f"[capi] retry {attempt + 1}/{config.MAX_RETRIES} in {wait:.1f}s — {msg}",
                  file=sys.stderr)
            time.sleep(wait)
            continue
        raise requests.HTTPError(msg) from None
    raise requests.HTTPError(last) from None


def send_events(events: list[dict], *,
                dataset_id: str | None = None,
                test_event_code: str | None = None,
                dry_run: bool = False) -> dict:
    """Send a batch of built events to a dataset.

    Returns Meta's response: {events_received, messages, fbtrace_id}. With
    ``dry_run`` nothing is sent — the fully-built payload is returned for
    inspection (used by verify_capi's safe local check).
    """
    ds = dataset_id or config.active_dataset()
    if not ds:
        raise CapiNotConfigured("No dataset configured (META_PIXEL_ID).")
    token = config.CAPI_TOKEN
    if not token:
        raise CapiNotConfigured("No token (META_CAPI_TOKEN / META_ACCESS_TOKEN).")

    code = config.TEST_EVENT_CODE if test_event_code is None else test_event_code
    payload: dict = {"data": events}
    if code:
        payload["test_event_code"] = code
    if config.PARTNER_AGENT:
        payload["partner_agent"] = config.PARTNER_AGENT

    if dry_run:
        return {"dry_run": True, "dataset": ds, "test_event_code": code or None,
                "event_count": len(events), "payload": payload}

    resp = _post(f"{_GRAPH}/{config.API_VERSION}/{ds}/events", token, payload)
    resp["_dataset"] = ds
    resp["_test"] = bool(code)
    return resp


# ============================================================================
# Convenience wrappers for the conversions Xalq Sigorta cares about
# ============================================================================
def send_lead(*, user_data: dict | None = None, value: float | None = None,
              currency: str = "AZN", content_name: str | None = None,
              action_source: str = "website", event_source_url: str | None = None,
              event_id: str | None = None, event_time: int | None = None,
              dataset_id: str | None = None, test_event_code: str | None = None,
              dry_run: bool = False, **identifiers) -> dict:
    """A new lead (form submit, chat enquiry, call). Extra kwargs are treated as
    user identifiers, e.g. send_lead(email=..., phone=...)."""
    ud = {**(user_data or {}), **identifiers}
    custom: dict = {}
    if value is not None:
        custom.update(value=value, currency=currency)
    if content_name:
        custom["content_name"] = content_name
    ev = build_event("Lead", event_time=event_time, action_source=action_source,
                     user_data=ud, custom_data=custom or None, event_id=event_id,
                     event_source_url=event_source_url)
    return send_events([ev], dataset_id=dataset_id,
                       test_event_code=test_event_code, dry_run=dry_run)


def send_custom_event(event_name: str, *, user_data: dict | None = None,
                      custom_data: dict | None = None, event_id: str | None = None,
                      action_source: str = "website", event_source_url: str | None = None,
                      event_time: int | None = None, dataset_id: str | None = None,
                      test_event_code: str | None = None, dry_run: bool = False,
                      already_hashed: bool = False, **identifiers) -> dict:
    """Generic sender for any funnel-step or custom event — ``ViewContent``,
    ``Search``, ``InitiateCheckout``, a custom ``Step2_FormStart``, a button click…

    This is the server-side twin of a browser Pixel fire. Pass the **same**
    ``event_id`` the Pixel used so Meta deduplicates and counts the action once.
    Defaults to the **website Pixel** dataset (where the browser Pixel lives) —
    NOT the offline dataset — because that is what dedup matches against.

    Extra kwargs are treated as user identifiers, e.g.
    ``send_custom_event("ViewContent", email=..., fbp=...)``.
    """
    ud = {**(user_data or {}), **identifiers}
    ev = build_event(event_name, event_time=event_time, action_source=action_source,
                     user_data=ud, custom_data=custom_data or None, event_id=event_id,
                     event_source_url=event_source_url, already_hashed=already_hashed)
    return send_events([ev], dataset_id=dataset_id,
                       test_event_code=test_event_code, dry_run=dry_run)


def send_purchase(*, value: float, currency: str = "AZN",
                  user_data: dict | None = None, content_name: str | None = None,
                  order_id: str | None = None, action_source: str = "system_generated",
                  event_source_url: str | None = None, event_id: str | None = None,
                  event_time: int | None = None, dataset_id: str | None = None,
                  test_event_code: str | None = None, dry_run: bool = False,
                  **identifiers) -> dict:
    """A closed sale — e.g. a policy sold in the CRM. Defaults to the offline
    dataset when one is configured so it lands where finance/optimisation expect."""
    ud = {**(user_data or {}), **identifiers}
    custom: dict = {"value": value, "currency": currency}
    if content_name:
        custom["content_name"] = content_name
    if order_id:
        custom["order_id"] = order_id
    ds = dataset_id or (config.OFFLINE_DATASET_ID or config.active_dataset())
    ev = build_event("Purchase", event_time=event_time, action_source=action_source,
                     user_data=ud, custom_data=custom, event_id=event_id,
                     event_source_url=event_source_url)
    return send_events([ev], dataset_id=ds,
                       test_event_code=test_event_code, dry_run=dry_run)


def build_policy_sale(*, premium: float | None = None, policy_no: str,
                      product: str | None = None,
                      currency: str = "AZN", sale_time: int | None = None,
                      action_source: str = "physical_store",
                      user_data: dict | None = None, **identifiers) -> dict:
    """One sold insurance policy as a Purchase event (no send — for batching).

    ``event_id`` is derived from the policy number so re-importing the same CRM
    export never double-counts the sale. ``premium`` is optional: with it Meta
    can measure ROAS / optimise on value; without it the sale still counts as a
    conversion the algorithm optimises toward.

    Default ``action_source="physical_store"`` (offline) — unlike
    ``system_generated`` it lets the offline dataset accept **backdated** sales
    (Meta allows ~62 days), which a monthly CRM export needs. ``system_generated``
    enforces a strict 7-day freshness window and rejects older rows.
    """
    ud = {**(user_data or {}), **identifiers}
    # Meta requires value+currency on a Purchase (value-less → subcode 2804010).
    # When the export has no premium we send value=0 as an honest "amount unknown"
    # placeholder: the sale still counts as a conversion, ROAS just reads 0.
    custom: dict = {
        "order_id": policy_no,
        "value": premium if premium is not None else 0.0,
        "currency": currency,
    }
    if product:
        custom["content_name"] = product
    return build_event("Purchase", event_time=sale_time, action_source=action_source,
                       user_data=ud, custom_data=custom,
                       event_id=f"policy:{policy_no}")


def send_policy_sale(*, premium: float | None = None, policy_no: str,
                     product: str | None = None,
                     currency: str = "AZN", sale_time: int | None = None,
                     action_source: str = "physical_store",
                     user_data: dict | None = None, dataset_id: str | None = None,
                     test_event_code: str | None = None, dry_run: bool = False,
                     **identifiers) -> dict:
    """Send a single sold policy. Goes to the offline dataset by default."""
    ev = build_policy_sale(premium=premium, policy_no=policy_no, product=product,
                           currency=currency, sale_time=sale_time,
                           action_source=action_source, user_data=user_data,
                           **identifiers)
    ds = dataset_id or (config.OFFLINE_DATASET_ID or config.active_dataset())
    return send_events([ev], dataset_id=ds,
                       test_event_code=test_event_code, dry_run=dry_run)
