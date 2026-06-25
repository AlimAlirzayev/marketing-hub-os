"""Offline unit tests — no network, no Meta calls. Run:

    .venv\\Scripts\\python.exe test_capi.py

Covers the parts that must be exactly right: PII hashing/normalisation, AZ phone
completion, fbc reconstruction, the generic custom-event builder (dedup id +
website-dataset routing), and the gateway's request-enrichment helpers.
"""

from __future__ import annotations

import hashlib
import os
import sys

os.environ.setdefault("CAPI_GATEWAY_DRY_RUN", "1")  # gateway import must not send

import capi
import gateway

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  ✓ {name}")
    else:
        _FAIL += 1
        print(f"  ✗ {name}  {detail}")


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# --- PII hashing -----------------------------------------------------------
ud = capi.hash_user_data({
    "email": "  Test.Lead@Example.com ",
    "phone": "0501234567",
    "first_name": "Aysel",
    "client_user_agent": "ua/1.0",
    "fbp": "fb.1.123.456",
})
check("email normalised (trim+lower) then sha256",
      ud["em"] == sha("test.lead@example.com"), ud.get("em"))
check("AZ local phone gets 994 + sha256",
      ud["ph"] == sha("994501234567"), ud.get("ph"))
check("name lowercased + sha256", ud["fn"] == sha("aysel"))
check("client_user_agent passes through unhashed", ud["client_user_agent"] == "ua/1.0")
check("fbp passes through unhashed", ud["fbp"] == "fb.1.123.456")

check("already-hashed value is left as-is (idempotent)",
      capi.hash_user_data({"em": sha("a@b.az")})["em"] == sha("a@b.az"))
check("junk that normalises to nothing is dropped",
      "ph" not in capi.hash_user_data({"phone": "n/a"}))

# --- phone normalisation edge cases ---------------------------------------
check("9-digit AZ mobile without 0 gets 994",
      capi.normalize_phone("501234567") == "994501234567")
check("00-prefixed international is cleaned",
      capi.normalize_phone("00994501234567") == "994501234567")
check("already full international untouched",
      capi.normalize_phone("994501234567") == "994501234567")

# --- fbc reconstruction ----------------------------------------------------
fbc = capi.build_fbc("AbCd123", click_time_ms=1700000000000)
check("build_fbc format fb.1.<ms>.<fbclid>", fbc == "fb.1.1700000000000.AbCd123", fbc)
check("build_fbc empty input -> empty", capi.build_fbc("") == "")

# --- generic custom-event builder (dry-run, no send) ----------------------
res = capi.send_custom_event(
    "ViewContent", email="a@b.az", custom_data={"content_name": "KASKO"},
    event_id="evt-123", dataset_id="DS_TEST", dry_run=True)
ev = res["payload"]["data"][0]
check("custom event name carried", ev["event_name"] == "ViewContent")
check("shared event_id preserved for dedup", ev["event_id"] == "evt-123")
check("custom event routed to given dataset", res["dataset"] == "DS_TEST")
check("custom event PII hashed", ev["user_data"]["em"] == sha("a@b.az"))
check("custom_data carried", ev["custom_data"]["content_name"] == "KASKO")

# --- gateway helpers -------------------------------------------------------
class FakeReq:
    def __init__(self, headers=None, host="9.9.9.9", cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client = type("C", (), {"host": host})()

check("client ip from X-Forwarded-For (first hop)",
      gateway._client_ip(FakeReq({"x-forwarded-for": "1.2.3.4, 5.6.7.8"})) == "1.2.3.4")
check("client ip falls back to socket peer",
      gateway._client_ip(FakeReq(host="8.8.8.8")) == "8.8.8.8")
check("fbc reconstructed from fbclid in url",
      gateway._fbc_from_url("https://x.az/kasko?fbclid=ZZ").startswith("fb.1."))
check("no fbclid -> no fbc", gateway._fbc_from_url("https://x.az/kasko") == "")
check("gateway imported in DRY_RUN (safe)", gateway.DRY_RUN is True)

print(f"\n  {_PASS} passed, {_FAIL} failed")
sys.exit(1 if _FAIL else 0)
