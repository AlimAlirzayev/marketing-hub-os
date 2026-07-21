"""Operations Self-Review: the weekly retrospective must count real events
honestly, fire lessons only on a clear threshold (no noise), self-gate to once a
week, and never raise on the always-on path.
"""

import time
import unittest
from unittest import mock

from gateway import self_review as sr


def _ev(kind, summary, ts=0.0):
    return {"kind": kind, "summary": summary, "ts": ts}


class Assess(unittest.TestCase):
    def _events(self):
        return [
            _ev("job", "#1 done (telegram)"), _ev("job", "#2 done (schedule)"),
            _ev("job", "#3 error: boom"),
            _ev("watchdog", "ads down"), _ev("watchdog", "ads down"),
            _ev("watchdog", "ads down"), _ev("watchdog", "ads restarted"),
            _ev("llm", "chat:router:gemini"), _ev("llm", "claude bridge fell back to free"),
            _ev("security", "rejected non-owner chat_id=999"),
        ]

    def test_counts_reliability_and_incidents(self):
        a = sr.assess(self._events(), now=1000.0, window_days=7)
        self.assertEqual(a["jobs"]["done"], 2)
        self.assertEqual(a["jobs"]["error"], 1)
        self.assertAlmostEqual(a["jobs"]["reliability_pct"], 66.7, places=1)
        self.assertEqual(a["incidents"]["down_events"], 3)
        self.assertEqual(a["incidents"]["by_service"]["ads"], 3)
        self.assertEqual(a["security"]["rejected"], 1)

    def test_brain_fallback_ratio(self):
        a = sr.assess(self._events(), now=1000.0, window_days=7)
        self.assertEqual(a["brain"]["llm_calls"], 2)
        self.assertEqual(a["brain"]["free_fallbacks"], 1)

    def test_status_healthy_when_quiet(self):
        a = sr.assess([_ev("job", "#1 done")], now=1.0, window_days=7)
        self.assertEqual(a["status"], "Sağlam")
        self.assertEqual(a["concerns"], [])

    def test_gaveup_raises_a_concern(self):
        evs = [_ev("watchdog", "ads gave up — insan lazım")]
        a = sr.assess(evs, now=1.0, window_days=7)
        self.assertIn("service_gaveup", a["concerns"])

    def test_no_fabrication_on_empty(self):
        a = sr.assess([], now=1.0, window_days=7)
        self.assertIsNone(a["jobs"]["reliability_pct"])
        self.assertEqual(a["incidents"]["down_events"], 0)
        self.assertEqual(a["status"], "Sağlam")


class Lessons(unittest.TestCase):
    def test_unstable_service_becomes_a_lesson(self):
        evs = [_ev("watchdog", "ads down")] * 3
        a = sr.assess(evs, now=1.0, window_days=7)
        titles = [x["title"] for x in sr.lessons(a)]
        self.assertTrue(any("ads" in t and "dayandı" in t for t in titles))

    def test_high_fallback_becomes_a_lesson(self):
        evs = [_ev("llm", "claude bridge fell back to free")] * 6 + \
              [_ev("llm", "chat:router:ok")] * 6
        a = sr.assess(evs, now=1.0, window_days=7)
        self.assertTrue(any("pulsuz" in x["title"] for x in sr.lessons(a)))

    def test_quiet_week_files_no_noise(self):
        a = sr.assess([_ev("job", "#1 done")], now=1.0, window_days=7)
        self.assertEqual(sr.lessons(a), [])

    def test_job_errors_threshold(self):
        evs = [_ev("job", f"#{i} error") for i in range(3)]
        a = sr.assess(evs, now=1.0, window_days=7)
        self.assertTrue(any("xəta ilə bitdi" in x["title"] for x in sr.lessons(a)))


class WeeklyGate(unittest.TestCase):
    def test_due_when_never_run(self):
        self.assertTrue(sr.weekly_due(1000.0, None, 7))

    def test_not_due_within_interval(self):
        now = 1_000_000.0
        self.assertFalse(sr.weekly_due(now, now - 3 * 86400, 7))

    def test_due_after_interval(self):
        now = 1_000_000.0
        self.assertTrue(sr.weekly_due(now, now - 8 * 86400, 7))

    def test_run_if_due_gates_and_records(self):
        state = {}
        with mock.patch.object(sr, "_load_state", side_effect=lambda: dict(state)), \
                mock.patch.object(sr, "_save_state", side_effect=state.update), \
                mock.patch.object(sr, "collect", return_value=sr.assess([], now=1.0)), \
                mock.patch.object(sr, "_file_lessons", return_value=0):
            first = sr.run_if_due(now=1_000_000.0)
            self.assertFalse(first["skipped"])
            self.assertIn("last_ts", state)
            again = sr.run_if_due(now=1_000_050.0)  # same week
            self.assertTrue(again["skipped"])

    def test_run_if_due_never_raises(self):
        with mock.patch.object(sr, "_load_state", side_effect=RuntimeError("boom")):
            self.assertEqual(sr.run_if_due(now=1.0), {"skipped": True})


class ReportText(unittest.TestCase):
    def test_report_renders_azerbaijani(self):
        with mock.patch.object(sr, "collect",
                               return_value=sr.assess([_ev("job", "#1 done")], now=1.0)):
            text = sr.report()
        self.assertIn("ƏMƏLİYYAT ÖZÜ-QİYMƏTLƏNDİRMƏSİ", text)
        self.assertIn("Etibarlılıq", text)
        self.assertNotIn("None", text)


if __name__ == "__main__":
    unittest.main()
