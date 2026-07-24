"""Guards for the AZ voice call-agent engine (gateway.call_agent). All offline:
brain.answer is mocked so no LLM call, no cap dependency."""

import unittest
from unittest.mock import patch

from gateway import call_agent as ca


class System(unittest.TestCase):
    def test_system_prompt_carries_company_and_qualify(self):
        s = ca._system(ca.DEFAULT_SCENARIO)
        self.assertIn("Xalq Sığorta", s)
        self.assertIn("KASKO", s)          # from a qualify item
        self.assertIn("AGENT", s)

    def test_render_transcript(self):
        t = ca._render([("caller", "salam"), ("agent", "buyurun")])
        self.assertEqual(t, "Müştəri: salam\nAgent: buyurun")


class Reply(unittest.TestCase):
    def test_reply_strips_role_prefix_and_quotes(self):
        with patch.object(ca.brain, "answer", return_value=('Agent: "Buyurun, necə kömək edim?"', "free:gemini")):
            self.assertEqual(ca.reply([]), "Buyurun, necə kömək edim?")

    def test_reply_uses_fast_path_by_default(self):
        with patch.object(ca.brain, "answer", return_value=("salam", "free:gemini")) as m:
            ca.reply([("caller", "salam")])
            self.assertEqual(m.call_args.kwargs["prefer"], "free")

    def test_reply_claude_when_not_fast(self):
        with patch.object(ca.brain, "answer", return_value=("salam", "claude")) as m:
            ca.reply([], fast=False)
            self.assertEqual(m.call_args.kwargs["prefer"], "claude")

    def test_reply_never_empty(self):
        with patch.object(ca.brain, "answer", return_value=("", "free:gemini")):
            self.assertTrue(ca.reply([]))


class Report(unittest.TestCase):
    def test_report_parses_json_card(self):
        payload = ('{"qualified": true, "need": "KASKO", "budget": "45000 AZN", '
                   '"urgency": "yüksək", "contact": "Elvin 0501234567", '
                   '"summary": "KASKO istəyir.", "next_action": "Mütəxəssisə ötür"}')
        with patch.object(ca.brain, "answer", return_value=(payload, "claude:sonnet")):
            card = ca.report([("caller", "KASKO lazımdır")])
        self.assertTrue(card["qualified"])
        self.assertEqual(card["urgency"], "yüksək")
        self.assertEqual(card["by"], "claude:sonnet")

    def test_report_survives_garbage_with_full_keyset(self):
        with patch.object(ca.brain, "answer", return_value=("model rambled, no json", "free:gemini")):
            card = ca.report([("caller", "salam")])
        for k in ("qualified", "need", "budget", "urgency", "contact", "summary", "next_action"):
            self.assertIn(k, card)
        self.assertFalse(card["qualified"])           # safe default

    def test_report_uses_claude_brain(self):
        with patch.object(ca.brain, "answer", return_value=("{}", "claude")) as m:
            ca.report([("caller", "salam")])
            self.assertEqual(m.call_args.kwargs["prefer"], "claude")


class DemoLoop(unittest.TestCase):
    def test_demo_runs_end_to_end(self):
        # agent replies canned; report returns a card — the whole loop must run
        # and return the qualification card without touching the network.
        with patch.object(ca.brain, "answer", return_value=("cavab", "free:gemini")):
            card = ca.demo(caller=["salam", "KASKO lazımdır"])
        self.assertIn("qualified", card)


if __name__ == "__main__":
    unittest.main()
