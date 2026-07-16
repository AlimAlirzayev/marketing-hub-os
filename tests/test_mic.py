"""The one microphone: every channel is a mic into ONE conversation + queue.

Contract:
  - mic.speak() enqueues from any source and returns a job id.
  - all channels share ONE conversation thread (MIC_THREAD), so history is not
    fragmented per chat/source.
  - the DEFAULT execution path is the single conversational brain (chat), not
    the council; the council is opt-in.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class _IsolatedJobsDB(unittest.TestCase):
    def setUp(self):
        from gateway import queue
        self.queue = queue
        self._saved = queue._DB_PATH
        queue._DB_PATH = Path(tempfile.mkdtemp()) / "jobs.sqlite"
        queue.init_db()

    def tearDown(self):
        self.queue._DB_PATH = self._saved


class MicBus(_IsolatedJobsDB):
    def test_speak_enqueues_and_labels_source(self):
        from gateway import mic
        with mock.patch.object(mic.sense, "emit") as emit:
            jid = mic.speak("salam", source="telegram", chat_id="42")
        job = self.queue.get(jid)
        self.assertEqual(job.task, "salam")
        self.assertEqual(job.source, "telegram")
        self.assertEqual(job.chat_id, "42")
        emit.assert_called_once()

    def test_every_source_shares_one_thread(self):
        from gateway import mic
        j1 = self.queue.get(mic.speak("a", source="telegram", chat_id="42"))
        j2 = self.queue.get(mic.speak("b", source="panel"))
        j3 = self.queue.get(mic.speak("c", source="codex"))
        # Different chat ids / sources, but the conversation thread is the same.
        self.assertEqual(mic.thread_for(j1), mic.MIC_THREAD)
        self.assertEqual(mic.thread_for(j1), mic.thread_for(j2))
        self.assertEqual(mic.thread_for(j2), mic.thread_for(j3))


class ConversationalDefault(_IsolatedJobsDB):
    def _job(self, task, source="telegram", chat_id="42"):
        import time
        from gateway.queue import Job
        return Job(id=1, source=source, chat_id=chat_id, task=task, status="running",
                   result=None, error=None, artifacts=[], created_at=time.time(),
                   started_at=None, finished_at=None, approved=False)

    def test_plain_task_uses_chat_brain_not_council(self):
        from gateway import executor, mic

        class _Used:
            provider, model = "gemini", "gemini-2.5-flash"

        seen = {}

        def _augment(system, task, thread=None):
            seen["system"] = system
            seen["thread"] = thread
            return system

        # Pin the conversational brain to free: this test asserts the free-router
        # chat path (mocked llm.complete). In the FULL suite (but not in isolation)
        # some earlier test leaks MIC_BRAIN=claude into the live os.environ, so
        # without this pin _converse takes the real claude_bridge path and the mock
        # is never hit. Pinning the selector is hermetic regardless of that leak.
        with mock.patch.object(executor, "_mic_brain", return_value="free"), \
             mock.patch.object(executor, "_council_should_run", return_value=False), \
             mock.patch.object(executor, "_choose_mode", return_value="plain"), \
             mock.patch.object(executor, "route", return_value="fake"), \
             mock.patch.object(executor.knowledge, "augment_system", side_effect=_augment), \
             mock.patch.object(executor.knowledge, "set_current_thread"), \
             mock.patch.object(executor.llm, "complete",
                               return_value=("Salam, buyur!", _Used())):
            out = executor.execute(self._job("necəsən?"))

        # answered by the conversational brain, tagged chat:
        self.assertIn("Salam, buyur!", out["result"])
        self.assertIn("chat:", out["result"])
        # with the conversational persona + the ONE shared thread:
        # The chat persona must be what drives this path (not the council/tools
        # persona) AND the self-card must ride along: without it the free floor
        # invents a system for itself (proven 2026-07-15 — it claimed GitLab and
        # GPT-4o). Identity-check was too strict once the card was appended.
        self.assertIn(executor._CHAT_SYSTEM, seen["system"])
        self.assertIn("GROUND TRUTH ABOUT YOURSELF", seen["system"])
        self.assertEqual(seen["thread"], mic.MIC_THREAD)

    def test_council_is_off_by_default(self):
        from gateway import executor
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_COUNCIL_ENABLED", None)
            self.assertFalse(executor._council_enabled())

    def test_council_opt_in(self):
        from gateway import executor
        with mock.patch.dict(os.environ, {"AI_COUNCIL_ENABLED": "1"}):
            self.assertTrue(executor._council_enabled())


class WorkerUnifiesMemory(_IsolatedJobsDB):
    def test_turns_recorded_to_one_thread_with_source_tag(self):
        from gateway import worker, mic
        jid = self.queue.submit("qiymət nədir?", source="panel")
        job = self.queue.claim_next()
        recorded = []

        with mock.patch.object(worker, "execute",
                               return_value={"result": "42 AZN", "artifacts": []}), \
             mock.patch.object(worker.queue, "claim_next", return_value=job), \
             mock.patch.object(worker.knowledge, "record_turn",
                               side_effect=lambda t, r, c: recorded.append((t, r, c))), \
             mock.patch.object(worker, "_notify"):
            worker.run_once()

        threads = {t for t, _r, _c in recorded}
        self.assertEqual(threads, {mic.MIC_THREAD})           # one shared thread
        self.assertTrue(any("[panel]" in c for _t, r, c in recorded if r == "user"))


if __name__ == "__main__":
    unittest.main()
