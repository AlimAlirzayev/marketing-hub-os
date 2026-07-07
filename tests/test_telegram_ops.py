"""Telegram-side reliability: crash recovery, 409 conflicts, /status, singleton."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class RecoverStaleRunning(unittest.TestCase):
    def setUp(self):
        from gateway import queue
        self.queue = queue
        self._saved = queue._DB_PATH
        queue._DB_PATH = Path(tempfile.mkdtemp()) / "jobs.sqlite"
        queue.init_db()

    def tearDown(self):
        self.queue._DB_PATH = self._saved

    def test_orphaned_running_job_is_requeued(self):
        jid = self.queue.submit("some task", source="telegram", chat_id="42")
        claimed = self.queue.claim_next()          # -> running
        self.assertEqual(claimed.id, jid)
        # simulate the worker process dying here (nothing completes the job)
        recovered = self.queue.recover_stale_running()
        self.assertEqual(recovered, [jid])
        job = self.queue.get(jid)
        self.assertEqual(job.status, "queued")
        self.assertIsNone(job.started_at)

    def test_nothing_to_recover_is_a_noop(self):
        self.assertEqual(self.queue.recover_stale_running(), [])


class ConflictDetection(unittest.TestCase):
    def test_409_raises_conflict_error(self):
        from gateway import telegram
        resp = mock.Mock(status_code=409)
        with mock.patch.object(telegram.requests, "post", return_value=resp), \
             mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "x"}):
            with self.assertRaises(telegram.ConflictError):
                telegram._call("getUpdates")

    def test_200_passes_through(self):
        from gateway import telegram
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"ok": True, "result": []}
        with mock.patch.object(telegram.requests, "post", return_value=resp), \
             mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "x"}):
            self.assertEqual(telegram._call("getUpdates")["result"], [])


class StatusCommand(unittest.TestCase):
    def setUp(self):
        from gateway import bot
        self.bot = bot
        self.sent: list[str] = []
        snap = {
            "git": {"head": "abc1234", "dirty": True, "ahead": 2, "behind": 0},
            "queue": {"queued": 1, "running": 0, "awaiting_approval": 1, "error": 0},
            "llm": {"calls_today": 3, "cost_usd_today": 0.01},
        }
        patches = [
            mock.patch.object(bot.telegram, "send_message",
                              side_effect=lambda c, t: self.sent.append(t)),
            mock.patch.object(bot.sense, "snapshot", return_value=snap),
            mock.patch.object(bot.keyvault, "enabled", return_value=False),
            mock.patch.object(bot.queue, "list_jobs", return_value=[]),
            mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

    def test_owner_gets_ship_state(self):
        self.bot._handle_message({"chat": {"id": 42}, "text": "/status"})
        text = "\n".join(self.sent)
        self.assertIn("abc1234", text)
        self.assertIn("commit edilməmiş dəyişiklik VAR", text)
        self.assertIn("push gözləyən 2 commit", text)

    def test_non_owner_denied(self):
        self.bot._handle_message({"chat": {"id": 999}, "text": "/status"})
        self.assertTrue(any("Unauthorized" in t for t in self.sent))


class SupervisorSingleton(unittest.TestCase):
    def test_second_instance_refuses(self):
        from gateway import supervisor
        with mock.patch.dict(os.environ, {"SUPERVISOR_LOCK_PORT": "18899"}):
            first = supervisor._singleton_lock()
            self.assertIsNotNone(first)
            self.assertIsNone(supervisor._singleton_lock())   # already held
            first.close()
            third = supervisor._singleton_lock()              # released -> free
            self.assertIsNotNone(third)
            third.close()


if __name__ == "__main__":
    unittest.main()
