import unittest
import tempfile
import datetime as dt
import json
from pathlib import Path

from certification_coach import coach, journey, knowledge, source_verifier
from gateway import permissions


class CertificationCoachTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_runtime = knowledge.RUNTIME_DIR
        self._orig_index = knowledge.INDEX_PATH
        self._orig_memory = knowledge.MEMORY_PATH
        self._orig_source_runtime = source_verifier.RUNTIME_DIR
        self._orig_source_cache = source_verifier.SOURCE_CACHE_PATH
        self._orig_journey_runtime = journey.RUNTIME_DIR
        self._orig_journey_dir = journey.JOURNEY_DIR
        self._orig_journey_log = journey.EVENT_LOG_PATH
        knowledge.RUNTIME_DIR = Path(self._tmp.name)
        knowledge.INDEX_PATH = Path(self._tmp.name) / "vector_index.json"
        knowledge.MEMORY_PATH = Path(self._tmp.name) / "learner_memory.jsonl"
        source_verifier.RUNTIME_DIR = Path(self._tmp.name)
        source_verifier.SOURCE_CACHE_PATH = Path(self._tmp.name) / "source_checks.json"
        journey.RUNTIME_DIR = Path(self._tmp.name)
        journey.JOURNEY_DIR = Path(self._tmp.name) / "journeys"
        journey.EVENT_LOG_PATH = Path(self._tmp.name) / "journey_events.jsonl"

    def tearDown(self):
        knowledge.RUNTIME_DIR = self._orig_runtime
        knowledge.INDEX_PATH = self._orig_index
        knowledge.MEMORY_PATH = self._orig_memory
        source_verifier.RUNTIME_DIR = self._orig_source_runtime
        source_verifier.SOURCE_CACHE_PATH = self._orig_source_cache
        journey.RUNTIME_DIR = self._orig_journey_runtime
        journey.JOURNEY_DIR = self._orig_journey_dir
        journey.EVENT_LOG_PATH = self._orig_journey_log
        self._tmp.cleanup()

    def _write_source_cache(self, cert_id, verdict="verified"):
        cert = coach.certification(cert_id)
        checked_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = {
            "summary": {
                "checked_at": checked_at,
                "total": 1,
                "verified": 1 if verdict == "verified" else 0,
                "reachable_official": 1 if verdict == "reachable_official" else 0,
                "needs_review": 0,
                "failed": 0,
            },
            "checks": [
                {
                    "cert_id": cert_id,
                    "title": cert["title"],
                    "provider": cert["provider"],
                    "url": cert["source_url"],
                    "host": "support.google.com",
                    "official_domain": True,
                    "checked_at": checked_at,
                    "status_code": 200,
                    "page_title": cert["title"],
                    "final_url": cert["source_url"],
                    "matched_terms": ["analytics", "certification"],
                    "missing_terms": [],
                    "verdict": verdict,
                    "note": "Official source is test-verified.",
                }
            ],
        }
        source_verifier.SOURCE_CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")

    def test_catalog_has_source_linked_certifications(self):
        data = coach.catalog()
        self.assertGreaterEqual(len(data["certifications"]), 8)
        self.assertEqual(data["ethics_policy"]["status"], "exam_prep_only")
        for cert in data["certifications"]:
            self.assertTrue(cert["source_url"].startswith("https://"))
            self.assertIn("portfolio_task", cert)

    def test_roadmap_prioritizes_profile_and_keeps_exam_human_only(self):
        plan = coach.build_roadmap(
            {
                "role": "Performance marketing lead",
                "level": "intermediate",
                "weekly_hours": 7,
                "focus_tags": ["performance", "meta_ads", "analytics", "measurement"],
                "goals": "Meta media buying and GA4 measurement credibility",
            }
        )
        titles = [item["title"] for item in plan["recommended_stack"]]
        self.assertTrue(any("Meta" in title or "Measurement" in title for title in titles))
        blocked = " ".join(plan["ethics_policy"]["blocked"]).casefold()
        self.assertIn("take a live certification exam", blocked)
        controls = " ".join(item["agent_rule"] for item in plan["approval_rail"]).casefold()
        self.assertIn("human", controls)

    def test_mock_exam_is_original_practice_and_grades(self):
        mock = coach.mock_exam("meta_media_buying", count=4)
        self.assertIn("Original practice only", mock["policy"])
        self.assertNotIn("answer", mock["questions"][0])
        answers = {q["id"]: 1 for q in mock["questions"]}
        grade = coach.grade_mock("meta_media_buying", answers, count=4)
        self.assertEqual(grade["total"], mock["count"])
        self.assertGreaterEqual(grade["score"], 50)

    def test_permission_manifest_contains_coach_boundaries(self):
        agent = permissions.get_agent("marketing_certification_coach")
        self.assertIsNotNone(agent)
        self.assertIn("draft_only", agent["permissions"])
        blocked_actions = {item.casefold() for item in agent["blocked_actions"]}
        self.assertIn("take live exams", blocked_actions)
        self.assertIn("answer live exam questions", blocked_actions)
        self.assertIn("handle payments", blocked_actions)

    def test_knowledge_index_is_real_and_searchable(self):
        index = knowledge.rebuild_index()
        self.assertTrue(knowledge.INDEX_PATH.exists())
        self.assertGreaterEqual(len(index["documents"]), 20)
        hits = knowledge.search("Meta media buying optimization measurement", k=5, include_brain=False)
        self.assertTrue(hits)
        titles = " ".join(hit["title"] for hit in hits).casefold()
        self.assertIn("meta", titles)

    def test_plan_is_enriched_with_evidence_and_memory_status(self):
        profile = {
            "role": "Marketing specialist",
            "level": "intermediate",
            "weekly_hours": 6,
            "focus_tags": ["performance", "meta_ads", "analytics"],
            "goals": "Meta and GA4 roadmap",
        }
        plan = knowledge.enrich_plan(coach.build_roadmap(profile), profile)
        self.assertIn("knowledge", plan)
        self.assertTrue(plan["knowledge"]["evidence"])
        self.assertIn("vector_store", plan["knowledge"]["architecture"])

    def test_mock_grade_writes_local_learner_memory(self):
        mock = coach.mock_exam("google_analytics_ga4", count=3)
        grade = coach.grade_mock(
            "google_analytics_ga4",
            {q["id"]: 1 for q in mock["questions"]},
            count=3,
        )
        knowledge.record_mock_grade(grade)
        summary = knowledge.learner_summary()
        self.assertEqual(summary["mock_attempts"], 1)
        self.assertIn("google_analytics_ga4", summary["scores_by_cert"])

    def test_ask_falls_back_to_retrieved_evidence_without_llm(self):
        answer = knowledge.answer_question(
            "Why is Meta media buying harder than HubSpot content?",
            {"focus_tags": ["performance", "content"]},
            use_llm=False,
        )
        self.assertEqual(answer["mode"], "extractive_fallback")
        self.assertTrue(answer["evidence"])

    def test_source_verifier_checks_allowlist_and_terms(self):
        cert = coach.certification("meta_media_buying")

        def fake_fetch(_url):
            return {
                "ok": True,
                "status_code": 200,
                "final_url": cert["source_url"],
                "title": "Meta Media Buying Professional study guide",
                "plain_text": "Meta media buying campaign optimization measurement troubleshooting",
            }

        result = source_verifier.verify_certification(cert, fetcher=fake_fetch)
        self.assertTrue(result["official_domain"])
        self.assertEqual(result["verdict"], "verified")
        self.assertIn("media", result["matched_terms"])

    def test_source_verifier_writes_and_reads_cache(self):
        def fake_fetch(_url):
            return {
                "ok": True,
                "status_code": 200,
                "final_url": "https://example.com",
                "title": "Certification page",
                "plain_text": "certification analytics media buying strategy",
            }

        payload = source_verifier.verify_catalog(fetcher=fake_fetch)
        cached = source_verifier.load_cached()
        self.assertTrue(source_verifier.SOURCE_CACHE_PATH.exists())
        self.assertEqual(cached["summary"]["total"], payload["summary"]["total"])
        self.assertIn("checks", cached)

    def test_journey_blocks_until_readiness_gates_clear(self):
        cert_id = "google_analytics_ga4"
        self._write_source_cache(cert_id)
        view = journey.create_journey(
            cert_id,
            {
                "role": "Marketing analyst",
                "level": "foundation",
                "weekly_hours": 8,
                "focus_tags": ["analytics", "ga4", "measurement"],
            },
        )
        journey_id = view["summary"]["journey_id"]
        self.assertTrue(view["readiness"]["source"]["ok"])
        self.assertFalse(view["readiness"]["prep_ready"])

        targets = view["targets"]
        for _ in range(targets["study_tasks"]):
            view = journey.apply_action(journey_id, "study_task_completed")
        for _ in range(targets["drills"]):
            view = journey.apply_action(journey_id, "drill_completed")
        view = journey.apply_action(journey_id, "portfolio_completed", {"summary": "GA4 funnel measurement brief"})

        mock = coach.mock_exam(cert_id, count=6)
        grade = coach.grade_mock(cert_id, {q["id"]: 1 for q in mock["questions"]}, count=6)
        view = journey.record_mock_grade(journey_id, grade)
        self.assertGreaterEqual(view["readiness"]["score"], 85)
        self.assertTrue(view["readiness"]["prep_ready"])
        self.assertFalse(view["readiness"]["human_handoff_ready"])

        with self.assertRaises(ValueError):
            journey.apply_action(journey_id, "official_exam_setup_completed")

        view = journey.apply_action(journey_id, "readiness_review_requested")
        self.assertFalse(view["readiness"]["human_handoff_ready"])
        view = journey.apply_action(journey_id, "human_approval_granted", {"note": "I will take the exam myself."})
        self.assertTrue(view["readiness"]["can_start_official_setup"])

    def test_journey_requires_current_official_source(self):
        view = journey.create_journey("hubspot_content_marketing", {"weekly_hours": 6})
        self.assertFalse(view["readiness"]["source"]["ok"])
        self.assertEqual(view["summary"]["current_stage"]["id"], "source_verify")
        self.assertEqual(view["summary"]["current_stage"]["status"], "blocked")
        blockers = " ".join(view["readiness"]["blocked_reasons"]).casefold()
        self.assertIn("official source", blockers)

    def test_journey_redacts_sensitive_profile_fields(self):
        self._write_source_cache("hubspot_content_marketing")
        view = journey.create_journey(
            "hubspot_content_marketing",
            {"role": "Content marketer", "password": "do-not-store-this"},
        )
        raw = (journey.JOURNEY_DIR / f"{view['summary']['journey_id']}.json").read_text(encoding="utf-8")
        self.assertIn("[redacted]", raw)
        self.assertNotIn("do-not-store-this", raw)


if __name__ == "__main__":
    unittest.main()
