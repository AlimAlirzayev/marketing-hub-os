"""Configuration for Influencer Hunter.

The tool reuses the repository root .env. Apify is optional but recommended for
Instagram profile/post/comment evidence. Without it, the system can still score
seed handles when profile/post data is supplied later, and it reports the gap
honestly instead of inventing market data.
"""

from __future__ import annotations

import os
from datetime import datetime

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*_a, **_k):  # type: ignore
        return False


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO_ROOT, ".env"))

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
REPORT_DIR = os.path.join(DATA_DIR, "reports")

DISABLE_LLM = os.getenv("IH_DISABLE_LLM", "0").lower() in {"1", "true", "yes", "on"}
DISABLE_APIFY = os.getenv("IH_DISABLE_APIFY", "0").lower() in {"1", "true", "yes", "on"}

GEMINI_API_KEY = "" if DISABLE_LLM else (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", ""))
GEMINI_MODEL = os.getenv("IH_GEMINI_MODEL") or os.getenv("MODEL_FREE_BULK", "gemini-2.5-flash")
GEMINI_MODELS = list(dict.fromkeys([
    GEMINI_MODEL,
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
]))

GROQ_API_KEY = "" if DISABLE_LLM else os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("IH_GROQ_MODEL", "llama-3.3-70b-versatile")

APIFY_API_TOKEN = "" if DISABLE_APIFY else os.getenv("APIFY_API_TOKEN", "")
APIFY_TIMEOUT = int(os.getenv("IH_APIFY_TIMEOUT", "180"))
APIFY_MAX_RETRIES = int(os.getenv("IH_APIFY_MAX_RETRIES", "2"))

# Apify costs money and runs are slow; cache identical actor calls on disk so
# repeated/dev runs do not re-scrape. Set IH_DISABLE_CACHE=1 for a guaranteed
# live run, or tune the freshness window with IH_CACHE_TTL (seconds).
DISABLE_CACHE = os.getenv("IH_DISABLE_CACHE", "0").lower() in {"1", "true", "yes", "on"}
CACHE_TTL = int(os.getenv("IH_CACHE_TTL", "21600"))

INSTAGRAM_SCRAPER_ACTOR = os.getenv("IH_INSTAGRAM_SCRAPER_ACTOR", "apify/instagram-scraper")
INSTAGRAM_PROFILE_ACTOR = os.getenv("IH_INSTAGRAM_PROFILE_ACTOR", "apify/instagram-profile-scraper")
INSTAGRAM_POST_ACTOR = os.getenv("IH_INSTAGRAM_POST_ACTOR", "apify/instagram-post-scraper")
INSTAGRAM_COMMENT_ACTOR = os.getenv("IH_INSTAGRAM_COMMENT_ACTOR", "apify/instagram-comment-scraper")
INSTAGRAM_HASHTAG_ACTOR = os.getenv("IH_INSTAGRAM_HASHTAG_ACTOR", "apify/instagram-hashtag-scraper")

# --- YouTube Data API v3 (free, official, no ban risk) ---
# Reuses the Google key if a dedicated one is not set. Independent of
# IH_DISABLE_LLM because this key is for data, not generation.
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
YT_MAX_CHANNELS = int(os.getenv("IH_YT_MAX_CHANNELS", "8"))
YT_MAX_VIDEOS_PER_CHANNEL = int(os.getenv("IH_YT_MAX_VIDEOS", "6"))
YT_MAX_COMMENTS_PER_VIDEO = int(os.getenv("IH_YT_MAX_COMMENTS", "20"))
YT_REGION = os.getenv("IH_YT_REGION", "AZ")
YT_RELEVANCE_LANGUAGE = os.getenv("IH_YT_RELEVANCE_LANGUAGE", "az")

# --- Public web discovery connector (free, no credentials, no ban risk) ---
DISABLE_WEB = os.getenv("IH_DISABLE_WEB", "0").lower() in {"1", "true", "yes", "on"}
WEB_MAX_PAGES = int(os.getenv("IH_WEB_MAX_PAGES", "5"))

# --- Telegram public-channel connector (t.me/s preview; free, anonymous, no ban) ---
DISABLE_TELEGRAM = os.getenv("IH_DISABLE_TELEGRAM", "0").lower() in {"1", "true", "yes", "on"}
TG_MAX_CHANNELS = int(os.getenv("IH_TG_MAX_CHANNELS", "10"))
TG_MAX_POSTS = int(os.getenv("IH_TG_MAX_POSTS", "12"))

# --- Generic RapidAPI connector (one key, many social hosts; free tiers) ---
# A single X-RapidAPI-Key unlocks every host you subscribe to, so this one key
# revives Instagram (without Apify) and adds TikTok. Primarily an ENRICHMENT
# connector: hand it handles (seeds, or handles discovered by web/telegram) and
# it returns real profile + recent posts. Degrades honestly without the key.
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY") or os.getenv("RAPID_API_KEY", "")
DISABLE_RAPIDAPI = os.getenv("IH_DISABLE_RAPIDAPI", "0").lower() in {"1", "true", "yes", "on"}
# Optional: pin a specific host you subscribed to (else the built-in registry is tried in order).
RAPIDAPI_IG_HOST = os.getenv("IH_RAPIDAPI_IG_HOST", "")
RAPIDAPI_TT_HOST = os.getenv("IH_RAPIDAPI_TT_HOST", "")
RAPIDAPI_MAX_HANDLES = int(os.getenv("IH_RAPIDAPI_MAX_HANDLES", "12"))
RAPIDAPI_MAX_POSTS = int(os.getenv("IH_RAPIDAPI_MAX_POSTS", "12"))
RAPIDAPI_TIMEOUT = int(os.getenv("IH_RAPIDAPI_TIMEOUT", "25"))

MAX_DISCOVERY_POSTS = int(os.getenv("IH_MAX_DISCOVERY_POSTS", "80"))
MAX_PROFILE_HANDLES = int(os.getenv("IH_MAX_PROFILE_HANDLES", "24"))
MAX_POSTS_PER_HANDLE = int(os.getenv("IH_MAX_POSTS_PER_HANDLE", "12"))
MAX_COMMENTS_PER_POST = int(os.getenv("IH_MAX_COMMENTS_PER_POST", "25"))
DEFAULT_MIN_FOLLOWERS = int(os.getenv("IH_DEFAULT_MIN_FOLLOWERS", "20000"))


def ensure_dirs() -> None:
    for path in (DATA_DIR, CACHE_DIR, REPORT_DIR):
        os.makedirs(path, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def llm_status() -> str:
    bits: list[str] = []
    if GEMINI_API_KEY:
        bits.append(f"gemini:{GEMINI_MODEL}")
    if GROQ_API_KEY:
        bits.append(f"groq:{GROQ_MODEL}")
    return ", ".join(bits) or "rule-based"


def engine_status() -> dict:
    return {
        "llm": llm_status(),
        "apify": bool(APIFY_API_TOKEN),
        "actors": {
            "search": INSTAGRAM_SCRAPER_ACTOR,
            "profile": INSTAGRAM_PROFILE_ACTOR,
            "post": INSTAGRAM_POST_ACTOR,
            "comment": INSTAGRAM_COMMENT_ACTOR,
            "hashtag": INSTAGRAM_HASHTAG_ACTOR,
        },
    }
