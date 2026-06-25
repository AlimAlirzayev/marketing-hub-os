"""Advisor (foresight organ) + sense.contradictions (reflex reconciliation).

All findings must be grounded in real signals; the LLM ranking is disabled here
so the suite is deterministic and offline. Event log is isolated to a temp file
so emit() never touches the real nervous-system log.
"""

import os
import tempfile
import unittest

from gateway import advisor, sense


class ContradictionReflex(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("SYSTEM_EVENTS_PATH")
        self._dir = tempfile.mkdtemp(prefix="adv_evt_")
        os.environ["SYSTEM_EVENTS_PATH"] = os.path.join(self._dir, "ev.jsonl")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("SYSTEM_EVENTS_PATH", None)
        else:
            os.environ["SYSTEM_EVENTS_PATH"] = self._saved

    def test_clean_when_no_events(self):
        self.assertEqual(sense.contradictions({"env": {}}), [])

    def test_flags_acquired_but_missing(self):
        sense.emit("credential", "RAPIDAPI_KEY acquired", {"provider": "rapidapi"})
        snap = {"env": {"RAPIDAPI_KEY": "MISSING"}}
        out = sense.contradictions(snap)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["key"], "RAPIDAPI_KEY")
        self.assertIn("MISSING", out[0]["reality"])

    def test_no_contradiction_when_key_actually_set(self):
        sense.emit("credential", "RAPIDAPI_KEY acquired", {"provider": "rapidapi"})
        snap = {"env": {"RAPIDAPI_KEY": "SET (len=36, …EF99)"}}
        self.assertEqual(sense.contradictions(snap), [])

    def test_dedups_repeated_claims(self):
        for _ in range(4):
            sense.emit("credential", "RAPIDAPI_KEY acquired", {"provider": "rapidapi"})
        out = sense.contradictions({"env": {"RAPIDAPI_KEY": "MISSING"}})
        self.assertEqual(len(out), 1)  # one finding, not four

    def test_ignores_non_credential_events(self):
        sense.emit("schedule", "RAPIDAPI_KEY acquired")  # wrong kind
        self.assertEqual(sense.contradictions({"env": {"RAPIDAPI_KEY": "MISSING"}}), [])


class AdvisorFindings(unittest.TestCase):
    def setUp(self):
        os.environ["ADVISOR_DISABLE_LLM"] = "1"  # deterministic, offline

    def tearDown(self):
        os.environ.pop("ADVISOR_DISABLE_LLM", None)

    def _snap(self, **over):
        base = {
            "env": {"RAPIDAPI_KEY": "SET (len=36, …EF99)"},
            "queue": {"queued": 0, "running": 0, "done": 0, "error": 0},
            "memory": {"turns": 0},
            "schedules": {"total": 0, "enabled": 0},
            "llm": {"cost_usd_today": 0.0},
            "git": {"head": "abc1234", "dirty": False},
            "recent_events": [],
            "contradictions": [],
        }
        base.update(over)
        return base

    def test_no_commits_is_a_risk(self):
        f = advisor.observe_state(self._snap(git={"head": "unknown", "dirty": True}))
        codes = {x.code for x in f}
        self.assertIn("no_commits", codes)
        self.assertTrue(any(x.level == "risk" and x.code == "no_commits" for x in f))

    def test_contradiction_sorts_first(self):
        f = advisor.observe_state(self._snap(
            contradictions=[{"key": "RAPIDAPI_KEY", "detail": "x"}],
            git={"head": "unknown", "dirty": True},
        ))
        self.assertEqual(f[0].code, "contradiction")  # risk, ranked above others

    def test_queue_stuck_without_worker(self):
        f = advisor.observe_state(self._snap(
            queue={"queued": 3, "running": 0, "done": 0, "error": 0}))
        self.assertIn("queue_idle", {x.code for x in f})

    def test_missing_credential_flagged(self):
        f = advisor.observe_state(self._snap(env={"RAPIDAPI_KEY": "MISSING"}))
        self.assertIn("missing_cred", {x.code for x in f})

    def test_spend_over_soft_ceiling(self):
        os.environ["ADVISOR_COST_WARN_USD"] = "0.5"
        try:
            import importlib
            from gateway import advisor as adv
            importlib.reload(adv)
            os.environ["ADVISOR_DISABLE_LLM"] = "1"
            f = adv.observe_state(self._snap(llm={"cost_usd_today": 1.25}))
            self.assertIn("llm_spend", {x.code for x in f})
        finally:
            os.environ.pop("ADVISOR_COST_WARN_USD", None)
            import importlib
            from gateway import advisor as adv
            importlib.reload(adv)

    def test_clean_snapshot_has_no_risk(self):
        f = advisor.observe_state(self._snap())
        self.assertFalse([x for x in f if x.level == "risk"])

    def test_brief_runs_offline_and_returns_text(self):
        text = advisor.brief(use_llm=False)
        self.assertIsInstance(text, str)
        self.assertIn("Məsləhətçi", text)

    def test_assess_shape(self):
        a = advisor.assess(use_llm=False)
        self.assertIn("findings", a)
        self.assertIn("risk_count", a)
        self.assertIsInstance(a["findings"], list)


if __name__ == "__main__":
    unittest.main()
