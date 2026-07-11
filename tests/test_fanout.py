"""Guards for the specialist fan-out (gateway.executor).

The pattern adopted from the 2026-07-10 multi-agent reel research (job 40):
strategy-shaped tasks fan out to parallel specialist branches with strict-JSON
outputs, then one bundler merges them. These tests stub the LLM seam
(_fanout_specialist / llm.complete) — no live model calls.
"""

import unittest
from unittest.mock import patch

from gateway import executor
from orchestrator.router import ModelChoice


def _branch(role, persona, task):
    return {
        "role": role, "model": "stub-model",
        "key_points": [f"{role}-kp"],
        "recommendations": [f"{role}-rec"],
        "risks": [f"{role}-risk"],
    }


class WantsFanout(unittest.TestCase):
    def test_greeting_stays_conversational(self):
        self.assertFalse(executor._wants_fanout("Salam"))

    def test_short_question_stays_conversational(self):
        # carries a cue word but is too short to be a deliverable ask
        self.assertFalse(executor._wants_fanout("planın nədir?"))

    def test_strategy_deliverable_triggers(self):
        self.assertTrue(executor._wants_fanout(
            "bizim sığorta məhsulu üçün marketinq strategiyası hazırla zəhmət olmasa"
        ))

    def test_fanout_tasks_still_route_plain(self):
        # fan-out must only ever upgrade the PLAIN path — if this task starts
        # matching a tools/browser/research hint, the feature silently dies
        task = "bizim sığorta məhsulu üçün marketinq strategiyası hazırla zəhmət olmasa"
        self.assertEqual(executor._choose_mode(task), "plain")


class FanoutDeliver(unittest.TestCase):
    def test_bundles_all_branches(self):
        captured = {}

        def fake_complete(choice, prompt, system=None, **kw):
            captured["prompt"] = prompt
            return "BUNDLED PLAN", ModelChoice(
                provider="router", model="stub", reason="test")

        with patch.object(executor, "_fanout_specialist", _branch), \
             patch.object(executor.llm, "complete", fake_complete), \
             patch.object(executor.knowledge, "augment_system",
                          lambda base, *a, **k: base):
            text, label = executor._fanout_deliver("task", "main")

        self.assertEqual(text, "BUNDLED PLAN")
        self.assertTrue(label.startswith("fanout:3x->"))
        for role, _ in executor._SPECIALISTS:
            self.assertIn(f"{role}-rec", captured["prompt"])

    def test_partial_branch_failure_still_delivers(self):
        def flaky(role, persona, task):
            if role == "product":
                raise RuntimeError("branch down")
            return _branch(role, persona, task)

        with patch.object(executor, "_fanout_specialist", flaky), \
             patch.object(executor.llm, "complete",
                          lambda c, p, system=None, **kw: (
                              "OK", ModelChoice(provider="router", model="stub", reason="test"))), \
             patch.object(executor.knowledge, "augment_system",
                          lambda base, *a, **k: base):
            text, label = executor._fanout_deliver("task", "main")

        self.assertEqual(text, "OK")
        self.assertIn("2x", label)
        self.assertIn("product", label)

    def test_total_failure_raises_for_converse_fallback(self):
        def dead(role, persona, task):
            raise RuntimeError("no provider")

        with patch.object(executor, "_fanout_specialist", dead):
            with self.assertRaises(RuntimeError):
                executor._fanout_deliver("task", "main")


if __name__ == "__main__":
    unittest.main()
