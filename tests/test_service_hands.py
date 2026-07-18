"""Service hands: the studio_api CLI gate, the paging scrub, the bridge
allowlist, and the workspace self-check loop's pure pieces.

Everything runs offline — HTTP and subprocess seams are mocked.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class StudioCliGate(unittest.TestCase):
    def setUp(self):
        from gateway import studio_api
        self.sa = studio_api

    def test_help_and_unknown(self):
        self.assertIn("usage", self.sa._cli([]))
        self.assertIn("unknown command", self.sa._cli(["frobnicate"]))

    def test_list_routes_to_list_studios(self):
        with mock.patch.object(self.sa, "list_studios", return_value="ads: ..."):
            self.assertEqual(self.sa._cli(["list"]), "ads: ...")

    def test_call_passes_through_the_same_gate(self):
        with mock.patch.object(self.sa, "call_studio_api",
                               return_value="HTTP 200 ok") as call:
            out = self.sa._cli(["call", "seo", "/api/health",
                                "--method", "GET", "--body", ""])
        self.assertEqual(out, "HTTP 200 ok")
        call.assert_called_once_with("seo", "/api/health", method="GET", json_body="")

    def test_risky_post_is_still_blocked_via_cli(self):
        # The CLI must not open a second, softer door: same _RISKY gate applies.
        out = self.sa._cli(["call", "ads", "/api/campaign/launch",
                            "--method", "POST"])
        self.assertIn("BLOCKED", out)


class PagingScrub(unittest.TestCase):
    def setUp(self):
        from gateway import studio_api
        self.sa = studio_api

    def test_paging_block_is_dropped(self):
        raw = json.dumps({"data": [{"id": 1}], "paging": {
            "next": "https://graph.facebook.com/x?access_token=EAAB123SECRET"}})
        out = self.sa.scrub_response(raw)
        self.assertNotIn("EAAB123SECRET", out)
        self.assertNotIn("paging", out)
        self.assertIn('"data"', out)

    def test_token_param_in_plain_text_is_redacted(self):
        out = self.sa.scrub_response("see https://g/x?access_token=EAABZZZ&b=1")
        self.assertNotIn("EAABZZZ", out)
        self.assertIn("access_token=<redacted>", out)

    def test_non_json_passes_through(self):
        self.assertEqual(self.sa.scrub_response("<html>ok</html>"), "<html>ok</html>")


class BridgeAllowlist(unittest.TestCase):
    def setUp(self):
        from gateway import claude_bridge
        self.cb = claude_bridge
        self._p = mock.patch.object(claude_bridge, "_SESSION_FILE",
                                    Path(tempfile.mkdtemp()) / "claude_session.json")
        self._p.start()
        self.addCleanup(self._p.stop)

    def _proc(self):
        payload = {"type": "result", "is_error": False, "result": "ok",
                   "session_id": "s1", "total_cost_usd": 0.01, "num_turns": 1}
        return mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")

    def test_ask_allowlists_the_studio_cli_door(self):
        with mock.patch.object(self.cb, "is_available", return_value=True), \
             mock.patch.object(self.cb.subprocess, "run",
                               return_value=self._proc()) as run:
            self.cb.ask("SEO auditi et", thread="t-hands")
        cmd = run.call_args.args[0]
        self.assertIn("--allowedTools", cmd)
        allowed = cmd[cmd.index("--allowedTools") + 1]
        self.assertIn("gateway.studio_api", allowed)
        self.assertNotIn("rm ", allowed)

    def test_hands_kill_switch(self):
        with mock.patch.dict(os.environ, {"CLAUDE_BRIDGE_HANDS": "0"}), \
             mock.patch.object(self.cb, "is_available", return_value=True), \
             mock.patch.object(self.cb.subprocess, "run",
                               return_value=self._proc()) as run:
            self.cb.ask("salam", thread="t-nohands")
        self.assertNotIn("--allowedTools", run.call_args.args[0])


class WorkspaceVerify(unittest.TestCase):
    def setUp(self):
        from gateway import executor
        self.ex = executor
        self.ws = Path(tempfile.mkdtemp())

    def test_empty_workspace_is_not_a_failure(self):
        # Conversational/tool-only jobs build nothing; nothing to verify.
        self.assertEqual(self.ex._verify_workspace(self.ws), [])

    def test_clean_build_passes(self):
        (self.ws / "app.py").write_text("print('ok')\n", encoding="utf-8")
        (self.ws / "cfg.json").write_text('{"a": 1}', encoding="utf-8")
        (self.ws / "style.css").write_text("body{}", encoding="utf-8")
        (self.ws / "index.html").write_text(
            '<link href="style.css"><a href="https://x.az">x</a>', encoding="utf-8")
        self.assertEqual(self.ex._verify_workspace(self.ws), [])

    def test_broken_build_is_reported(self):
        (self.ws / "app.py").write_text("def broken(:\n", encoding="utf-8")
        (self.ws / "cfg.json").write_text("{nope", encoding="utf-8")
        (self.ws / "index.html").write_text('<img src="missing.png">', encoding="utf-8")
        (self.ws / "empty.txt").write_text("", encoding="utf-8")
        problems = "\n".join(self.ex._verify_workspace(self.ws))
        for cue in ("app.py", "cfg.json", "missing.png", "empty.txt"):
            self.assertIn(cue, problems)

    def test_verify_note_is_honest_azerbaijani(self):
        note = self.ex._verify_note(["index.html: broken local reference 'x.css'"])
        self.assertIn("Özünü-yoxlama", note)
        self.assertIn("x.css", note)


class AdsWatchRail(unittest.TestCase):
    def test_cues_route_to_the_rail_not_chat(self):
        from gateway import executor
        self.assertTrue(executor._is_ads_watch("reklam nəbzi"))
        self.assertTrue(executor._is_ads_watch("/adswatch"))
        # ordinary ads questions stay OFF the rail
        self.assertFalse(executor._is_ads_watch("reklamlar necə gedir?"))
        self.assertFalse(executor._is_ads_watch("kampaniya xərcləri barədə danış"))


if __name__ == "__main__":
    unittest.main()
