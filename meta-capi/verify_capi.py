"""Meta Conversions API connection + setup checker.

Stages, safest first:
  0. Show config (dataset, token, test mode).
  1. Confirm the token can reach the dataset (read-only GET).
  2. Build a synthetic Lead and DRY-RUN it — proves PII hashing + payload shape
     without sending anything.
  3. With --send, actually POST the test event. It only lands in
     Events Manager → Test Events (needs META_TEST_EVENT_CODE) and never
     affects optimisation/attribution.

    .venv\\Scripts\\python.exe verify_capi.py          # stages 0-2 (no send)
    .venv\\Scripts\\python.exe verify_capi.py --send    # also fire a test event
"""

from __future__ import annotations

import json
import sys

import requests

import capi
import config


def _mask(tok: str) -> str:
    return f"{tok[:6]}…{tok[-4:]} ({len(tok)} simvol)" if tok else "(yoxdur)"


def _check_dataset_access() -> bool:
    """GET the dataset's name — confirms the token has access to it."""
    url = f"{capi._GRAPH}/{config.API_VERSION}/{config.active_dataset()}"
    try:
        r = capi._session.get(url, params={
            "access_token": config.CAPI_TOKEN, "fields": "id,name"}, timeout=config.TIMEOUT)
    except requests.RequestException as exc:
        print(f"  ✗ Şəbəkə xətası: {capi._sanitize(str(exc), config.CAPI_TOKEN)}")
        return False
    if r.ok:
        d = r.json()
        print(f"  ✓ Dataset əlçatandır: {d.get('id')} · {d.get('name')}")
        return True
    msg, _ = capi._parse_error(r, config.CAPI_TOKEN)
    print(f"  ✗ Dataset-ə çıxış yoxdur: {msg}")
    if "code=190" in msg or "expired" in msg.lower():
        print("    → Token bitib. Events Manager → dataset → Settings →")
        print("      'Generate access token' ilə yeni CAPI token yarat, .env-də")
        print("      META_CAPI_TOKEN= sətrinə yapışdır.")
    elif "code=200" in msg or "code=10" in msg or "permission" in msg.lower():
        print("    → Token-in bu dataset-ə icazəsi yoxdur. Events Manager-də")
        print("      dataset üçün ayrıca token yarat (META_CAPI_TOKEN).")
    return False


def _synthetic_event() -> dict:
    """A clearly-synthetic Lead used only for verification."""
    return capi.build_event(
        "Lead",
        action_source="website",
        event_source_url="https://xalqsigorta.az/kasko",
        user_data={
            "email": "test.lead@example.com",
            "phone": "+994501112233",
            "first_name": "Test",
            "last_name": "Lead",
            "city": "Baku",
            "country": "AZ",
            "client_user_agent": "ramin-os-capi-verify/1.0",
        },
        custom_data={"content_name": "KASKO (test)", "value": 0, "currency": "AZN"},
    )


def main() -> int:
    send = "--send" in sys.argv
    print("=" * 64)
    print("  Meta Conversions API · quraşdırma yoxlaması")
    print("=" * 64)
    print(f"  Dataset (Pixel) : {config.PIXEL_ID or '(yoxdur)'}")
    print(f"  Offline dataset : {config.OFFLINE_DATASET_ID or '(yoxdur)'}")
    print(f"  Token           : {_mask(config.CAPI_TOKEN)}")
    print(f"  Test event code : {config.TEST_EVENT_CODE or '(yoxdur — production rejimi)'}")
    print(f"  API version     : {config.API_VERSION}")

    if not config.PIXEL_ID:
        print("\n  ✗ META_PIXEL_ID .env-də yoxdur. Aktiv pixel: 897120645527637")
        print("    (Xalq Sigorta Pixel). .env-ə əlavə et və yenidən işə sal.\n")
        return 1
    if not config.CAPI_TOKEN:
        print("\n  ✗ Token yoxdur (META_CAPI_TOKEN və ya META_ACCESS_TOKEN).\n")
        return 1

    # Stage 1 — token reaches the dataset.
    print("\n  [1/3] Dataset-ə çıxış yoxlanılır…")
    if not _check_dataset_access():
        return 2

    # Stage 2 — build + hash + dry-run (always safe).
    print("\n  [2/3] Test hadisəsi qurulur (DRY-RUN, heç nə göndərilmir)…")
    ev = _synthetic_event()
    dry = capi.send_events([ev], dry_run=True)
    ud = ev["user_data"]
    print(f"        event_name = {ev['event_name']}   event_id = {ev['event_id']}")
    print(f"        action_source = {ev['action_source']}")
    print( "        user_data (SHA-256 hash-lənmiş, raw PII GETMİR):")
    for k in ("em", "ph", "fn", "ln", "ct", "country"):
        if k in ud:
            print(f"          {k:<3} = {ud[k][:24]}…")
    if "client_user_agent" in ud:
        print(f"          client_user_agent = {ud['client_user_agent']} (hash-siz, düzgün)")
    print(f"        payload düzgün quruldu ({dry['event_count']} hadisə).")

    # Stage 3 — optional real send to Test Events.
    if not send:
        print("\n  [3/3] Göndərmə ötürüldü. Real test üçün:")
        print("        1) Events Manager → dataset → Test Events → 'Test event code'-u kopyala.")
        print("        2) .env-də META_TEST_EVENT_CODE= sətrinə yapışdır.")
        print("        3) Yenidən: python verify_capi.py --send")
        print("\n" + "=" * 64)
        print("  ✓ Hazırlıq OK — token işləyir, hashing düzgün, payload valid.")
        print("=" * 64 + "\n")
        return 0

    print("\n  [3/3] Test hadisəsi göndərilir…")
    if not config.TEST_EVENT_CODE:
        print("        ⚠ META_TEST_EVENT_CODE yoxdur — bu REAL (production) hadisə olacaq.")
    try:
        resp = capi.send_events([ev])
    except Exception as exc:
        print(f"        ✗ Göndərmə uğursuz: {exc}\n")
        return 3
    print(f"        ✓ Meta qəbul etdi: events_received={resp.get('events_received')}  "
          f"fbtrace_id={resp.get('fbtrace_id')}")
    if resp.get("messages"):
        print(f"        messages: {json.dumps(resp['messages'], ensure_ascii=False)}")
    print("\n" + "=" * 64)
    if config.TEST_EVENT_CODE:
        print("  ✓ GÖNDƏRİLDİ — Events Manager → Test Events-də 1-2 dəqiqəyə görünəcək.")
    else:
        print("  ✓ GÖNDƏRİLDİ (production). Events Manager → Overview-da görünəcək.")
    print("=" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
