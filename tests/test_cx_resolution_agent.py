import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "cx-command-center" / "resolution_agent.py"
spec = importlib.util.spec_from_file_location("cx_resolution_agent", MODULE_PATH)
resolution_agent = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(resolution_agent)


class CxResolutionAgentTests(unittest.TestCase):
    def sample_report(self):
        item = {
            "id": 42,
            "channel": "google_review",
            "category": "delay",
            "sentiment": "very_negative",
            "severity": "critical",
            "status": "new",
            "assigned_team": "Operations",
            "sla_due_at": "2020-01-01T00:00:00+00:00",
            "urgency_score": 95,
            "text": "My phone is +994 50 123 45 67 and nobody answered me.",
            "ai_summary": "Customer reports a delayed response.",
            "recommended_reply": "We are sorry for the delay. Please share details privately.",
        }
        return {
            "totals": {
                "open": 1,
                "overdue": 1,
                "critical_open": 1,
                "risk_score": 88,
            },
            "root_causes": [{"category": "delay", "count": 1, "team": "Operations"}],
            "priority_queue": [item],
            "overdue_queue": [item],
        }

    def test_plan_is_draft_only(self):
        plan = resolution_agent.build_plan(self.sample_report(), days=7)
        self.assertEqual(plan["mode"], "sandbox_draft_only")
        self.assertFalse(plan["send_allowed"])
        self.assertFalse(plan["status_write_allowed"])
        self.assertTrue(plan["approval_required"])

    def test_pii_is_redacted_in_customer_text(self):
        plan = resolution_agent.build_plan(self.sample_report(), days=7)
        draft = plan["draft_queue"][0]
        self.assertIn("[redacted-phone]", draft["customer_text_redacted"])
        self.assertNotIn("+994 50 123 45 67", draft["customer_text_redacted"])

    def test_draft_contains_human_approval_checklist(self):
        plan = resolution_agent.build_plan(self.sample_report(), days=7)
        draft = plan["draft_queue"][0]
        self.assertTrue(draft["approval_required"])
        self.assertFalse(draft["send_allowed"])
        self.assertTrue(any("Approve" in item or "approval" in item.lower() for item in draft["approval_checklist"]))

    def test_empty_report_is_safe(self):
        plan = resolution_agent.build_plan({"totals": {}, "priority_queue": [], "overdue_queue": []}, days=7)
        self.assertFalse(plan["send_allowed"])
        self.assertEqual(plan["draft_queue"], [])
        self.assertIn("No urgent CX recovery work found", " ".join(plan["next_actions"]))


if __name__ == "__main__":
    unittest.main()
