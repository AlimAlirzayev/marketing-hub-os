import unittest
from datetime import datetime, timezone

from scripts import system_context


class SystemContextTests(unittest.TestCase):
    def test_context_mentions_core_operating_contracts(self):
        text = system_context.render_context(datetime(2026, 6, 22, tzinfo=timezone.utc))
        self.assertIn("Ramin-OS is the unified", text)
        self.assertIn("Security is the highest law", text)
        self.assertIn("services.json", text)
        self.assertIn("Agent Radar", text)
        self.assertIn("Hugging Face Opportunity Radar", text)
        self.assertIn("AI Agents", text)

    def test_context_includes_service_registry_table(self):
        text = system_context.render_context(datetime(2026, 6, 22, tzinfo=timezone.utc))
        self.assertIn("| Key | Name | Port | Category | Launch | Target | Health |", text)
        self.assertIn("| hub |", text)
        self.assertIn("| hq |", text)

    def test_capability_paths_are_workspace_relative(self):
        text = system_context.render_context(datetime(2026, 6, 22, tzinfo=timezone.utc))
        self.assertIn("gateway/security.py", text)
        self.assertIn("gateway/hf_radar.py", text)
        self.assertIn("brain", text)
        self.assertIn("influencer-hunter", text)


if __name__ == "__main__":
    unittest.main()
