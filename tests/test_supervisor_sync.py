"""The always-on host's self-sync: pull periodically, announce real updates only."""

import os
import unittest
from unittest import mock


class AnnounceLogic(unittest.TestCase):
    def test_no_announce_when_up_to_date(self):
        from gateway import supervisor
        with mock.patch.object(supervisor.telegram, "send_message") as sm:
            self.assertFalse(
                supervisor._announce_if_updated("[sync] engine up to date (HEAD abc1234)")
            )
            sm.assert_not_called()

    def test_announces_to_owner_on_real_update(self):
        from gateway import supervisor
        sent = []
        with mock.patch.object(supervisor.telegram, "send_message",
                               side_effect=lambda c, t: sent.append((c, t))), \
             mock.patch.object(supervisor.telegram, "is_configured", return_value=True), \
             mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}):
            self.assertTrue(
                supervisor._announce_if_updated("[sync] pulled new engine updates -> abc1234")
            )
        self.assertEqual(sent[0][0], "42")
        self.assertIn("yeniliklər", sent[0][1])

    def test_update_without_owner_never_sends(self):
        from gateway import supervisor
        with mock.patch.object(supervisor.telegram, "send_message") as sm, \
             mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": ""}):
            self.assertTrue(
                supervisor._announce_if_updated("[sync] pulled new engine updates -> abc1234")
            )
            sm.assert_not_called()

    def test_sync_once_returns_brain_summary(self):
        from gateway import supervisor
        fake = mock.Mock(stdout="[sync] engine up to date (HEAD abc1234)", stderr="")
        with mock.patch.object(supervisor.subprocess, "run", return_value=fake):
            self.assertIn("up to date", supervisor._sync_once())


if __name__ == "__main__":
    unittest.main()
