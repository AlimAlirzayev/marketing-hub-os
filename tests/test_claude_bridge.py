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


class BrainSelector(unittest.TestCase):
    def test_default_is_free(self):
        from gateway import executor
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MIC_BRAIN", None)
            self.assertEqual(executor._mic_brain(), "free")

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


if __name__ == "__main__":
    unittest.main()
