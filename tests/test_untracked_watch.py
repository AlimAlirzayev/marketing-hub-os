"""The untracked-file watchdog must see corners, ping once, and never raise.

sync_engine moves committed work only; these tests pin the watchdog that makes
the leftover class visible: staleness threshold, new-path-only Telegram ping
with cooldown, state reset when the corner is cleaned, and total silence of
errors (the sweep rides the sync path and must never break it).
"""

import json
import time
import unittest
from unittest import mock

from gateway import untracked_watch as uw


class Sweep(unittest.TestCase):
    def setUp(self):
        self.state = {}
        patches = [
            mock.patch.object(uw, "_load_state", side_effect=lambda: dict(self.state)),
            mock.patch.object(uw, "_save_state", side_effect=self.state.update),
            mock.patch.object(uw.sense, "emit"),
            mock.patch.object(uw.telegram, "is_configured", return_value=True),
            mock.patch.object(uw.telegram, "send_message"),
            mock.patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": "42"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.send = uw.telegram.send_message

    def test_fresh_files_stay_quiet(self):
        with mock.patch.object(uw, "_git_untracked", return_value=["wip.md"]), \
                mock.patch.object(uw, "_age_hours", return_value=1.0):
            self.assertEqual(uw.sweep(), [])
        self.send.assert_not_called()

    def test_stale_path_pings_owner_once(self):
        with mock.patch.object(uw, "_git_untracked", return_value=["docs/lost.md"]), \
                mock.patch.object(uw, "_age_hours", return_value=72.0):
            self.assertEqual(uw.sweep(), ["docs/lost.md"])
            self.assertEqual(self.send.call_count, 1)
            self.assertIn("docs/lost.md", self.send.call_args[0][1])
            # same path again inside the cooldown -> silent
            uw.sweep()
            self.assertEqual(self.send.call_count, 1)

    def test_new_path_after_cooldown_pings_again(self):
        with mock.patch.object(uw, "_age_hours", return_value=72.0):
            with mock.patch.object(uw, "_git_untracked", return_value=["a.md"]):
                uw.sweep()
            self.state["last_notify_ts"] = time.time() - 90000  # cooldown expired
            with mock.patch.object(uw, "_git_untracked", return_value=["a.md", "b.md"]):
                uw.sweep()
        self.assertEqual(self.send.call_count, 2)

    def test_path_seen_during_cooldown_still_pings_later(self):
        # a path first seen DURING the cooldown must still ping after it expires
        with mock.patch.object(uw, "_age_hours", return_value=72.0):
            with mock.patch.object(uw, "_git_untracked", return_value=["a.md"]):
                uw.sweep()
            with mock.patch.object(uw, "_git_untracked", return_value=["a.md", "b.md"]):
                uw.sweep()  # b.md arrives inside cooldown -> silent for now
                self.assertEqual(self.send.call_count, 1)
                self.state["last_notify_ts"] = time.time() - 90000
                uw.sweep()  # cooldown over, b.md was never announced -> ping
        self.assertEqual(self.send.call_count, 2)
        self.assertIn("b.md", self.send.call_args[0][1])

    def test_clean_repo_resets_known(self):
        with mock.patch.object(uw, "_age_hours", return_value=72.0), \
                mock.patch.object(uw, "_git_untracked", return_value=["a.md"]):
            uw.sweep()
        with mock.patch.object(uw, "_git_untracked", return_value=[]):
            self.assertEqual(uw.sweep(), [])
        self.assertEqual(self.state["known"], [])
        # the path comes back after the cooldown -> pings again
        self.state["last_notify_ts"] = time.time() - 90000
        with mock.patch.object(uw, "_age_hours", return_value=72.0), \
                mock.patch.object(uw, "_git_untracked", return_value=["a.md"]):
            uw.sweep()
        self.assertEqual(self.send.call_count, 2)

    def test_git_failure_never_raises(self):
        with mock.patch.object(uw, "_git_untracked", side_effect=OSError("no git")):
            self.assertEqual(uw.sweep(), [])

    def test_notify_failure_never_raises(self):
        self.send.side_effect = RuntimeError("telegram down")
        with mock.patch.object(uw, "_git_untracked", return_value=["a.md"]), \
                mock.patch.object(uw, "_age_hours", return_value=72.0):
            self.assertEqual(uw.sweep(), ["a.md"])


if __name__ == "__main__":
    unittest.main()
