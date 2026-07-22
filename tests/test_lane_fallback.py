"""Guard the system's core promise on the Telegram/worker side: no single
provider stopping ever stops the work, and Claude is the DEFAULT brain.

Regression pinned (2026-07-22): a heavy 'kampaniya' ask routed to a Gemini lane,
Gemini hit its cap, and the worker surfaced a raw 'Google Gemini pulsuz
limitlərini keçdiniz — 30-40 saniyə gözləyib yenidən cəhd edin' to the operator
instead of falling back to Claude. The operator rightly asked "axı sən Claude
ilə cavab verirdin, nə oldu?". The worker must now fall back to the resilient
brain and NEVER hand back a provider name as a dead end.
"""

import time
import unittest
from unittest.mock import patch

from gateway import executor


def _job(task: str):
    return executor.Job(
        id=0, source="telegram", chat_id="1", task=task, status="running",
        result=None, error=None, artifacts=[], created_at=time.time(),
        started_at=None, finished_at=None,
    )


class LaneFallback(unittest.TestCase):
    def _run_with_lane_raising(self, exc: Exception):
        with patch.object(executor.mic, "thread_for", return_value=""), \
             patch.object(executor, "_save_artifact", return_value="/tmp/x.md"), \
             patch.object(executor, "_wants_crew", return_value=False), \
             patch.object(executor, "_is_heavy_operational", return_value=False), \
             patch.object(executor, "_wants_plan", return_value=False), \
             patch.object(executor, "_council_should_run", return_value=False), \
             patch.object(executor, "_choose_mode", return_value="research"), \
             patch.object(executor, "_research_grounded", side_effect=exc), \
             patch.object(executor, "_converse",
                          return_value=("Claude cavabı budur.", "chat:claude-code")):
            return executor.execute(_job("bu ay səyahət sığortası kampaniyası necədir"))

    def test_gemini_quota_falls_back_to_brain(self):
        out = self._run_with_lane_raising(RuntimeError("429 RESOURCE_EXHAUSTED"))
        self.assertIn("Claude cavabı budur.", out["result"])
        # the operator must NEVER see the old provider-dead-end message again
        self.assertNotIn("pulsuz limitlərini", out["result"])
        self.assertNotIn("30-40 saniyə", out["result"])
        self.assertNotIn("Gemini", out["result"])

    def test_generic_lane_error_also_falls_back(self):
        out = self._run_with_lane_raising(RuntimeError("some studio blew up"))
        self.assertIn("Claude cavabı budur.", out["result"])
        self.assertNotIn("İcra xətası", out["result"])

    def test_honest_error_only_when_brain_also_dies(self):
        with patch.object(executor.mic, "thread_for", return_value=""), \
             patch.object(executor, "_wants_crew", return_value=False), \
             patch.object(executor, "_is_heavy_operational", return_value=False), \
             patch.object(executor, "_wants_plan", return_value=False), \
             patch.object(executor, "_council_should_run", return_value=False), \
             patch.object(executor, "_choose_mode", return_value="research"), \
             patch.object(executor, "_research_grounded",
                          side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")), \
             patch.object(executor, "_converse",
                          return_value=("[brain error] all capped", "none")):
            out = executor.execute(_job("bu ay səyahət sığortası kampaniyası necədir"))
        # brain also empty -> honest, but still not a Gemini-specific retry nag
        self.assertNotIn("pulsuz limitlərini", out["result"])
        self.assertIn("tamamlaya bilmədim", out["result"])


if __name__ == "__main__":
    unittest.main()
