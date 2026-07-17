"""Guards for the multi-step planner (gateway.executor._plan_and_run)."""

import types
import unittest
from unittest import mock

from gateway import executor


class _Job:
    def __init__(self, task, jid=1):
        self.task = task
        self.id = jid
        self.chat_id = None
        self.source = "cli"
        self.approved = 0


class WantsPlan(unittest.TestCase):
    def test_triggers_on_sequential_phrasing(self):
        self.assertTrue(executor._wants_plan(
            "əvvəlcə son TikTok trendlərini araşdır, sonra bizim üçün 3 post hazırla"))

    def test_ignores_short_chat(self):
        self.assertFalse(executor._wants_plan("salam necəsən"))
        self.assertFalse(executor._wants_plan("sonra?"))


class PlanAndRun(unittest.TestCase):
    def setUp(self):
        # Silence the event bus during the test.
        self._sense = mock.patch.object(executor.sense, "emit").start()
        self.addCleanup(mock.patch.stopall)

    def test_single_step_falls_back(self):
        with mock.patch.object(executor, "_decompose",
                               return_value=[{"lane": "reason", "goal": "x"}]):
            self.assertIsNone(executor._plan_and_run(_Job("bir addımlıq iş"), "t"))

    def test_all_reason_plan_falls_back(self):
        # Pure-thinking chains stay on the normal chat path — the planner must
        # never hijack a conversational turn just because it phrased steps.
        steps = [{"lane": "reason", "goal": "düşün"}, {"lane": "reason", "goal": "cavabla"}]
        with mock.patch.object(executor, "_decompose", return_value=steps):
            self.assertIsNone(executor._plan_and_run(_Job("əvvəlcə düşün sonra cavabla"), "t"))

    def test_runs_steps_in_order_and_threads_context(self):
        steps = [{"lane": "research", "goal": "son trendləri tap"},
                 {"lane": "reason", "goal": "onlardan strategiya çıxar"}]
        seen = {}

        def _fake_converse(prompt, thread):
            seen["converse_prompt"] = prompt
            return "STRATEGY", "chat:test"

        def _fake_synth_or_reason(prompt, thread):
            # the synthesis prompt is the only one that starts with "ƏSAS TAPŞIRIQ"
            seen.setdefault("calls", []).append(prompt)
            return ("FINAL" if "ƏSAS TAPŞIRIQ" in prompt else "STRATEGY"), "chat:test"

        with mock.patch.object(executor, "_decompose", return_value=steps), \
             mock.patch.object(executor, "_research_grounded",
                               return_value="TREND-DATA") as research, \
             mock.patch.object(executor, "_converse", side_effect=_fake_synth_or_reason):
            out = executor._plan_and_run(_Job("əvvəlcə araşdır sonra strategiya"), "t")

        self.assertIsNotNone(out)
        text, label = out
        self.assertEqual(label, "plan:2-addım")
        self.assertEqual(text, "FINAL")
        research.assert_called_once()
        # the reason step must have received step-1's research result as context
        reason_prompt = seen["calls"][0]
        self.assertIn("TREND-DATA", reason_prompt)
        self.assertIn("onlardan strategiya", reason_prompt)

    def test_one_bad_step_does_not_sink_the_chain(self):
        steps = [{"lane": "research", "goal": "a"}, {"lane": "reason", "goal": "b"}]
        with mock.patch.object(executor, "_decompose", return_value=steps), \
             mock.patch.object(executor, "_research_grounded",
                               side_effect=RuntimeError("boom")), \
             mock.patch.object(executor, "_converse", return_value=("OK", "chat:test")):
            out = executor._plan_and_run(_Job("araşdır sonra yaz"), "t")
        self.assertIsNotNone(out)  # chain still completes despite step 1 failing


if __name__ == "__main__":
    unittest.main()
