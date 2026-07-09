"""The canonical engine refresh (gateway.engine_sync): every entry point pulls-first
through one brain — announce real updates only, debounce bursty callers."""

import os
import unittest
from unittest import mock


class AnnounceLogic(unittest.TestCase):
    def test_no_announce_when_up_to_date(self):
        from gateway import engine_sync
        with mock.patch.object(engine_sync.telegram, "send_message") as sm:
            self.assertFalse(
                engine_sync.announce_update("[sync] engine up to date (HEAD abc1234)")
            )
            sm.assert_not_called()

    def test_announces_to_owner_on_real_update_with_tripwire(self):
        from gateway import engine_sync
        sent = []
        with mock.patch.object(engine_sync.telegram, "send_message",
                               side_effect=lambda c, t: sent.append((c, t))), \
             mock.patch.object(engine_sync.telegram, "is_configured", return_value=True), \
             mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}):
            self.assertTrue(
                engine_sync.announce_update(
                    "[sync] pulled new engine updates -> abc1234",
                    "✅ testlər yaşıl (5/5 keçdi)",
                )
            )
        self.assertEqual(sent[0][0], "42")
        self.assertIn("yeniliklər", sent[0][1])
        self.assertIn("testlər yaşıl", sent[0][1])  # tripwire verdict folded in

    def test_update_without_owner_never_sends(self):
        from gateway import engine_sync
        with mock.patch.object(engine_sync.telegram, "send_message") as sm, \
             mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": ""}):
            self.assertTrue(
                engine_sync.announce_update("[sync] pulled new engine updates -> abc1234")
            )
            sm.assert_not_called()

    def test_run_brain_returns_summary(self):
        from gateway import engine_sync
        fake = mock.Mock(stdout="[sync] engine up to date (HEAD abc1234)", stderr="")
        with mock.patch.object(engine_sync.subprocess, "run", return_value=fake):
            self.assertIn("up to date", engine_sync._run_brain(True, True))


class DebounceLogic(unittest.TestCase):
    def test_pull_if_stale_skips_when_fresh(self):
        from gateway import engine_sync
        with mock.patch.object(engine_sync, "seconds_since_sync", return_value=5.0), \
             mock.patch.object(engine_sync, "refresh") as rf:
            self.assertIsNone(engine_sync.pull_if_stale(max_age_s=90))
            rf.assert_not_called()

    def test_pull_if_stale_pulls_when_stale(self):
        from gateway import engine_sync
        with mock.patch.object(engine_sync, "seconds_since_sync", return_value=999.0), \
             mock.patch.object(engine_sync, "refresh",
                               return_value="[sync] engine up to date") as rf:
            self.assertEqual(engine_sync.pull_if_stale(max_age_s=90),
                             "[sync] engine up to date")
            rf.assert_called_once()


if __name__ == "__main__":
    unittest.main()
