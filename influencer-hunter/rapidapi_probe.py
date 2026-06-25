r"""RapidAPI capability probe — the "many-armed" discovery tool.

Given the key in .env, it pings every built-in host adapter with one tiny call
for a known public handle and reports which hosts the key actually unlocks, the
rate-limit headers, and whether the response parses into a real profile. This is
how you turn "I subscribed to something on RapidAPI" into a concrete, wired
capability — without guessing.

Usage:
    ..\.venv\Scripts\python.exe rapidapi_probe.py            # live probe (needs RAPIDAPI_KEY)
    ..\.venv\Scripts\python.exe rapidapi_probe.py --offline  # just list the adapter registry
"""

from __future__ import annotations

import sys

import httpx

import config
import sources_rapidapi as rapid

# Well-known public handles used only to test that a host responds at all.
_PROBE_HANDLE = {"instagram": "instagram", "tiktok": "tiktok"}
_QUOTA_HEADERS = (
    "x-ratelimit-requests-limit", "x-ratelimit-requests-remaining",
    "x-ratelimit-rapid-free-plans-hard-limit-remaining",
)


def _list_adapters() -> None:
    print("=== built-in RapidAPI adapters ===")
    for a in rapid.ADAPTERS:
        print(f"  [{a.platform}] {a.name}  host={a.host}")
        print(f"       profile: {a.profile_path}")
        if a.posts_path:
            print(f"       posts:   {a.posts_path}")
    print("\nWire a new host by appending a RapidAdapter in sources_rapidapi.py.")


def _probe_one(a: rapid.RapidAdapter) -> None:
    user = _PROBE_HANDLE.get(a.platform, "instagram")
    url = f"https://{a.host}{a.profile_path.format(user=user)}"
    try:
        r = httpx.get(url, headers={"X-RapidAPI-Key": config.RAPIDAPI_KEY, "X-RapidAPI-Host": a.host},
                      timeout=config.RAPIDAPI_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        print(f"  [{a.platform}] {a.name:28} NETWORK-ERR  {type(exc).__name__}: {str(exc)[:80]}")
        return

    quota = " ".join(f"{h.split('-')[-1]}={r.headers[h]}" for h in _QUOTA_HEADERS if h in r.headers)
    if r.status_code == 200:
        parsed = None
        try:
            parsed = rapid.build_profile(a, user, r.json())
        except Exception:  # noqa: BLE001
            pass
        ok = parsed is not None and parsed.followers is not None
        flag = "OK  followers=%s" % parsed.followers if ok else "200 but UNPARSED (check field map)"
        print(f"  [{a.platform}] {a.name:28} {flag}   {quota}")
    elif r.status_code in (401, 403):
        print(f"  [{a.platform}] {a.name:28} NOT-SUBSCRIBED ({r.status_code}) -> subscribe to its free plan on RapidAPI")
    elif r.status_code == 429:
        print(f"  [{a.platform}] {a.name:28} RATE-LIMITED (429)   {quota}")
    else:
        print(f"  [{a.platform}] {a.name:28} HTTP {r.status_code}   {r.text[:80]}")


def main() -> None:
    if "--offline" in sys.argv:
        _list_adapters()
        return
    if not config.RAPIDAPI_KEY:
        print("RAPIDAPI_KEY yoxdur. Addımlar:")
        print("  1. https://rapidapi.com/hub -> hesab aç (pulsuz)")
        print("  2. Bir social host seç (məs. instagram-scraper-api2, tiktok-scraper7) -> Subscribe -> Basic (Free)")
        print("  3. Dashboard-dakı 'X-RapidAPI-Key'-i kopyala")
        print("  4. .env-ə əlavə et:  RAPIDAPI_KEY=...")
        print("  5. yenidən işə sal:  python rapidapi_probe.py")
        print()
        _list_adapters()
        return
    print(f"=== probing {len(rapid.ADAPTERS)} hosts with the configured key ===")
    for a in rapid.ADAPTERS:
        _probe_one(a)
    print("\nOK = key unlocks it now. NOT-SUBSCRIBED = open its RapidAPI page and Subscribe (free).")


if __name__ == "__main__":
    main()
