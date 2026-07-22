"""Central configuration for GA4 Studio — website analytics for Marketing OS.

Where ads-studio reads *paid* performance (Meta), this reads *website behaviour*
from Google Analytics 4: who arrives, from which channel, which pages leak, and
which sessions convert. It is the on-site truth neither Meta nor Google Ads sees.

Same house rules as ads-studio: reuse the repo-root .env, a demo/live split so
the whole dashboard works with zero credentials, Xalq Sigorta brand palette,
Azerbaijani period labels. Pure-Python — no native deps in demo mode; live mode
lazily imports google-auth only when real credentials are present.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from dotenv import load_dotenv

# Repo-root .env (one level up) — shared with ads-studio / meta-capi.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

# --------------------------------------------------------------------------
# Account / brand (mirrors ads-studio so the two dashboards feel like one suite)
# --------------------------------------------------------------------------
ACCOUNT_NAME = os.getenv("GA4_ACCOUNT_NAME", "Xalq Sigorta")
ACCOUNT_TAGLINE = os.getenv("GA4_ACCOUNT_TAGLINE", "Google Analytics 4 · Vebsayt Analitikası")
SITE_DOMAIN = os.getenv("GA4_SITE_DOMAIN", "xalqsigorta.az")

BRAND = {
    "red": "#E31E24", "red_dark": "#B3171C", "charcoal": "#2B2A29",
    "ink": "#1C1B17", "burgundy": "#5C0F12", "white": "#FFFFFF",
    "bg": "#F5F6F8", "card": "#FFFFFF", "muted": "#6B7280", "line": "#E5E7EB",
    "green": "#16A34A", "amber": "#F59E0B", "blue": "#2563EB", "violet": "#7C3AED",
}

# --------------------------------------------------------------------------
# GA4 connection
#   GA4_PROPERTY_ID            numeric GA4 property id, e.g. "493xxxxxx"
#   GA4_SERVICE_ACCOUNT_FILE   path to a service-account JSON (preferred), OR
#   GOOGLE_APPLICATION_CREDENTIALS  the standard Google env var (fallback)
# Grant the service-account email "Viewer" on the GA4 property (Admin → Property
# Access Management). Scope used: analytics.readonly.
# --------------------------------------------------------------------------
PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "").strip()
SERVICE_ACCOUNT_FILE = (os.getenv("GA4_SERVICE_ACCOUNT_FILE", "")
                        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")).strip()
GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GA4_API = "https://analyticsdata.googleapis.com/v1beta"
TIMEOUT = int(os.getenv("GA4_TIMEOUT", "30"))

# Portable secret: the encrypted key vault (gateway/keyvault.py) carries the
# service-account JSON as base64 (GA4_SERVICE_ACCOUNT_JSON_B64) so the whole
# connection travels to the twin machine — a file path alone is machine-specific
# and a multi-line JSON is not a KEY=VALUE the vault can move. If the pointed-at
# file is missing but the b64 is present, materialize it locally once and use it.
_SA_B64 = os.getenv("GA4_SERVICE_ACCOUNT_JSON_B64", "").strip()
if _SA_B64 and (not SERVICE_ACCOUNT_FILE or not os.path.exists(SERVICE_ACCOUNT_FILE)):
    try:
        import base64 as _b64
        _dest = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "secrets", "ga4-service-account.json")
        os.makedirs(os.path.dirname(_dest), exist_ok=True)
        _raw = _b64.b64decode(_SA_B64)
        if not os.path.exists(_dest) or open(_dest, "rb").read() != _raw:
            with open(_dest, "wb") as _f:
                _f.write(_raw)
        SERVICE_ACCOUNT_FILE = _dest
    except Exception:
        pass  # stay in demo rather than crash on a malformed blob

# --------------------------------------------------------------------------
# Data source — demo (synthetic, no creds) vs live (real GA4). Auto-detects:
# a property id + a readable credentials file => live, unless GA4_DATA_MODE
# forces one. Mirrors ads-studio's DATA_MODE behaviour exactly.
# --------------------------------------------------------------------------
_explicit_mode = os.getenv("GA4_DATA_MODE", "").lower()
_have_creds = bool(PROPERTY_ID and SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE))
if _explicit_mode in ("demo", "live"):
    DATA_MODE = _explicit_mode
else:
    DATA_MODE = "live" if _have_creds else "demo"


def live_blockers() -> list[str]:
    """Human-readable reasons live mode is unavailable (for honest UI labels)."""
    out = []
    if not PROPERTY_ID:
        out.append("GA4_PROPERTY_ID .env-də yoxdur")
    if not SERVICE_ACCOUNT_FILE:
        out.append("Service-account JSON göstərilməyib (GA4_SERVICE_ACCOUNT_FILE)")
    elif not os.path.exists(SERVICE_ACCOUNT_FILE):
        out.append(f"Service-account faylı tapılmadı: {SERVICE_ACCOUNT_FILE}")
    return out


# --------------------------------------------------------------------------
# AI assistant — reuse the free Gemini key already in the repo .env.
# --------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("MODEL_FREE_BULK", "gemini-3.5-flash")

# --------------------------------------------------------------------------
# Localisation
# --------------------------------------------------------------------------
AZ_MONTHS = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "İyun",
             "İyul", "Avqust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"]

# GA4 channel group → Azerbaijani label for the UI.
CHANNEL_AZ = {
    "Organic Search": "Üzvi axtarış", "Paid Search": "Ödənişli axtarış",
    "Direct": "Birbaşa", "Organic Social": "Üzvi sosial",
    "Paid Social": "Ödənişli sosial", "Referral": "Yönləndirmə",
    "Email": "E-poçt", "Display": "Display", "Organic Video": "Üzvi video",
    "Unassigned": "Təyin olunmamış", "Affiliates": "Affiliate",
}


def today() -> date:
    override = os.getenv("GA4_TODAY")
    return date.fromisoformat(override) if override else date.today()


def default_range(days: int = 28) -> tuple[str, str]:
    """Last N complete days ending yesterday (GA4's freshest stable window)."""
    end = today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def range_label(start: str, end: str) -> str:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if s.year == e.year and s.month == e.month:
        return f"{s.day}–{e.day} {AZ_MONTHS[e.month]} {e.year}"
    return f"{s.day} {AZ_MONTHS[s.month]} – {e.day} {AZ_MONTHS[e.month]} {e.year}"


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
