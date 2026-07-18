"""The human checkpoint: outward actions park for approval, drafting stays free.

Covers the full rail end to end:
  security.evaluate_checkpoint -> executor parks -> worker notifies ->
  bot /approve re-queues (approved=1) -> executor lets it through.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class _IsolatedJobsDB(unittest.TestCase):
    """Point gateway.queue at a throwaway sqlite file for each test."""

    def setUp(self):
        from gateway import queue
        self.queue = queue
        self._saved_db = queue._DB_PATH
        queue._DB_PATH = Path(tempfile.mkdtemp()) / "jobs.sqlite"
        queue.init_db()

    def tearDown(self):
        self.queue._DB_PATH = self._saved_db


class CheckpointClassifier(unittest.TestCase):
    def _dec(self, task):
        from gateway import security
        return security.evaluate_checkpoint(task)

    def test_drafting_is_free(self):
        # Writing/ideating ABOUT posts must not park — that's the daily bread.
        for task in (
            "Write 3 Instagram post ideas for a car insurance brand",
            "KASKO üçün 3 kampaniya ideyası hazırla",
            "Summarize Q2 ad performance",
            "Draft an email announcement for the team",
            "Yaratdığın vizual kontentləri bura göndər baxım",
            "Send the generated image here so I can review it",
        ):
            self.assertTrue(self._dec(task).allowed, task)

    def test_outward_actions_park(self):
        for task in (
            "İnstagramda bu şəkli paylaş",
            "Publish the article on the blog",
            "Post it to Facebook now",
            "Send email to all customers about the campaign",
            "Müştəriyə mesajı göndər",
        ):
            dec = self._dec(task)
            self.assertFalse(dec.allowed, task)
            self.assertEqual(dec.severity, "checkpoint", task)

    def test_checkpoint_is_not_a_block(self):
        dec = self._dec("Publish the article")
        self.assertEqual(dec.category, "outward_action")
        self.assertNotEqual(dec.severity, "high")


class QueueRail(_IsolatedJobsDB):
    def test_park_approve_requeues_with_flag(self):
        jid = self.queue.submit("Publish the article", source="cli")
        self.queue.park_for_approval(jid, "outward_action checkpoint")
        self.assertEqual(self.queue.get(jid).status, "awaiting_approval")

        self.assertTrue(self.queue.approve(jid))
        job = self.queue.get(jid)
        self.assertEqual(job.status, "queued")
        self.assertTrue(job.approved)

    def test_reject_closes_without_running(self):
        jid = self.queue.submit("Publish the article", source="cli")
        self.queue.park_for_approval(jid)
        self.assertTrue(self.queue.reject(jid))
        self.assertEqual(self.queue.get(jid).status, "rejected")

    def test_decide_twice_is_noop(self):
        jid = self.queue.submit("Publish the article", source="cli")
        self.queue.park_for_approval(jid)
        self.assertTrue(self.queue.approve(jid))
        self.assertFalse(self.queue.approve(jid))   # already decided
        self.assertFalse(self.queue.reject(jid))

    def test_claim_skips_parked_jobs(self):
        jid = self.queue.submit("Publish the article", source="cli")
        self.queue.park_for_approval(jid)
        self.assertIsNone(self.queue.claim_next())


class ExecutorCheckpoint(_IsolatedJobsDB):
    def _job(self, task, approved=False):
        import time
        from gateway.queue import Job
        return Job(id=1, source="cli", chat_id=None, task=task, status="running",
                   result=None, error=None, artifacts=[], created_at=time.time(),
                   started_at=None, finished_at=None, approved=approved)

    def test_unapproved_outward_job_parks(self):
        from gateway import executor
        out = executor.execute(self._job("İnstagramda bu şəkli paylaş"))
        self.assertTrue(out.get("needs_approval"))
        self.assertIn("/approve 1", out["result"])

    def test_approved_job_passes_the_checkpoint(self):
        from gateway import executor

        class _Used:
            provider, model = "test", "fake"

        with mock.patch.object(executor, "_council_should_run", return_value=False), \
             mock.patch.object(executor, "_choose_mode", return_value="plain"), \
             mock.patch.object(executor, "route", return_value="fake"), \
             mock.patch.object(executor.llm, "complete",
                               return_value=("OK icra edildi", _Used())), \
             mock.patch.object(executor.knowledge, "augment_system",
                               side_effect=lambda s, *a, **k: s):
            out = executor.execute(self._job("İnstagramda bu şəkli paylaş", approved=True))
        self.assertFalse(out.get("needs_approval", False))
        self.assertIn("OK icra edildi", out["result"])


class WorkerParksInsteadOfCompleting(_IsolatedJobsDB):
    def test_worker_parks_and_notifies(self):
        from gateway import worker
        jid = self.queue.submit("Publish the article", source="cli")
        job = self.queue.claim_next()
        self.assertEqual(job.id, jid)

        with mock.patch.object(worker, "execute",
                               return_value={"result": "⏸ approval", "artifacts": [],
                                             "needs_approval": True}), \
             mock.patch.object(worker.queue, "claim_next", return_value=job):
            self.assertTrue(worker.run_once())

        self.assertEqual(self.queue.get(jid).status, "awaiting_approval")


class BotApproveCommand(_IsolatedJobsDB):
    def _bot(self):
        from gateway import bot
        return bot

    def test_owner_approves_via_telegram(self):
        bot = self._bot()
        jid = self.queue.submit("Publish the article", source="telegram", chat_id="42")
        self.queue.park_for_approval(jid)

        sent = []
        with mock.patch.object(bot.telegram, "send_message",
                               side_effect=lambda c, t: sent.append(t)), \
             mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}):
            bot._handle_message({"chat": {"id": 42}, "text": f"/approve {jid}"})

        self.assertEqual(self.queue.get(jid).status, "queued")
        self.assertTrue(self.queue.get(jid).approved)
        self.assertTrue(any("təsdiqləndi" in t for t in sent))

    def test_non_owner_cannot_decide(self):
        bot = self._bot()
        jid = self.queue.submit("Publish the article", source="telegram", chat_id="42")
        self.queue.park_for_approval(jid)

        sent = []
        with mock.patch.object(bot.telegram, "send_message",
                               side_effect=lambda c, t: sent.append(t)), \
             mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}):
            bot._handle_message({"chat": {"id": 999}, "text": f"/approve {jid}"})

        self.assertEqual(self.queue.get(jid).status, "awaiting_approval")
        # fleet's fail-closed shell rejects non-owners with "Unauthorized"
        self.assertTrue(any("Unauthorized" in t for t in sent))


class BotPlainLanguageApproval(_IsolatedJobsDB):
    """The owner approves the way a person answers — "hə", "hə göndər", "yox" —
    not only "/approve N". Strict: owner-only, exactly one job parked, and a
    short reply that is or starts with a yes/no word. Everything else falls
    through to conversation so a casual word never fires an outward action."""

    def _send(self, bot, text, chat_id=42):
        sent = []
        with mock.patch.object(bot.telegram, "send_message",
                               side_effect=lambda c, t: sent.append(t)), \
             mock.patch.object(bot.engine_sync, "pull_if_stale"), \
             mock.patch.object(bot.mic, "speak", return_value=999), \
             mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}):
            bot._handle_message({"chat": {"id": chat_id}, "text": text})
        return sent

    def _parked(self):
        from gateway import bot
        jid = self.queue.submit("İnstagramda şəkli paylaş", source="telegram", chat_id="42")
        self.queue.park_for_approval(jid)
        return bot, jid

    def test_bare_he_approves(self):
        bot, jid = self._parked()
        self._send(bot, "hə")
        self.assertTrue(self.queue.get(jid).approved)

    def test_natural_he_gonder_approves(self):
        bot, jid = self._parked()
        self._send(bot, "hə göndər")
        self.assertTrue(self.queue.get(jid).approved)

    def test_natural_yox_rejects(self):
        bot, jid = self._parked()
        self._send(bot, "yox, lazım deyil")
        self.assertEqual(self.queue.get(jid).status, "rejected")

    def test_long_sentence_with_yes_word_falls_through(self):
        # "ok bəs sonra nə edək?" merely CONTAINS a yes word — it must NOT approve
        # a live outward action; it goes to conversation (mic.speak) instead.
        bot, jid = self._parked()
        self._send(bot, "ok bəs sonra nə edək onunla?")
        self.assertEqual(self.queue.get(jid).status, "awaiting_approval")

    def test_no_parked_job_is_just_conversation(self):
        from gateway import bot
        # "hə" with nothing parked must not error — it is a normal chat turn.
        sent = self._send(bot, "hə")
        self.assertFalse(any("icra edirəm" in t for t in sent))


class PanelApi(_IsolatedJobsDB):
    """Direct-call smoke of the control panel endpoints (no HTTP client needed)."""

    def test_submit_list_approve_roundtrip(self):
        import json
        from gateway import panel

        r = panel.submit(panel.NewTask(task="Publish the article"))
        jid = json.loads(r.body)["id"]

        self.queue.park_for_approval(jid)
        listed = json.loads(panel.jobs(status="awaiting_approval").body)
        self.assertTrue(any(x["id"] == jid for x in listed))

        self.assertTrue(json.loads(panel.approve(jid).body)["ok"])
        self.assertEqual(self.queue.get(jid).status, "queued")

    def test_health_and_pulse(self):
        import json
        from gateway import panel
        self.assertTrue(panel.health()["ok"])
        snap = json.loads(panel.pulse().body)
        self.assertIn("queue", snap)


if __name__ == "__main__":
    unittest.main()
