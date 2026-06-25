import unittest

from gateway.agent_radar import (
    AgentCandidate,
    build_marketing_os_scan,
    evaluate_candidate,
    render_marketing_os_scan_report,
)


class AgentRadarTests(unittest.TestCase):
    def test_customer_support_candidate_can_reach_sandbox(self):
        candidate = AgentCandidate(
            name="Support Triage Copilot",
            use_case="customer support triage and SLA analytics",
            description="Classifies tickets, detects sentiment, drafts replies, and reports SLA risk.",
            source_url="https://example.com/support-agent",
            repository_url="https://github.com/example/support-agent",
            owner="Example Team",
            requested_permissions=["network", "database_read"],
            evidence=["demo video", "public docs"],
        )
        result = evaluate_candidate(candidate)
        self.assertEqual(result.category, "customer_service")
        self.assertGreaterEqual(result.benefit_score, 70)
        self.assertIn(result.verdict, {"approved_for_sandbox", "sandbox_review"})

    def test_secret_and_payment_permissions_are_rejected(self):
        candidate = AgentCandidate(
            name="Revenue Autopilot",
            use_case="marketing automation",
            description="Fully autonomous agent that can pay, subscribe, and make money with no human.",
            source_url="https://example.com/revenue",
            requested_permissions=["payment", "secrets", "admin"],
            claims=["fully autonomous", "no human", "guaranteed make money"],
        )
        result = evaluate_candidate(candidate)
        self.assertEqual(result.verdict, "reject")
        self.assertGreaterEqual(result.risk_score, 75)

    def test_private_url_increases_risk_to_reject(self):
        candidate = AgentCandidate(
            name="Internal Scanner",
            use_case="data analytics",
            description="Scans internal dashboard data.",
            source_url="http://localhost:8501",
            requested_permissions=["local_network", "database_read"],
        )
        result = evaluate_candidate(candidate)
        self.assertEqual(result.verdict, "reject")

    def test_verdict_never_promises_production_approval(self):
        candidate = AgentCandidate(
            name="Analytics Reporter",
            use_case="data analytics reports",
            description="Builds KPI dashboard summaries.",
            source_url="https://example.com/analytics",
            repository_url="https://github.com/example/analytics",
            owner="Example Team",
            evidence=["docs"],
        )
        result = evaluate_candidate(candidate)
        self.assertIn(result.verdict, {"approved_for_sandbox", "sandbox_review", "quarantine", "reject"})
        self.assertNotEqual(result.verdict, "approved_for_production")

    def test_marketing_os_scan_prioritizes_governance(self):
        scan = build_marketing_os_scan(now=1_800_000_000)
        self.assertEqual(scan["recommendation"]["name"], "Agent Governance Control Plane")
        self.assertEqual(scan["recommendation"]["decision"], "reinforce_current_module")
        self.assertGreaterEqual(scan["system_fit_summary"]["overall_rating"], 80)

    def test_marketing_os_scan_has_no_production_approval(self):
        scan = build_marketing_os_scan(now=1_800_000_000)
        verdicts = [item["evaluation"]["verdict"] for item in scan["ranked_candidates"]]
        self.assertNotIn("approved_for_production", verdicts)
        self.assertTrue(all("production" not in item["decision"] for item in scan["ranked_candidates"]))

    def test_marketing_os_scan_report_contains_world_comparison(self):
        scan = build_marketing_os_scan(now=1_800_000_000)
        report = render_marketing_os_scan_report(scan)
        self.assertIn("World Comparison", report)
        self.assertIn("Microsoft Agent 365", report)
        self.assertIn("ServiceNow AI Control Tower", report)


if __name__ == "__main__":
    unittest.main()
