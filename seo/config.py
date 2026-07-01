"""SEO Engine configuration — env-driven, free-first, zero required keys.

Reads the repo-root .env the same way llm_router does, so a single .env powers
the whole ecosystem. Every key here is OPTIONAL: without it the engine falls
back to a keyless/free path and labels any gap honestly.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data" / "seo"
OUTPUT_DIR = REPO / "output" / "seo"


def _load_env() -> None:
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

# --- fetch behaviour -------------------------------------------------------- #
# A real, honest UA. We identify as a normal browser-class crawler; sites that
# block generic bots still answer this, and we respect robots meta on-page.
USER_AGENT = os.getenv(
    "SEO_USER_AGENT",
    "Mozilla/5.0 (compatible; RaminSEO/0.1; +https://ramin-os.local/seo)",
)
FETCH_TIMEOUT = int(os.getenv("SEO_FETCH_TIMEOUT", "20"))
MAX_HTML_BYTES = int(os.getenv("SEO_MAX_HTML_BYTES", str(3_000_000)))  # 3 MB cap

# --- optional connectors (blank = keyless/free path) ------------------------ #
# PageSpeed Insights works with NO key (rate-limited). A key raises the quota.
PSI_API_KEY = os.getenv("PAGESPEED_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Apify token (already in the ecosystem) — optional SERP fallback.
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")

# Known AI/LLM crawler user-agents — presence in robots.txt = GEO governance.
AI_BOTS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-Web",
    "anthropic-ai", "PerplexityBot", "Google-Extended", "CCBot", "Bytespider",
    "Applebot-Extended", "Amazonbot", "cohere-ai", "Meta-ExternalAgent",
]

for _d in (DATA_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
