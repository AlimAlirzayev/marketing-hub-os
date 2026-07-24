"""Regression guard for the workspace-wide user-visible delivery contract."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STANDARD = "docs/USER_VISIBLE_DELIVERY_STANDARD.md"


class UserVisibleDeliveryPolicyTests(unittest.TestCase):
    def test_authoritative_standard_exists_and_defines_completion_gate(self):
        text = (ROOT / STANDARD).read_text(encoding="utf-8")
        self.assertIn("## Definition of Done", text)
        self.assertIn("The Ramin-OS Hub is the canonical front door", text)
        self.assertIn("status is **partial**", text)
        self.assertIn("full operator journey", text)

    def test_major_agent_entrypoints_load_the_same_standard(self):
        entrypoints = (
            "AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
            ".github/copilot-instructions.md",
            "claude-agents/CLAUDE.md",
        )
        for relative in entrypoints:
            with self.subTest(entrypoint=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(STANDARD, text)
                self.assertIn("partial", text.lower())
                self.assertIn("Hub", text)

    def test_runtime_brain_cannot_call_hidden_backend_complete(self):
        from gateway import executor

        self.assertIn("never call a hidden backend complete", executor._SYSTEM)
        self.assertIn("validate the journey from the user side", executor._SYSTEM)
        self.assertIn("never call a hidden backend complete", executor._CHAT_SYSTEM)


if __name__ == "__main__":
    unittest.main()
