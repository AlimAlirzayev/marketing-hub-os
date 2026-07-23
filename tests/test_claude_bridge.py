"""The headless Claude Code bridge — 'this chat' on any microphone.

Subprocess is mocked so no real Claude Code runs (no quota spend). Covers: the
JSON contract, session persistence + resume, the MIC_BRAIN selector, and the
fail-safe fallback to the free brain.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class BridgeAsk(unittest.TestCase):
    def setUp(self):
        from gateway import claude_bridge
        self.cb = claude_bridge
        self._p = mock.patch.object(claude_bridge, "_SESSION_FILE",
                                    Path(tempfile.mkdtemp()) / "claude_session.json")
        self._p.start()
        self.addCleanup(self._p.stop)

    def _proc(self, result="Salam!", sid="sess-123", is_error=False, rc=0):
        payload = {"type": "result", "is_error": is_error, "result": result,
                   "session_id": sid, "total_cost_usd": 0.05, "num_turns": 1}
        return mock.Mock(returncode=rc, stdout=json.dumps(payload), stderr="")

    def test_parses_result_and_persists_session(self):
        with mock.patch.object(self.cb, "is_available", return_value=True), \
             mock.patch.object(self.cb.subprocess, "run", return_value=self._proc()) as run:
            text, meta = self.cb.ask("necəsən?", thread="main")
        self.assertEqual(text, "Salam!")
        self.assertEqual(meta["session_id"], "sess-123")
        # session saved -> next call resumes it
        self.assertEqual(self.cb._load_session("main"), "sess-123")

    def test_resumes_existing_session(self):
        self.cb._save_session("main", "old-sid")
        with mock.patch.object(self.cb, "is_available", return_value=True), \
             mock.patch.object(self.cb.subprocess, "run",
                               return_value=self._proc(sid="old-sid")) as run:
            self.cb.ask("davam", thread="main")
        cmd = run.call_args.args[0]
        self.assertIn("--resume", cmd)
        self.assertIn("old-sid", cmd)

    def test_error_result_raises(self):
        with mock.patch.object(self.cb, "is_available", return_value=True), \
             mock.patch.object(self.cb.subprocess, "run",
                               return_value=self._proc(result="", is_error=True)):
            with self.assertRaises(RuntimeError):
                self.cb.ask("x")

    def test_missing_cli_raises(self):
        with mock.patch.object(self.cb, "is_available", return_value=False):
            with self.assertRaises(RuntimeError):
                self.cb.ask("x")


class LimitDetection(unittest.TestCase):
    """Regression guard (2026-07-19): the Claude Code CLI reports a session/5h cap
    as an is_error result with api_error_status 429 + a "session limit" message.
    If _is_limit misses it, complete() raises HARD on the first account instead of
    rotating to the next -- defeating multi-account failover and leaving
    account_status falsely 'ready'."""

    def test_session_limit_429_is_a_cap(self):
        from gateway.claude_bridge import _is_limit
        real = ('claude -p failed: {"type":"result","is_error":true,'
                '"api_error_status":429,"result":"You have hit your session '
                'limit resets 2pm (UTC)"}')
        self.assertTrue(_is_limit(real))
        self.assertTrue(_is_limit("You have hit your session limit"))
        self.assertTrue(_is_limit("usage limit reached"))

    def test_a_normal_error_is_not_a_cap(self):
        from gateway.claude_bridge import _is_limit
        self.assertFalse(_is_limit("connection refused"))
        self.assertFalse(_is_limit("invalid json output"))


class BrainSelector(unittest.TestCase):
    def test_default_is_claude(self):
        # Operator policy (2026-07-19): Claude is the DEFAULT brain everywhere —
        # strongest model first, free cascade only on total cap. MIC_BRAIN=free
        # opts back down to the cheaper Gemini->Groq brain.
        from gateway import executor
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MIC_BRAIN", None)
            self.assertEqual(executor._mic_brain(), "claude")

    def test_converse_uses_claude_when_selected(self):
        from gateway import executor
        with mock.patch.dict(os.environ, {"MIC_BRAIN": "claude"}), \
             mock.patch("gateway.claude_bridge.is_available", return_value=True), \
             mock.patch("gateway.claude_bridge.ask",
                        return_value=("Claude cavabı", {"session_id": "abc12345"})):
            text, label = executor._converse("salam", "main")
        self.assertEqual(text, "Claude cavabı")
        self.assertIn("claude-code", label)

    def test_converse_falls_back_to_free_on_bridge_error(self):
        from gateway import executor

        class _Used:
            provider, model = "gemini", "gemini-2.5-flash"

        with mock.patch.dict(os.environ, {"MIC_BRAIN": "claude"}), \
             mock.patch("gateway.claude_bridge.is_available", return_value=True), \
             mock.patch("gateway.claude_bridge.ask", side_effect=RuntimeError("boom")), \
             mock.patch.object(executor, "route", return_value="fake"), \
             mock.patch.object(executor.knowledge, "augment_system",
                               side_effect=lambda s, *a, **k: s), \
             mock.patch.object(executor.llm, "complete",
                               return_value=("free cavab", _Used())), \
             mock.patch.object(executor.sense, "emit"):
            text, label = executor._converse("salam", "main")
        self.assertEqual(text, "free cavab")
        self.assertIn("gemini", label)

    def test_free_brain_never_calls_bridge(self):
        from gateway import executor

        class _Used:
            provider, model = "gemini", "x"

        with mock.patch.dict(os.environ, {"MIC_BRAIN": "free"}), \
             mock.patch("gateway.claude_bridge.ask") as bridge, \
             mock.patch.object(executor, "route", return_value="fake"), \
             mock.patch.object(executor.knowledge, "augment_system",
                               side_effect=lambda s, *a, **k: s), \
             mock.patch.object(executor.llm, "complete",
                               return_value=("free", _Used())):
            executor._converse("salam", "main")
        bridge.assert_not_called()


class ModelStepdown(unittest.TestCase):
    """A credit-gated / gone MODEL must step DOWN the ladder on the SAME account,
    never be mistaken for an account usage cap — which benched a HEALTHY account and
    dropped the whole premium brain to the free floor (2026-07-23, account-1 fable
    'requires usage credits')."""

    def setUp(self):
        from gateway import claude_bridge
        self.cb = claude_bridge
        self._sess = mock.patch.object(
            claude_bridge, "_SESSION_FILE",
            Path(tempfile.mkdtemp()) / "s.json")
        self._sess.start()
        self.addCleanup(self._sess.stop)
        self._saved_cd = dict(claude_bridge._model_cooldown)
        claude_bridge._model_cooldown.clear()

        def _restore():
            claude_bridge._model_cooldown.clear()
            claude_bridge._model_cooldown.update(self._saved_cd)
        self.addCleanup(_restore)

    def _mk(self, result, is_error=False, rc=0):
        payload = {"type": "result", "is_error": is_error, "result": result,
                   "session_id": "s", "total_cost_usd": 0.01, "num_turns": 1,
                   "model": "claude-sonnet-5"}
        return mock.Mock(returncode=rc, stdout=json.dumps(payload), stderr="")

    def test_credit_gate_is_model_gone_not_a_cap(self):
        msg = "Fable 5 requires usage credits. /model to switch models."
        self.assertTrue(self.cb._is_model_gone(msg))
        self.assertFalse(self.cb._is_limit(msg))

    def test_fable_credit_error_steps_down_to_next_model_same_account(self):
        with mock.patch.dict(os.environ,
                             {"CLAUDE_CHAT_LADDER": "claude-fable-5,claude-sonnet-5"}), \
             mock.patch.object(self.cb.subprocess, "run", side_effect=[
                 self._mk("Fable 5 requires usage credits. /model to switch models.",
                          is_error=True),
                 self._mk("Salam, buradayam."),
             ]) as run:
            text, meta = self.cb._run_once("salam", "t-step", None, 30, None)
        self.assertEqual(text, "Salam, buradayam.")   # sonnet answered
        self.assertEqual(run.call_count, 2)            # fable failed -> stepped down
        self.assertIn("claude-fable-5", self.cb._model_cooldown)  # model benched, not account


if __name__ == "__main__":
    unittest.main()
