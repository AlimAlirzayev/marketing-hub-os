"""Central configuration for Atelier - the unified marketing cockpit.

Single source of truth for branding, paths into the existing studios, and the
free Gemini key. Mirrors the ads-studio pattern so the whole Xalq Insurance Digital OS stays in
lock-step: pure-Python, no Docker, reuses the repo-root .env.

Nothing here pulls heavy/native deps - safe to import from anywhere.
"""

from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv

# Load the repo-root .env (one level up from atelier/) so we reuse the same keys
# the rest of Xalq Insurance Digital OS already has (GEMINI_API_KEY, etc.).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

BASE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Brand
# --------------------------------------------------------------------------
ACCOUNT_NAME = os.getenv("ATELIER_ACCOUNT_NAME", "Xalq Sigorta")
ACCOUNT_TAGLINE = os.getenv("ATELIER_TAGLINE", "Creative Lab · Marketing Cockpit")

# Xalq Sigorta brand palette (mirrors social-studio/brand_kit + ads-studio).
BRAND = {
    "red": "#E31E24",
    "red_dark": "#B3171C",
    "charcoal": "#2B2A29",
    "ink": "#1C1B17",
    "burgundy": "#5C0F12",
    "white": "#FFFFFF",
    # Cockpit chrome accents (not brand fills).
    "bg": "#0E0E10",
    "panel": "#17171A",
    "card": "#1E1E22",
    "line": "#2A2A30",
    "muted": "#8A8A93",
    "text": "#ECECEE",
    "green": "#16A34A",
    "amber": "#F59E0B",
    "blue": "#3B82F6",
}

# --------------------------------------------------------------------------
# Paths into the existing studios - Atelier is a cockpit ON TOP of these,
# never a copy of them. The studio markdown stays the single source of truth.
# --------------------------------------------------------------------------
SOCIAL_STUDIO = os.path.join(_REPO_ROOT, "social-studio")
COPY_STUDIO = os.path.join(_REPO_ROOT, "copy-studio")

PROMPT_KIT = os.path.join(SOCIAL_STUDIO, "prompt_kit")
STYLE_DNA_DIR = os.path.join(PROMPT_KIT, "style_dna")
MODEL_DIALECTS_DIR = os.path.join(PROMPT_KIT, "model_dialects")
MASTER_TEMPLATE = os.path.join(PROMPT_KIT, "master_template.md")
AI_TELLS = os.path.join(PROMPT_KIT, "negative_templates", "ai-tells.md")
BRAND_MD = os.path.join(SOCIAL_STUDIO, "brand_kit", "brand.md")

VOICE_DNA_DIR = os.path.join(COPY_STUDIO, "voice_dna")
LEGAL_PHRASES = os.path.join(COPY_STUDIO, "copy_kit", "legal_phrases.md")

# --------------------------------------------------------------------------
# Atelier-local storage (SQLite + uploaded images + saved brand state)
# --------------------------------------------------------------------------
DATA_DIR = os.path.join(BASE, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "atelier.db")
BRAND_STATE = os.path.join(DATA_DIR, "brand_state.json")

# --------------------------------------------------------------------------
# AI - reuse the live, free Gemini key already in Xalq Insurance Digital OS .env.
# --------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("MODEL_FREE_BULK", "gemini-2.0-flash")

# Aspect-ratio presets the Creative Lab offers (label -> pixel spec for prompts).
FORMATS = {
    "4:5 Feed": "4:5 vertical, 1080x1350",
    "1:1 Square": "1:1 square, 1080x1080",
    "9:16 Story": "9:16 vertical, 1080x1920",
    "1.91:1 Link": "1.91:1 landscape, 1200x628",
    "16:9 Wide": "16:9 landscape, 1920x1080",
}

# Where the user generates the hero image (ChatGPT Bridge flow).
CHATGPT_URL = os.getenv("ATELIER_CHATGPT_URL", "https://chatgpt.com/")


def ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
