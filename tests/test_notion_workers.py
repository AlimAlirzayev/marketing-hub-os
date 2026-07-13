import unittest

from gateway import notion_workers
from gateway import permissions


class NotionWorkersTests(unittest.TestCase):
    def test_status_detects_worker_project_and_governance(self):
        status = notion_workers.build_notion_workers_status(now=1_800_000_000)
        readiness = status["local_readiness"]

        self.assertTrue(readiness["worker_project_exists"])
        self.assertTrue(readiness["package_has_workers_sdk"])
        self.assertTrue(readiness["source_has_expected_tools"])
        self.assertTrue(readiness["tools_are_read_only_hinted"])
        self.assertTrue(readiness["setup_script_exists"])
        self.assertTrue(readiness["cli_wrapper_exists"])
        self.assertTrue(readiness["manifest_has_notion_workers"])
        self.assertTrue(readiness["manifest_blocks_secrets"])
        self.assertTrue(readiness["manifest_blocks_customer_data"])
        self.assertTrue(readiness["manifest_blocks_public_posting"])
        self.assertIn(
            status["recommendation"]["status"],
            {"configured_cli_installed", "configured_needs_cli_setup"},
        )
        self.assertFalse(readiness["local_exec_smoke_tested"])

    def test_doctor_does_not_check_credentials(self):
        status = notion_workers.build_notion_workers_status(now=1_800_000_000)
        self.assertFalse(status["local_readiness"]["credential_presence_checked"])
        self.assertFalse(status["local_readiness"]["notion_login_checked"])
        self.assertIn("intentionally not inspected", status["local_readiness"]["note"])

    def test_report_mentions_checkpoint_and_tools(self):
        status = notion_workers.build_notion_workers_status(now=1_800_000_000)
        report = notion_workers.render_notion_workers_report(status)

        self.assertIn("screenRaminOsAction", report)
        self.assertIn("prepareRaminOsHandoff", report)
        self.assertIn("Human checkpoint", report)
        self.assertIn("https://developers.notion.com/workers/get-started/quickstart", report)

    def test_permission_manifest_blocks_risky_notion_worker_actions(self):
        agent = permissions.get_agent("notion_workers")
        self.assertIsNotNone(agent)
        blocked_inputs = {item.casefold() for item in agent["blocked_inputs"]}
        blocked_actions = {item.casefold() for item in agent["blocked_actions"]}
        self.assertIn("secrets", blocked_inputs)
        self.assertIn("customer data", blocked_inputs)
        self.assertIn(".env content", blocked_inputs)
        self.assertIn("post publicly", blocked_actions)
        self.assertIn("deploy workers without approval", blocked_actions)


if __name__ == "__main__":
    unittest.main()
