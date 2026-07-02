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


if __name__ == "__main__":
    unittest.main()
