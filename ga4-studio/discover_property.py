"""List every GA4 property the configured service account can read.

Use this after granting the service account access in GA4 Admin (Property
Access Management) to find the numeric GA4_PROPERTY_ID with zero guessing —
and to set up the same connection on the VPS twin.

    python discover_property.py            # uses GA4_SERVICE_ACCOUNT_FILE from .env
    python discover_property.py <key.json> # or an explicit key path

Reads only (analytics.readonly). Prints "properties/<id>  <name>  <account>".
"""

from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCOPE = ["https://www.googleapis.com/auth/analytics.readonly"]
_ADMIN = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"


def _key_path(argv: list[str]) -> str:
    if len(argv) > 1 and argv[1].strip():
        return argv[1].strip()
    try:  # let .env supply it, same var ga4-studio uses at runtime
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(_HERE), ".env"))
    except Exception:
        pass
    return (os.getenv("GA4_SERVICE_ACCOUNT_FILE")
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")).strip()


def discover(key_path: str, retries: int = 4) -> list[tuple[str, str, str]]:
    from google.oauth2 import service_account
    import google.auth.transport.requests as tr
    import requests

    creds = service_account.Credentials.from_service_account_file(key_path, scopes=_SCOPE)
    creds.refresh(tr.Request())
    headers = {"Authorization": f"Bearer {creds.token}"}

    for attempt in range(retries):
        r = requests.get(_ADMIN, headers=headers, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"Admin API HTTP {r.status_code}: {r.text[:300]}")
        out: list[tuple[str, str, str]] = []
        for acc in r.json().get("accountSummaries", []):
            for prop in acc.get("propertySummaries", []):
                pid = (prop.get("property") or "").split("/")[-1]
                out.append((pid, prop.get("displayName", ""), acc.get("displayName", "")))
        if out:
            return out
        time.sleep(8)  # access grants take a few seconds to propagate
    return []


if __name__ == "__main__":
    key = _key_path(sys.argv)
    if not key or not os.path.exists(key):
        print(f"Açar tapılmadı: {key or '(GA4_SERVICE_ACCOUNT_FILE boşdur)'}")
        sys.exit(2)
    props = discover(key)
    if not props:
        print("Heç bir property görünmür — GA4 Admin-də service-account-a Viewer verildiyini yoxla.")
        sys.exit(1)
    print("Əlçatan GA4 property-lər:")
    for pid, name, acc in props:
        print(f"  GA4_PROPERTY_ID={pid}  |  {name}  |  hesab: {acc}")
