"""Data connectors for GA4 Studio.

``get_report(start, end)`` returns one report dict — the SAME shape from both the
demo engine and the live GA4 Data API — so the analytics + dashboard layers never
care which is active. ``config.DATA_MODE`` decides.
"""

from __future__ import annotations

import config


def get_report(start: str, end: str) -> dict:
    if config.DATA_MODE == "live":
        from . import ga4_live
        return ga4_live.get_report(start, end)
    from . import demo
    return demo.get_report(start, end)
