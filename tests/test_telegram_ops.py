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


class SelfDocumentingReject(unittest.TestCase):
    """A bare 'Unauthorized' is what made the owner-id mix-up unfixable. The
    rejection must now reveal the sender's id, the configured owner, its source
    env var, and the exact fix."""

    def setUp(self):
        from gateway import bot
        self.bot = bot
        self.sent: list[str] = []
        p = [
            mock.patch.object(bot.telegram, "send_message",
                              side_effect=lambda c, t: self.sent.append(t)),
            mock.patch.object(bot.sense, "emit"),
        ]
        for x in p:
            x.start()
        self.addCleanup(lambda: [x.stop() for x in p])

    def test_wrong_owner_reveals_id_owner_and_fix(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "784455040"},
                             clear=False):
            os.environ.pop("GATEWAY_OWNER_ID", None)
            self.bot._handle_message({"chat": {"id": 1923265939}, "text": "/status"})
        text = "\n".join(self.sent)
        self.assertIn("1923265939", text)          # your id
        self.assertIn("784455040", text)           # the wrong configured owner
        self.assertIn("TELEGRAM_OWNER_CHAT_ID=1923265939", text)  # exact fix

    def test_legacy_gateway_owner_id_is_named_as_culprit(self):
        with mock.patch.dict(os.environ, {"GATEWAY_OWNER_ID": "784455040"},
                             clear=False):
            os.environ.pop("TELEGRAM_OWNER_CHAT_ID", None)
            self.bot._handle_message({"chat": {"id": 1923265939}, "text": "/jobs"})
        text = "\n".join(self.sent)
        self.assertIn("GATEWAY_OWNER_ID", text)     # names the leaking var

    def test_unset_owner_tells_how_to_claim(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_OWNER_CHAT_ID", None)
            os.environ.pop("GATEWAY_OWNER_ID", None)
            self.bot._handle_message({"chat": {"id": 555}, "text": "/status"})
        text = "\n".join(self.sent)
        self.assertIn("kilidlidir", text)
        self.assertIn("TELEGRAM_OWNER_CHAT_ID=555", text)


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
