import unittest

from gateway.hf_radar import (
    HFOpportunity,
    build_hf_scan,
    evaluate_opportunity,
    render_hf_scan_report,
)


class HuggingFaceRadarTests(unittest.TestCase):
    def test_scan_prioritizes_private_rag(self):
        scan = build_hf_scan(now=1_800_000_000)
        self.assertEqual(
            scan["recommendation"]["name"],
            "Private RAG Embedding Layer (TEI + HF embedding models)",
        )
        self.assertEqual(scan["recommendation"]["decision"], "pilot_now_private_path")
        self.assertGreaterEqual(scan["system_fit_summary"]["overall_rating"], 90)

    def test_hosted_sensitive_path_is_not_approved(self):
        opportunity = HFOpportunity(
            name="Hosted Claims Assistant",
            category="hosted_inference",
            use_case="analyze customer claims with hosted inference",
            description="External API analyzes insurance claims.",
            integration_points=["cx-command-center"],
            data_boundary="external_hosted",
            business_impact=90,
            cost_leverage=50,
            implementation_readiness=70,
            implementation_effort=2,
            external_calls=True,
            requires_token=True,
            handles_sensitive_data=True,
            sensitive_data_allowed=False,
            risks=["customer data leaves RAMIN OS"],
        )
        result = evaluate_opportunity(opportunity)
        self.assertIn(result.verdict, {"quarantine", "reject"})
        self.assertGreaterEqual(result.risk_score, 70)
        self.assertIn("Sensitive or customer data must stay out of this workflow.", result.required_controls)

    def test_no_production_approval_verdict(self):
        scan = build_hf_scan(now=1_800_000_000)
        verdicts = [item["evaluation"]["verdict"] for item in scan["ranked_opportunities"]]
        self.assertNotIn("approved_for_production", verdicts)
        decisions = [item["evaluation"]["decision"] for item in scan["ranked_opportunities"]]
        self.assertTrue(all("production" not in decision for decision in decisions))

    def test_report_contains_policy_and_sources(self):
        scan = build_hf_scan(now=1_800_000_000)
        report = render_hf_scan_report(scan)
        self.assertIn("Hosted HF services are for public/synthetic PoCs", report)
        self.assertIn("Text Embeddings Inference", report)
        self.assertIn("Inference Providers", report)
        self.assertIn("Desktop research source", report)

    def test_local_readiness_does_not_inspect_credentials(self):
        scan = build_hf_scan(now=1_800_000_000)
        self.assertIn("Credential presence is intentionally not inspected", scan["local_readiness"]["note"])


if __name__ == "__main__":
    unittest.main()
