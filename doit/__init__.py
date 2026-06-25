"""doit — Ramin-OS autonomous credential-acquisition agent.

Fetches API keys itself (under your own browser session) and writes them to .env,
instead of asking you to go get them. See agent.acquire().
"""

from .agent import acquire, verify_rapidapi  # noqa: F401

__version__ = "0.1.0"
