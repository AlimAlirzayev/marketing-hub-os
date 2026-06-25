"""Import + environment bootstrap for the gateway.

Importing this module makes the repo root importable so the gateway can reuse
``orchestrator.router`` without packaging gymnastics, and loads ``.env`` into
the process environment (works with or without python-dotenv installed).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Make `import orchestrator.router` work no matter where we're launched from.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_ENV_LOADED = False


def load_env() -> None:
    """Load .env into os.environ once. Falls back to a tiny parser if
    python-dotenv is unavailable, so the gateway never hard-depends on it."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = _REPO_ROOT / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
    _ENV_LOADED = True
