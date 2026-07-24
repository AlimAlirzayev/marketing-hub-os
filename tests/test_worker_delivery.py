"""Guards for the human-facing Telegram delivery in gateway.worker.

The executor tags every stored result with a leading `_[label]_` source tag
(the panel renders it as a chip). A human in Telegram must never see that tag
raw — this is exactly the 2026-07-10 owner complaint (jobs 36-39: replies
opened with `_[chat:router:...]_`).
"""

import unittest
import time
import tempfile
from pathlib import Path
from unittest import mock

from gateway.queue import Job
from gateway.worker import _TelegramProgressRelay, _split_source_tag


class SplitSourceTag(unittest.TestCase):
    def test_chat_tag_is_split_off(self):
        label, clean = _split_source_tag(
            "_[chat:router:gemini/gemini-2.5-flash]_\n\nSalam, necəsən?"
        )
        self.assertEqual(label, "chat:router:gemini/gemini-2.5-flash")
        self.assertEqual(clean, "Salam, necəsən?")

    def test_work_labels_are_split_off_too(self):
        label, clean = _split_source_tag("_[browser:gemini-2.5-pro]_\n\nHesabat hazır.")
        self.assertEqual(label, "browser:gemini-2.5-pro")
        self.assertEqual(clean, "Hesabat hazır.")

    def test_untagged_result_passes_through(self):
        label, clean = _split_source_tag("❌ **İcra xətası:** boom")
        self.assertIsNone(label)
        self.assertEqual(clean, "❌ **İcra xətası:** boom")

    def test_tag_only_matches_at_the_start(self):
        text = "Cavabın içində _[chat:x]_ görünsə, toxunulmur."
        label, clean = _split_source_tag(text)
        self.assertIsNone(label)
        self.assertEqual(clean, text)


class ProgressRelay(unittest.TestCase):
    def test_job_scoped_events_are_debounced_into_one_card(self):
        job = Job(
            id=9,
            source="telegram",
            chat_id="42",
            task="iş",
            status="running",
            result=None,
            error=None,
            artifacts=[],
            created_at=1.0,
            started_at=2.0,
            finished_at=None,
            telegram_status_message_id=77,
        )
        relay = _TelegramProgressRelay(job, interval=0.01)
        with mock.patch("gateway.worker._progress") as progress:
            relay.start()
            from gateway import sense
            sense.emit("progress", "birinci", {"job": 8})
            sense.emit("progress", "ikinci", {"job": 9})
            time.sleep(0.35)
            relay.close()
        progress.assert_called_once()
        self.assertEqual(progress.call_args.args[1], "ikinci")

    def test_worker_commits_cancel_at_executor_checkpoint(self):
        from gateway import queue, worker

        saved = queue._DB_PATH
        queue._DB_PATH = Path(tempfile.mkdtemp()) / "jobs.sqlite"
        try:
            job_id = queue.submit("uzun iş", source="telegram", chat_id="42")

            def execute_with_checkpoint(job):
                from gateway import sense
                sense.emit("progress", "araşdırılır", {"job": job.id})
                self.assertEqual(queue.request_cancel(job.id), "requested")
                queue.cancellation_checkpoint(job.id)

            with mock.patch.object(worker, "execute", side_effect=execute_with_checkpoint), \
                 mock.patch.object(worker.telegram, "is_configured", return_value=False):
                self.assertTrue(worker.run_once())

            self.assertEqual(queue.get(job_id).status, "cancelled")
            self.assertEqual(
                queue.get(job_id).progress_stage,
                "✕ Dayandırıldı — növbəti təhlükəsiz checkpoint-də icra kəsildi.",
            )
        finally:
            queue._DB_PATH = saved


if __name__ == "__main__":
    unittest.main()
