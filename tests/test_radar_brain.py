"""The radar's digest is the brain, so it must run on the smart tier (→ Claude).

Guards the 2026-07-14 change bumping radar's weekly brief + daily pulse digests
from tier="cheap" (Groq floor) to tier="smart" (Claude subscription first). The
SCRAPING stays keyless/free; only the synthesis is premium.
"""

from __future__ import annotations

import unittest
from unittest import mock


class RadarDigestTier(unittest.TestCase):
    def test_weekly_brief_digests_on_smart_tier(self):
        from gateway import radar
        items = [{"src": "HF", "title": "some/model", "info": "text-to-image", "url": "x"}]
        with mock.patch("llm_router.complete",
                        return_value=("brief mətni", "claude-code/subscription")) as rc:
            radar.digest(items, [])
        self.assertEqual(rc.call_args.kwargs.get("tier"), "smart")

    def test_scraping_helpers_use_no_llm(self):
        # collection must stay mechanical/free — no brain spend on fetching.
        import inspect
        from gateway import radar
        for name in ("_hf_models", "_github_new", "_rss"):
            src = inspect.getsource(getattr(radar, name))
            self.assertNotIn("llm_router", src, f"{name} must not call the LLM")


if __name__ == "__main__":
    unittest.main()
