"""Configuration for Customer Relations Center.

The module is deliberately dependency-light because every layer imports it:
API, storage, triage, analytics and future connectors. Values are loaded from
the repo-root .env so this app can reuse the same provider keys.
"""

from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(REPO_ROOT, ".env"), override=True)

APP_NAME = os.getenv("CX_APP_NAME", "Customer Relations Center")
ACCOUNT_NAME = os.getenv("CX_ACCOUNT_NAME", "Xalq Sigorta")
ACCOUNT_TAGLINE = os.getenv(
    "CX_ACCOUNT_TAGLINE",
    "Complaint radar, AI triage, SLA and customer recovery",
)
DATA_MODE = os.getenv("CX_DATA_MODE", "demo").lower()
DATABASE_PATH = os.getenv("CX_DATABASE_PATH", os.path.join(BASE_DIR, "data", "cx.sqlite"))
PUBLIC_BASE_URL = os.getenv("CX_PUBLIC_BASE_URL", "").rstrip("/")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("CX_GEMINI_MODEL") or os.getenv("MODEL_FREE_BULK", "gemini-3.5-flash")
AI_ENABLED = os.getenv("CX_AI_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
AI_TIMEOUT_SECONDS = float(os.getenv("CX_AI_TIMEOUT_SECONDS", "5"))

HF_SENTIMENT_ENABLED = os.getenv("CX_HF_SENTIMENT_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
HF_SENTIMENT_ENDPOINT = os.getenv("CX_HF_SENTIMENT_ENDPOINT", "").strip()
HF_SENTIMENT_MODEL = os.getenv("CX_HF_SENTIMENT_MODEL", "").strip()
HF_SENTIMENT_ALLOW_EXTERNAL = os.getenv("CX_HF_SENTIMENT_ALLOW_EXTERNAL", "0").lower() in {"1", "true", "yes", "on"}
HF_SENTIMENT_TIMEOUT_SECONDS = float(os.getenv("CX_HF_SENTIMENT_TIMEOUT_SECONDS", "4"))
HF_SENTIMENT_MIN_CONFIDENCE = float(os.getenv("CX_HF_SENTIMENT_MIN_CONFIDENCE", "0.70"))
HF_SENTIMENT_MAX_CHARS = int(os.getenv("CX_HF_SENTIMENT_MAX_CHARS", "1200"))
HF_SENTIMENT_WAIT_FOR_MODEL = os.getenv("CX_HF_SENTIMENT_WAIT_FOR_MODEL", "1").lower() in {"1", "true", "yes", "on"}

WEBHOOK_SECRET = os.getenv("CX_WEBHOOK_SECRET", "")
META_VERIFY_TOKEN = os.getenv("CX_META_VERIFY_TOKEN", os.getenv("META_WEBHOOK_VERIFY_TOKEN", ""))
META_APP_SECRET = os.getenv("CX_META_APP_SECRET", os.getenv("META_APP_SECRET", ""))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CX_ALERT_CHAT_ID = os.getenv("CX_ALERT_CHAT_ID", "")
CX_SYNC_INTERVAL_SECONDS = int(os.getenv("CX_SYNC_INTERVAL_SECONDS", "0"))

CHATPLACE_PULL_URL = os.getenv("CHATPLACE_PULL_URL", "")
CHATPLACE_API_TOKEN = os.getenv("CHATPLACE_API_TOKEN", "")

GBP_ACCESS_TOKEN = os.getenv("GOOGLE_BUSINESS_PROFILE_ACCESS_TOKEN", "")
GBP_ACCOUNT_ID = os.getenv("GOOGLE_BUSINESS_PROFILE_ACCOUNT_ID", "")
GBP_LOCATION_IDS = [
    part.strip()
    for part in os.getenv("GOOGLE_BUSINESS_PROFILE_LOCATION_IDS", "").split(",")
    if part.strip()
]
GBP_REVIEW_PAGE_SIZE = int(os.getenv("GOOGLE_BUSINESS_PROFILE_REVIEW_PAGE_SIZE", "50"))

# YouTube social-listening (free Data API v3). Fills the "Sosial dinləmə" gap.
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_QUERIES = [
    q.strip()
    for q in os.getenv("YOUTUBE_QUERIES", "Xalq Sigorta,Xalq Sığorta").split(",")
    if q.strip()
]

META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION") or os.getenv("META_API_VERSION", "v25.0")
META_GRAPH_ACCESS_TOKEN = os.getenv("META_GRAPH_ACCESS_TOKEN") or os.getenv("META_ACCESS_TOKEN", "")
META_FACEBOOK_PAGE_IDS = [
    part.strip()
    for part in os.getenv("META_FACEBOOK_PAGE_IDS", os.getenv("FACEBOOK_PAGE_IDS", "")).split(",")
    if part.strip()
]
META_INSTAGRAM_BUSINESS_IDS = [
    part.strip()
    for part in os.getenv("META_INSTAGRAM_BUSINESS_IDS", os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_IDS", "")).split(",")
    if part.strip()
]
META_SYNC_POST_LIMIT = int(os.getenv("META_SYNC_POST_LIMIT", "10"))
META_SYNC_MEDIA_LIMIT = int(os.getenv("META_SYNC_MEDIA_LIMIT", "10"))
META_SYNC_COMMENT_LIMIT = int(os.getenv("META_SYNC_COMMENT_LIMIT", "50"))

BRAND = {
    "red": "#E31E24",
    "red_dark": "#B3171C",
    "ink": "#1C1B17",
    "charcoal": "#2B2A29",
    "bg": "#F5F6F8",
    "card": "#FFFFFF",
    "line": "#E5E7EB",
    "green": "#16A34A",
    "amber": "#F59E0B",
    "blue": "#2563EB",
}

CHANNELS = [
    {"id": "instagram_comment", "label": "Instagram comments", "kind": "owned_social"},
    {"id": "instagram_dm", "label": "Instagram DM", "kind": "owned_social"},
    {"id": "facebook_message", "label": "Facebook messages", "kind": "owned_social"},
    {"id": "tiktok_comment", "label": "TikTok comments", "kind": "owned_social"},
    {"id": "telegram", "label": "Telegram", "kind": "messaging"},
    {"id": "whatsapp", "label": "WhatsApp", "kind": "messaging"},
    {"id": "facebook_comment", "label": "Facebook comments", "kind": "owned_social"},
    {"id": "google_review", "label": "Google reviews", "kind": "review"},
    {"id": "website_form", "label": "Website forms", "kind": "owned_web"},
    {"id": "email", "label": "Email", "kind": "owned_support"},
    {"id": "web_mention", "label": "Web mentions", "kind": "earned_web"},
]

CATEGORIES = [
    "claims",
    "price",
    "service_quality",
    "delay",
    "staff_behavior",
    "digital_issue",
    "policy_terms",
    "branch_experience",
    "sales_followup",
    "reputation_risk",
    "other",
]

TEAMS = {
    "claims": "Claims",
    "price": "Sales",
    "service_quality": "Customer Care",
    "delay": "Operations",
    "staff_behavior": "Branch Management",
    "digital_issue": "Digital",
    "policy_terms": "Product",
    "branch_experience": "Branch Management",
    "sales_followup": "Sales",
    "reputation_risk": "PR and Customer Care",
    "other": "Customer Care",
}

SLA_BY_SEVERITY = {
    "critical": timedelta(minutes=int(os.getenv("CX_SLA_CRITICAL_MIN", "15"))),
    "high": timedelta(hours=int(os.getenv("CX_SLA_HIGH_HOURS", "1"))),
    "medium": timedelta(hours=int(os.getenv("CX_SLA_MEDIUM_HOURS", "4"))),
    "low": timedelta(hours=int(os.getenv("CX_SLA_LOW_HOURS", "24"))),
}

STATUSES = ["new", "triaged", "in_progress", "waiting_customer", "resolved", "closed"]
