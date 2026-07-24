"""Regression guards for typed execution outcomes and provider failure truth."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from gateway import llm, queue, worker
from gateway.contracts import ExecutionOutcome
from gateway.queue import Job


class ExecutionOutcomeContract(unittest.TestCase):
    def test_failure_requires_error_code(self):
        with self.assertRaises(ValueError):
            ExecutionOutcome(status="failure", result="provider down")

    def test_legacy_approval_shape_is_normalized(self):
        out = ExecutionOutcome.model_validate({
            "result": "approval required", "artifacts": [], "needs_approval": True,
        })
        self.assertEqual(out.status, "needs_approval")


class WorkerFailureSemantics(unittest.TestCase):
    def setUp(self):
        self.saved = queue._DB_PATH
        queue._DB_PATH = Path(tempfile.mkdtemp()) / "jobs.sqlite"
        queue.init_db()

    def tearDown(self):
        queue._DB_PATH = self.saved

    def test_failure_is_not_done_or_learned(self):
        job_id = queue.submit("provider failure test", source="panel")
        job = queue.claim_next()
        failed = ExecutionOutcome.failed(
            "Model providers are unavailable.", error_code="provider_quota", retryable=True,
        ).model_dump()
        with mock.patch.object(worker.queue, "claim_next", return_value=job), \
             mock.patch.object(worker, "execute", return_value=failed), \
             mock.patch.object(worker.knowledge, "record_turn") as record, \
             mock.patch.object(worker.knowledge, "reflect_job") as reflect, \
             mock.patch.object(worker.skills, "learn_from_job") as learn, \
             mock.patch.object(worker, "_notify"):
            self.assertTrue(worker.run_once())

        stored = queue.get(job_id)
        self.assertEqual(stored.status, "error")
        self.assertNotEqual(stored.status, "done")
        record.assert_not_called()
        reflect.assert_not_called()
        learn.assert_not_called()

    def test_delivery_rejects_artifacts_outside_job_output(self):
        outside = Path(tempfile.mkdtemp()) / "private.pdf"
        outside.write_bytes(b"not for delivery")
        self.assertIsNone(worker._safe_deliverable(str(outside)))


class UnifiedRouterFailure(unittest.TestCase):
    def test_router_error_is_not_swallowed_into_direct_gemini(self):
        from orchestrator.router import ModelChoice
        import llm_router

        choice = ModelChoice(provider="gemini", model="gemini-2.5-pro", reason="test")
        with mock.patch.object(llm_router, "complete", side_effect=llm_router.RouterError("all failed")), \
             mock.patch.dict(llm._PROVIDERS, {"gemini": mock.Mock(side_effect=AssertionError("direct retry"))}):
            with self.assertRaises(llm_router.RouterError):
                llm.complete(choice, "test")

    def test_daily_quota_is_not_retryable(self):
        self.assertFalse(llm._is_retryable(RuntimeError("429 daily quota exceeded")))


if __name__ == "__main__":
    unittest.main()
