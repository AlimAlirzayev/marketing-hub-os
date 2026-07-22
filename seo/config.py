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
            v = v.strip()
            # python-dotenv writes quoted values; strip a matching surrounding
            # pair so paths/URLs don't carry literal quotes (os.path.exists fails).
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)


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

# --- Google Search Console (own-site TRUTH; powers the D1 reinforcement loop) - #
# The one data source no free tool can replace: real clicks/impressions/position
# for YOUR site, straight from Google. Service-account auth, same pattern as
# ga4-studio. Grant the service-account email access in Search Console
# (Settings -> Users and permissions -> Add, Full/Restricted).
#   GSC_SITE_URL   "sc-domain:xalqsigorta.az"  (Domain property, preferred) OR
#                  "https://xalqsigorta.az/"    (URL-prefix property)
#   credentials    GSC_SERVICE_ACCOUNT_FILE, else GA4's, else GOOGLE_APPLICATION_CREDENTIALS
GSC_SITE_URL = os.getenv("GSC_SITE_URL", "").strip()
GSC_SERVICE_ACCOUNT_FILE = (
    os.getenv("GSC_SERVICE_ACCOUNT_FILE", "")
    or os.getenv("GA4_SERVICE_ACCOUNT_FILE", "")
    or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
).strip()
# Cross-machine fallback: env paths are per-OS (a Windows path won't exist on the
# Linux twin), but ga4-studio materializes the SA from GA4_SERVICE_ACCOUNT_JSON_B64
# (synced in the vault) to this repo-relative file on EVERY machine. So if the
# env-named file is absent, fall back to that known location — GSC then goes live
# on the twin automatically once the b64 is in the vault, with no path juggling.
if not GSC_SERVICE_ACCOUNT_FILE or not os.path.exists(GSC_SERVICE_ACCOUNT_FILE):
    _ga4_secret = REPO / "ga4-studio" / "secrets" / "ga4-service-account.json"
    if _ga4_secret.exists():
        GSC_SERVICE_ACCOUNT_FILE = str(_ga4_secret)
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GSC_API = "https://searchconsole.googleapis.com/webmasters/v3"


def gsc_mode() -> str:
    """'live' when a site + readable credentials exist, else 'demo'. An explicit
    GSC_DATA_MODE=demo|live overrides (mirrors ga4-studio)."""
    forced = os.getenv("GSC_DATA_MODE", "").lower()
    if forced in ("demo", "live"):
        return forced
    have = bool(GSC_SITE_URL and GSC_SERVICE_ACCOUNT_FILE
                and os.path.exists(GSC_SERVICE_ACCOUNT_FILE))
    return "live" if have else "demo"


def gsc_blockers() -> list[str]:
    """Honest reasons live GSC is unavailable (for UI/CLI labels)."""
    out = []
    if not GSC_SITE_URL:
        out.append("GSC_SITE_URL .env-də yoxdur (məs: sc-domain:xalqsigorta.az)")
    if not GSC_SERVICE_ACCOUNT_FILE:
        out.append("Service-account JSON göstərilməyib (GSC_SERVICE_ACCOUNT_FILE)")
    elif not os.path.exists(GSC_SERVICE_ACCOUNT_FILE):
        out.append(f"Service-account faylı tapılmadı: {GSC_SERVICE_ACCOUNT_FILE}")
    return out

# Known AI/LLM crawler user-agents — presence in robots.txt = GEO governance.
AI_BOTS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-Web",
    "anthropic-ai", "PerplexityBot", "Google-Extended", "CCBot", "Bytespider",
    "Applebot-Extended", "Amazonbot", "cohere-ai", "Meta-ExternalAgent",
]

for _d in (DATA_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
