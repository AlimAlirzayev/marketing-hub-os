"""Central configuration for Price Hunter - the AZ price-intelligence agent.

Mirrors the rest of Xalq Insurance Digital OS: pure-Python, no Docker, reuses the repo-root .env
so we share the same free keys (GEMINI_API_KEY, GROQ_API_KEY, APIFY_API_TOKEN,
TELEGRAM_BOT_TOKEN). Nothing here pulls heavy/native deps - safe to import
anywhere.
"""

from __future__ import annotations

import os
from datetime import datetime

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is a hard dep, but stay importable
    def load_dotenv(*_a, **_k):  # type: ignore
        return False

# Load the repo-root .env (one level up from price-hunter/) so we reuse the same
# keys the rest of Xalq Insurance Digital OS already has.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
REPORT_DIR = os.path.join(DATA_DIR, "reports")

# --------------------------------------------------------------------------
# LLM - reuse the live, free keys already in Xalq Insurance Digital OS .env.
# Gemini is the primary extractor (big context, free). Groq is the fast
# fallback. Either alone is enough; with neither we degrade to regex.
# --------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("PH_GEMINI_MODEL") or os.getenv("MODEL_FREE_BULK", "gemini-2.5-flash")

# Free Gemini quota is per-model. When one model returns RESOURCE_EXHAUSTED we
# rotate to the next so a single exhausted model never breaks a run. Primary
# first, then known free-tier flash models, de-duplicated.
_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash",
                    "gemini-2.5-flash-lite", "gemini-flash-latest"]
GEMINI_MODELS = list(dict.fromkeys([GEMINI_MODEL, *_FALLBACK_MODELS]))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("PH_GROQ_MODEL", "llama-3.3-70b-versatile")

# Apify - optional, only used as a fallback for anti-bot sources.
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")

# Telegram - optional push of the final verdict.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("PH_TELEGRAM_CHAT_ID") or os.getenv("CX_ALERT_CHAT_ID", "")

# --------------------------------------------------------------------------
# Crawl tuning
# --------------------------------------------------------------------------
HTTP_TIMEOUT = float(os.getenv("PH_HTTP_TIMEOUT", "30"))
MAX_CONCURRENCY = int(os.getenv("PH_MAX_CONCURRENCY", "8"))
# Per-source cap on listing pages parsed for offers, keeps LLM calls bounded.
MAX_PAGES_PER_SOURCE = int(os.getenv("PH_MAX_PAGES_PER_SOURCE", "6"))
CACHE_TTL_SECONDS = int(os.getenv("PH_CACHE_TTL", "1800"))  # 30 min

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Currency: everything is normalised to AZN. Hook for future multi-currency.
CURRENCY = "AZN"


def ensure_dirs() -> None:
    for d in (DATA_DIR, CACHE_DIR, REPORT_DIR):
        os.makedirs(d, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def llm_status() -> str:
    bits = []
    if GEMINI_API_KEY:
        bits.append(f"gemini:{GEMINI_MODEL}")
    if GROQ_API_KEY:
        bits.append(f"groq:{GROQ_MODEL}")
    if APIFY_API_TOKEN:
        bits.append("apify")
    return ", ".join(bits) or "regex-only (no LLM keys found)"
