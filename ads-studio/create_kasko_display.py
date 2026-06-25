"""Create the KASKO Qurban-Bayram Google Display campaign (PAUSED).

Run from the ads-studio/ folder once the GOOGLE_ADS_* creds are in the repo .env
(see GOOGLE_ADS_SETUP.md):

    .\\.venv\\Scripts\\python.exe create_kasko_display.py                 # create PAUSED
    .\\.venv\\Scripts\\python.exe create_kasko_display.py --find-audiences # list audience ids
    .\\.venv\\Scripts\\python.exe create_kasko_display.py --enable RES     # enable after review

The campaign is created PAUSED. It spends nothing until you enable it (here with
--enable, or in the Google Ads UI) — the checkpoint principle.
"""

from __future__ import annotations

import sys
from pathlib import Path

from connectors.google_ads import (
    DisplayCampaignSpec,
    GoogleAdsNotConfigured,
    build_client,
    create_display_campaign,
    enable_campaign,
    find_user_interests,
)

_ASSETS = Path(__file__).resolve().parent / "assets" / "kasko"

# Copy approved by the user (Azerbaijani). Google limits: headline <=30,
# long headline <=90, description <=90, business name <=25.
KASKO_SPEC = DisplayCampaignSpec(
    name="KASKO Bayram - Display - 25-31 May",
    final_url="https://www.instagram.com/p/DYobvDpCR8Q/",
    daily_budget=10.0,                       # $10/day (user-confirmed)
    location_name="Azerbaijan",
    language_codes=["az", "ru"],
    age_min=25,
    age_max=60,
    business_name="Xalq Sigorta",
    headlines=[
        "KASKO-ya özəl bayram təklifi",
        "KASKO al, yanacaq hədiyyə",
        "Xalq Sığorta — KASKO",
        "Azpetrol kartı hədiyyə",
        "Bayram hədiyyəsi qazan",
    ],
    long_headline="Qurban bayramına özəl: KASKO al, Azpetrol yanacaq kartı hədiyyə qazan",
    descriptions=[
        "25 may–5 iyun: KASKO etdir, Azpetrol yanacaq kartı hədiyyə qazan.",
        "Avtomobilini Xalq Sığorta ilə qoru, dəyərli bayram hədiyyəsi əldə et.",
    ],
    square_image=str(_ASSETS / "square.jpg"),
    landscape_image=str(_ASSETS / "landscape.jpg"),
    logo_image=str(_ASSETS / "logo.png"),
    # Fill after running --find-audiences (in-market "Vehicle Insurance",
    # "Motor Vehicles"; affinity "Auto Enthusiasts"). Empty = age targeting only.
    audience_user_interest_ids=[],
)

# Terms to surface the right in-market/affinity audiences for KASKO.
_AUDIENCE_TERMS = ["Vehicle Insurance", "Motor Vehicles", "Auto", "Car"]


def _find_audiences() -> None:
    client = build_client()
    cid = _customer_id_from_env()
    rows = find_user_interests(client, cid, _AUDIENCE_TERMS)
    if not rows:
        print("No audiences matched. Try broader terms.")
        return
    print(f"{'ID':>12}  {'TAXONOMY':<18}  NAME")
    for r in rows:
        print(f"{r['id']:>12}  {r['taxonomy']:<18}  {r['name']}")
    print("\nPut the chosen ids into KASKO_SPEC.audience_user_interest_ids, re-run.")


def _customer_id_from_env() -> str:
    import os

    return (os.getenv("GOOGLE_ADS_CUSTOMER_ID") or "").replace("-", "")


def main(argv: list[str]) -> int:
    try:
        if "--find-audiences" in argv:
            _find_audiences()
            return 0
        if "--enable" in argv:
            i = argv.index("--enable")
            res = argv[i + 1] if i + 1 < len(argv) else ""
            if not res:
                print("Usage: --enable <campaign_resource_name>")
                return 2
            print("Enabling (this STARTS spend):", enable_campaign(res))
            return 0

        result = create_display_campaign(KASKO_SPEC)
        print("Created Google Display campaign (PAUSED):")
        for k, v in result.items():
            print(f"  {k}: {v}")
        print("\nReview it in Google Ads, then enable with:")
        print(f"  python create_kasko_display.py --enable {result['campaign']}")
        return 0
    except GoogleAdsNotConfigured as exc:
        print("NOT CONFIGURED:", exc)
        return 1
    except FileNotFoundError as exc:
        print("MISSING CREATIVE:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
