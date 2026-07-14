"""The brain is Claude: llm_router prefers the subscription for the smart tier.

Guards the 2026-07-14 directive "yalnız claude olsun hər yerdə beyin" — the smart
tier (planning/synthesis/decisions/digests) must route to the Claude subscription
first, falling back to the free cascade only when every account is capped. The
cheap tier stays free by default so mechanical bulk never burns the 5h cap.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock


class ClaudeFirstPolicy(unittest.TestCase):
    def setUp(self):
        import llm_router
        self.r = llm_router

    def test_smart_tier_prefers_claude(self):
        with mock.patch.dict(os.environ, {"BRAIN_CLAUDE_FIRST": "1"}), \
             mock.patch("gateway.claude_bridge.is_available", return_value=True), \
             mock.patch("gateway.claude_bridge.complete",
                        return_value=("cavab", "claude-code/subscription")) as cb:
            text, model = self.r.complete("plan this", tier="smart")
        self.assertEqual(text, "cavab")
        self.assertIn("claude-code", model)
        cb.assert_called_once()

    def test_cheap_tier_stays_free_by_default(self):
        # cheap must NOT touch the subscription unless CLAUDE_EVERYWHERE=1.
        with mock.patch.dict(os.environ, {"BRAIN_CLAUDE_FIRST": "1"}), \
             mock.patch("gateway.claude_bridge.complete") as cb:
            self.assertFalse(self.r._claude_first("cheap", want_json=False))
            cb.assert_not_called()

    def test_claude_everywhere_opt_in_covers_cheap(self):
        with mock.patch.dict(os.environ, {"BRAIN_CLAUDE_FIRST": "1", "CLAUDE_EVERYWHERE": "1"}):
            self.assertTrue(self.r._claude_first("cheap", want_json=False))

    def test_json_calls_skip_claude(self):
        # structured output has no subscription-CLI guarantee -> free tier owns it.
        with mock.patch.dict(os.environ, {"BRAIN_CLAUDE_FIRST": "1"}):
            self.assertFalse(self.r._claude_first("smart", want_json=True))

    def test_disable_flag_turns_it_off(self):
        with mock.patch.dict(os.environ, {"BRAIN_CLAUDE_FIRST": "0"}):
            self.assertFalse(self.r._claude_first("smart", want_json=False))

    def test_falls_back_to_free_when_claude_capped(self):
        # every account capped -> _try_claude returns None -> free cascade runs.
        with mock.patch.dict(os.environ, {"BRAIN_CLAUDE_FIRST": "1"}), \
             mock.patch("gateway.claude_bridge.is_available", return_value=True), \
             mock.patch("gateway.claude_bridge.complete",
                        side_effect=RuntimeError("all Claude accounts capped")):
            self.assertIsNone(self.r._try_claude("x", None, "smart"))


if __name__ == "__main__":
    unittest.main()
