"""Token/cost harmony — one router brain, symmetric model default, tiered council,
unified spend board. No network/LLM calls."""

import datetime
import json
import os
import tempfile
import unittest


class OneRouterBrain(unittest.TestCase):
    """gateway.llm maps a routing decision to the unified router's tier (FIX-1)."""

    def _llm(self):
        try:
            from gateway import llm
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"gateway.llm deps unavailable: {exc}")
        return llm

    def test_tier_for_smart_vs_cheap(self):
        llm = self._llm()
        from orchestrator.router import ModelChoice
        smart = ModelChoice(provider="anthropic", model="claude-sonnet-4-6", reason="")
        pro = ModelChoice(provider="gemini", model="gemini-2.5-pro", reason="")
        cheap = ModelChoice(provider="gemini", model="gemini-2.5-flash", reason="")
        self.assertEqual(llm._tier_for(smart), "smart")
        self.assertEqual(llm._tier_for(pro), "smart")
        self.assertEqual(llm._tier_for(cheap), "cheap")


class SymmetricModelDefault(unittest.TestCase):
    """No more pro-vs-flash split for the same mode (FIX-2)."""

    def test_single_agent_model_constant(self):
        try:
            from gateway import executor
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"executor deps unavailable: {exc}")
        self.assertTrue(isinstance(executor.AGENT_MODEL, str) and executor.AGENT_MODEL)

    def test_no_hardcoded_model_default_split_in_source(self):
        import pathlib
        src = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "executor.py"
        text = src.read_text(encoding="utf-8")
        # the 'pro' default must be gone entirely (it caused the asymmetry)
        self.assertEqual(text.count('os.getenv("MODEL_AGENT", "gemini-2.5-pro")'), 0)
        # the flash default may appear EXACTLY once — the single AGENT_MODEL constant
        self.assertEqual(text.count('os.getenv("MODEL_AGENT", "gemini-2.5-flash")'), 1)
        # the mode branches reference the constant, not their own inline default
        self.assertGreaterEqual(text.count("agent_model = AGENT_MODEL"), 4)


class TieredCouncil(unittest.TestCase):
    """Council fires for deliberation-worthy tiers, not every trivial task (FIX-3)."""

    def _executor(self):
        try:
            from gateway import executor
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"executor deps unavailable: {exc}")
        return executor

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("AI_COUNCIL_ENABLED", "AI_COUNCIL_TIERS")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_complex_task_runs_council_simple_does_not(self):
        ex = self._executor()
        os.environ["AI_COUNCIL_ENABLED"] = "1"
        os.environ.pop("AI_COUNCIL_TIERS", None)  # default = complex
        self.assertTrue(ex._council_should_run("refactor and debug the payment module"))
        self.assertFalse(ex._council_should_run("write 3 instagram captions"))

    def test_all_tier_restores_fire_on_everything(self):
        ex = self._executor()
        os.environ["AI_COUNCIL_ENABLED"] = "1"
        os.environ["AI_COUNCIL_TIERS"] = "all"
        self.assertTrue(ex._council_should_run("write 3 instagram captions"))

    def test_master_switch_off(self):
        ex = self._executor()
        os.environ["AI_COUNCIL_ENABLED"] = "0"
        self.assertFalse(ex._council_should_run("refactor the architecture"))


class UnifiedSpendBoard(unittest.TestCase):
    """sense reads the router's usage log into the live board (FIX-4)."""

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._saved = os.environ.get("LLM_USAGE_PATH")
        self._path = os.path.join(self._dir, "llm_usage.jsonl")
        os.environ["LLM_USAGE_PATH"] = self._path

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("LLM_USAGE_PATH", None)
        else:
            os.environ["LLM_USAGE_PATH"] = self._saved

    def test_counts_today_spend_by_model(self):
        from gateway import sense
        today = datetime.date.today().isoformat()
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": today + "T08:00:00", "model": "gemini/gemini-2.5-flash",
                                "prompt_tokens": 100, "completion_tokens": 40, "cost_usd": 0.0}) + "\n")
            f.write(json.dumps({"ts": today + "T09:00:00", "model": "gemini/gemini-2.5-flash",
                                "prompt_tokens": 50, "completion_tokens": 10, "cost_usd": 0.0}) + "\n")
            f.write(json.dumps({"ts": "2020-01-01T00:00:00", "model": "old",
                                "prompt_tokens": 999, "completion_tokens": 999, "cost_usd": 9.0}) + "\n")
        st = sense._llm_state()
        self.assertEqual(st["calls_today"], 2)          # the 2020 row excluded
        self.assertEqual(st["in_tok"], 150)
        self.assertEqual(st["by_model"]["gemini/gemini-2.5-flash"], 2)

    def test_pulse_includes_llm_section(self):
        from gateway import sense
        self.assertIn("LLM", sense.pulse())


if __name__ == "__main__":
    unittest.main()
