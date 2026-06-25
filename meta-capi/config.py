"""Configuration for the Meta Conversions API (CAPI) sender.

Server-side counterpart to ads-studio: where ads-studio *reads* performance,
this *sends* conversion events (Lead, Purchase, …) straight to Meta so the ad
algorithm optimises toward people who actually convert and attribution survives
browser/iOS signal loss.

Reuses the repo-root .env so the same Meta credentials power both. Pure-Python,
no native deps — runs on the locked-down corporate machine.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Repo-root .env (one level up) — shared with ads-studio / cx-command-center.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

# --------------------------------------------------------------------------
# Datasets (auto-discovered from the ad account; override in .env if they change)
#   META_PIXEL_ID            main website Pixel — browser + server share it so
#                            server events DEDUPE with the Pixel via event_id.
#   META_OFFLINE_DATASET_ID  the "Offline dataset" — CRM policy sales with value.
# --------------------------------------------------------------------------
PIXEL_ID = os.getenv("META_PIXEL_ID", "")
OFFLINE_DATASET_ID = os.getenv("META_OFFLINE_DATASET_ID", "")

# --------------------------------------------------------------------------
# Auth — a CAPI-specific token if provided, else the Marketing API token.
# A dedicated token is generated in Events Manager → dataset → Settings →
# "Generate access token"; the existing system-user token often works too.
# --------------------------------------------------------------------------
CAPI_TOKEN = os.getenv("META_CAPI_TOKEN", "") or os.getenv("META_ACCESS_TOKEN", "")
API_VERSION = os.getenv("META_API_VERSION", "v21.0")

# --------------------------------------------------------------------------
# Test mode — when set, events land ONLY in Events Manager → Test Events and are
# NOT used for optimisation/attribution. Get the code there while testing, then
# clear it for production traffic.
# --------------------------------------------------------------------------
TEST_EVENT_CODE = os.getenv("META_TEST_EVENT_CODE", "")

# Shown to Meta as the integration that produced the event (good hygiene).
PARTNER_AGENT = os.getenv("META_CAPI_PARTNER_AGENT", "ramin-os-capi/1.0")

# Default country code used to complete bare local phone numbers before hashing
# (Azerbaijan). Callers can always pass a full international number instead.
DEFAULT_COUNTRY_CODE = os.getenv("META_CAPI_DEFAULT_CC", "994")

# Resilience knobs — mirror the hardened ads-studio Meta connector.
MAX_RETRIES = int(os.getenv("META_CAPI_MAX_RETRIES", "3"))
TIMEOUT = int(os.getenv("META_CAPI_TIMEOUT", "30"))


def active_dataset() -> str:
    """The dataset CAPI posts to by default (the live website Pixel)."""
    return PIXEL_ID
