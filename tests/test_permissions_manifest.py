import unittest

from gateway import permissions


class PermissionManifestTests(unittest.TestCase):
    def test_manifest_validates(self):
        errors = permissions.validate_manifest()
        self.assertEqual(errors, [])

    def test_context7_is_read_only(self):
        agent = permissions.get_agent("context7_docs_grounding")
        self.assertIsNotNone(agent)
        self.assertEqual(agent["status"], "approved_read_only")
        self.assertIn("read_only", agent["permissions"])
        self.assertNotIn("draft_only", agent["permissions"])

    def test_cx_resolution_blocks_sending(self):
        agent = permissions.get_agent("cx_resolution_agent")
        self.assertIsNotNone(agent)
        blocked = {item.casefold() for item in agent["blocked_actions"]}
        self.assertIn("send replies", blocked)
        self.assertIn("post publicly", blocked)
        self.assertIn("approval_required", agent["permissions"])

    def test_flora_mcp_is_draft_only_and_cost_gated(self):
        agent = permissions.get_agent("flora_ai_mcp")
        self.assertIsNotNone(agent)
        self.assertEqual(agent["status"], "sandbox_draft_only")
        self.assertIn("draft_only", agent["permissions"])
        self.assertIn("approval_required", agent["permissions"])
        blocked_inputs = {item.casefold() for item in agent["blocked_inputs"]}
        blocked_actions = {item.casefold() for item in agent["blocked_actions"]}
        controls = " ".join(agent["required_controls"]).casefold()
        self.assertIn("customer data", blocked_inputs)
        self.assertIn("post publicly", blocked_actions)
        self.assertIn("manage billing", blocked_actions)
        self.assertIn("run_cost", controls)

    def test_unknown_agent_permission_fails_closed(self):
        with self.assertRaises(permissions.PermissionManifestError):
            permissions.require_allowed("missing_agent", "read_only")

    def test_unlisted_permission_fails_closed(self):
        with self.assertRaises(permissions.PermissionManifestError):
            permissions.require_allowed("context7_docs_grounding", "sandbox")


if __name__ == "__main__":
    unittest.main()
