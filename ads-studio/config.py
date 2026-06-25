"""Central configuration for Ads Studio.

Single source of truth for branding, business targets, currency, and the data
source mode. Everything the dashboard, analytics and connectors need to agree on
lives here so the UI, the demo engine and the live Meta/Gmail adapters stay in
lock-step.

Nothing here pulls heavy/native deps - it is safe to import from anywhere.
"""

from __future__ import annotations

import os
from datetime import date

from dotenv import load_dotenv

# Load the repo-root .env (one level up from ads-studio/) so we reuse the same
# keys the rest of Xalq Insurance Digital OS already has (GEMINI_API_KEY, etc.).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

# --------------------------------------------------------------------------
# Account / brand
# --------------------------------------------------------------------------
ACCOUNT_NAME = os.getenv("ADS_ACCOUNT_NAME", "Xalq Sigorta")
ACCOUNT_TAGLINE = os.getenv("ADS_ACCOUNT_TAGLINE", "Meta Ads · Performans Hesabatı")
CURRENCY = os.getenv("ADS_CURRENCY", "USD")
CURRENCY_SYMBOL = {"USD": "$", "AZN": "₼", "EUR": "€"}.get(CURRENCY, "$")

# Xalq Sigorta brand palette (mirrors social-studio/brand_kit/colors.json).
BRAND = {
    "red": "#E31E24",
    "red_dark": "#B3171C",
    "charcoal": "#2B2A29",
    "ink": "#1C1B17",
    "burgundy": "#5C0F12",
    "white": "#FFFFFF",
    # Soft accents used only inside the dashboard chrome (not brand fills).
    "bg": "#F5F6F8",
    "card": "#FFFFFF",
    "muted": "#6B7280",
    "line": "#E5E7EB",
    "green": "#16A34A",
    "amber": "#F59E0B",
    "blue": "#2563EB",
}

# --------------------------------------------------------------------------
# Business targets - drive the "budget pacing + forecast" pro feature.
# These are intentionally editable: a marketing lead sets the monthly plan here.
# --------------------------------------------------------------------------
MONTHLY_BUDGET = float(os.getenv("ADS_MONTHLY_BUDGET", "2500"))
TARGET_LEADS = int(os.getenv("ADS_TARGET_LEADS", "1800"))
TARGET_MESSAGES = int(os.getenv("ADS_TARGET_MESSAGES", "850"))
# Acceptable cost-per-lead ceiling; pacing flags red if the run-rate exceeds it.
MAX_CPL = float(os.getenv("ADS_MAX_CPL", "1.80"))

# --------------------------------------------------------------------------
# Data source
#   demo -> deterministic synthetic data (no credentials needed)
#   live -> real Meta Marketing API + Gmail invoices (when configured)
# Auto-detects: if a Meta token + ad account are present, default to live.
# --------------------------------------------------------------------------
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")  # e.g. act_1234567890
META_API_VERSION = os.getenv("META_API_VERSION", "v21.0")


def _parse_accounts() -> list[dict]:
    """Build the multi-account list. Sources, in order of priority:
      META_AD_ACCOUNTS="act_111|Xalq Sigorta, act_222|Client X"   (multi)
      META_AD_ACCOUNT_ID="act_111"                                 (single, fallback)
    Each entry: {"id": "act_...", "label": "..."}
    """
    raw = os.getenv("META_AD_ACCOUNTS", "").strip()
    if raw:
        out = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if "|" in part:
                acc_id, label = (s.strip() for s in part.split("|", 1))
            else:
                acc_id, label = part, part
            out.append({"id": acc_id, "label": label})
        return out
    if META_AD_ACCOUNT_ID:
        return [{"id": META_AD_ACCOUNT_ID, "label": ACCOUNT_NAME}]
    return [{"id": "demo_account", "label": ACCOUNT_NAME + " (demo)"}]


AD_ACCOUNTS = _parse_accounts()
DEFAULT_ACCOUNT_ID = AD_ACCOUNTS[0]["id"]

_explicit_mode = os.getenv("ADS_DATA_MODE", "").lower()
if _explicit_mode in ("demo", "live"):
    DATA_MODE = _explicit_mode
elif META_ACCESS_TOKEN and META_AD_ACCOUNT_ID:
    DATA_MODE = "live"
else:
    DATA_MODE = "demo"

# --------------------------------------------------------------------------
# AI assistant - reuse the live, free Gemini key already in Xalq Insurance Digital OS .env.
# --------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("MODEL_FREE_BULK", "gemini-3.5-flash")

# --------------------------------------------------------------------------
# Localisation - Azerbaijani month labels for the period selector.
# --------------------------------------------------------------------------
AZ_MONTHS = [
    "", "Yanvar", "Fevral", "Mart", "Aprel", "May", "İyun",
    "İyul", "Avqust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr",
]

# How many months of history the demo engine / selector exposes.
HISTORY_MONTHS = int(os.getenv("ADS_HISTORY_MONTHS", "6"))

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")


def month_label(ym: str) -> str:
    """'2026-04' -> 'Aprel 2026'."""
    y, m = ym.split("-")
    return f"{AZ_MONTHS[int(m)]} {y}"


def today() -> date:
    """Override-able 'now' so demos/tests can pin a date via ADS_TODAY."""
    override = os.getenv("ADS_TODAY")
    if override:
        return date.fromisoformat(override)
    return date.today()
