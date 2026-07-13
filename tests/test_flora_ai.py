import shutil
import unittest

from gateway import flora_ai
from gateway import permissions


class FloraAiMcpTests(unittest.TestCase):
    def test_status_detects_project_mcp_and_governance(self):
        status = flora_ai.build_flora_status(now=1_800_000_000)
        readiness = status["local_readiness"]

        self.assertTrue(readiness["settings_has_flora"])
        self.assertEqual(readiness["settings_url"], flora_ai.FLORA_MCP_URL)
        self.assertTrue(readiness["settings_command_available"])
        self.assertTrue(readiness["setup_script_has_flora"])
        self.assertTrue(readiness["manifest_has_flora"])
        self.assertTrue(readiness["manifest_blocks_customer_data"])
        self.assertTrue(readiness["manifest_blocks_public_posting"])
        self.assertTrue(readiness["manifest_requires_cost_control"])
        self.assertEqual(status["recommendation"]["status"], "configured_pending_oauth")
        self.assertEqual(status["recommendation"]["decision"], "activate_with_oauth_checkpoint")

    def test_doctor_is_green_without_checking_credentials(self):
        status = flora_ai.build_flora_status(now=1_800_000_000)
        self.assertEqual(flora_ai.doctor_errors(status), [])
        self.assertFalse(status["local_readiness"]["credential_presence_checked"])
        self.assertIn("intentionally not inspected", status["local_readiness"]["note"])

    def test_report_mentions_oauth_cost_and_local_touchpoints(self):
        status = flora_ai.build_flora_status(now=1_800_000_000)
        report = flora_ai.render_flora_report(status)

        self.assertIn("OAuth", report)
        self.assertIn("run_cost", report)
        self.assertIn("video-studio/generative_ads/model_matrix.flora.md", report)
        self.assertIn("https://developer.flora.ai/mcp/", report)

    def test_permission_manifest_blocks_risky_flora_actions(self):
        agent = permissions.get_agent("flora_ai_mcp")
        self.assertIsNotNone(agent)
        blocked_inputs = {item.casefold() for item in agent["blocked_inputs"]}
        blocked_actions = {item.casefold() for item in agent["blocked_actions"]}
        self.assertIn("customer data", blocked_inputs)
        self.assertIn("claims", blocked_inputs)
        self.assertIn("post publicly", blocked_actions)
        self.assertIn("run unapproved paid batches", blocked_actions)


class CrossMachineCommandTests(unittest.TestCase):
    """settings.json is git-tracked, so it TRAVELS — carrying the Windows twin's
    absolute path to its own vendored npx. A POSIX Path does not treat a backslash as
    a separator, so that path defeated every name check here: the doctor reported a
    perfectly working paid-Flora integration as broken on the VPS and the Mac, and the
    transport was misread as plain stdio. Resolution now falls back to a local npx.
    """

    WIN = r"C:\Users\a.alirzayev\ramin-os\video-studio\tools\node-v24.15.0-win-x64\npx.cmd"

    def test_basename_splits_a_windows_path_on_any_os(self):
        self.assertEqual(flora_ai._basename(self.WIN), "npx.cmd")

    @unittest.skipUnless(shutil.which("npx"), "node/npx not installed on this machine")
    def test_a_foreign_absolute_path_resolves_to_the_local_npx(self):
        resolved = flora_ai._resolve_command(self.WIN)
        self.assertTrue(resolved, "a machine with npx must still be able to launch flora")
        self.assertIn("npx", resolved.lower())

    def test_transport_survives_a_windows_command(self):
        server = {"command": self.WIN,
                  "args": ["-y", "mcp-remote", flora_ai.FLORA_MCP_URL]}
        self.assertEqual(flora_ai._flora_transport(server), "stdio_proxy_to_http")


if __name__ == "__main__":
    unittest.main()
