"""Browser agent v2 — unit guards for the Claude ReAct action parser and the
Claude-first / Gemini-fallback dispatch. No network/browser needed here; the live
loop is exercised separately (a real headless run)."""
import os
import unittest
from unittest import mock


class ActionParser(unittest.TestCase):
    def test_clean_json(self):
        from gateway.agent import _parse_action
        a = _parse_action('{"thought":"x","action":"open_page","args":{"url":"https://a.com"}}')
        self.assertEqual(a["action"], "open_page")
        self.assertEqual(a["args"]["url"], "https://a.com")

    def test_json_embedded_in_prose(self):
        from gateway.agent import _parse_action
        a = _parse_action('Sure, here it is:\n{"action":"read_page","args":{}}\nhope that helps')
        self.assertEqual(a["action"], "read_page")

    def test_code_fenced_json(self):
        from gateway.agent import _parse_action
        a = _parse_action('```json\n{"action":"finish","answer":"done"}\n```')
        self.assertEqual(a["action"], "finish")

    def test_non_json_is_none(self):
        from gateway.agent import _parse_action
        self.assertIsNone(_parse_action("I cannot do that."))
        self.assertIsNone(_parse_action(""))


class ClaudeFirstFallback(unittest.TestCase):
    def test_claude_used_when_it_succeeds(self):
        from gateway import agent
        with mock.patch.object(agent, "_run_browser_claude", return_value="CLAUDE OUT") as c, \
             mock.patch.object(agent, "_run_browser_gemini", return_value="GEMINI OUT") as g:
            out = agent.run_browser_agent("task", model="gemini-2.5-flash")
        self.assertEqual(out, "CLAUDE OUT")
        c.assert_called_once()
        g.assert_not_called()

    def test_falls_back_to_gemini_on_claude_failure(self):
        from gateway import agent
        with mock.patch.object(agent, "_run_browser_claude", side_effect=RuntimeError("capped")), \
             mock.patch.object(agent, "_run_browser_gemini", return_value="GEMINI OUT") as g:
            out = agent.run_browser_agent("task", model="gemini-2.5-flash")
        self.assertEqual(out, "GEMINI OUT")
        g.assert_called_once()

    def test_browser_brain_env_forces_gemini(self):
        from gateway import agent
        with mock.patch.dict(os.environ, {"BROWSER_BRAIN": "gemini"}), \
             mock.patch.object(agent, "_run_browser_claude") as c, \
             mock.patch.object(agent, "_run_browser_gemini", return_value="GEMINI OUT") as g:
            out = agent.run_browser_agent("task", model="gemini-2.5-flash")
        self.assertEqual(out, "GEMINI OUT")
        c.assert_not_called()
        g.assert_called_once()


if __name__ == "__main__":
    unittest.main()
