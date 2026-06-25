"""One-off helper: mint a Google Ads API refresh token.

Reads GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET from the repo-root .env,
opens a browser for consent (scope: adwords), and prints the refresh token to
paste back into .env as GOOGLE_ADS_REFRESH_TOKEN.

    cd ads-studio
    .\\.venv\\Scripts\\python.exe generate_refresh_token.py

Requires: pip install google-auth-oauthlib (pulled in by google-ads).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main() -> int:
    client_id = os.getenv("GOOGLE_ADS_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print("Set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET in .env first.")
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Run: pip install google-auth-oauthlib")
        return 1

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=_SCOPES,
    )
    creds = flow.run_local_server(port=0, prompt="consent")
    print("\n=== Add this to .env ===")
    print(f"GOOGLE_ADS_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
