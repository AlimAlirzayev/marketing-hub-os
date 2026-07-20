"""Service watchdog: grace period before acting, notify-once-per-incident,
circuit-broken restarts, recovery reset, and total silence of errors — the
watchdog rides the always-on supervisor and must never take it down.
"""

import unittest
from unittest import mock

from gateway import watchdog as wd


def _row(key, up, port=8800, name=None):
    return {"key": key, "name": name or key, "port": port, "up": up}


class Tick(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.local = {"ads": {"key": "ads", "_python": "py", "launch": "uvicorn",
                               "target": "app:app", "port": 8800, "cwd": "."}}
        patches = [
            mock.patch.object(wd, "_load_state", side_effect=lambda: dict(self.state)),
            mock.patch.object(wd, "_save_state", side_effect=self.state.update),
            mock.patch.object(wd, "_launch", return_value=True),
            mock.patch.object(wd, "_auto_restart", return_value=True),
            mock.patch.object(wd.sense, "emit"),
            mock.patch.object(wd.telegram, "is_configured", return_value=True),
            mock.patch.object(wd.telegram, "send_message"),
            mock.patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": "42"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.send = wd.telegram.send_message

    def test_service_up_stays_quiet(self):
        r = wd.tick(rows=[_row("ads", True)], local=self.local)
        self.assertEqual(r, {"down": [], "restarted": [], "gave_up": [], "recovered": []})
        self.send.assert_not_called()

    def test_fresh_down_needs_grace(self):
        r = wd.tick(rows=[_row("ads", False)], local=self.local, now=1000.0)
        self.assertEqual(r["down"], [])
        self.send.assert_not_called()

    def test_down_past_grace_notifies_and_restarts(self):
        wd.tick(rows=[_row("ads", False)], local=self.local, now=1000.0)
        r = wd.tick(rows=[_row("ads", False)], local=self.local, now=1010.0)
        self.assertEqual(r["down"], ["ads"])
        self.assertEqual(r["restarted"], ["ads"])
        self.assertEqual(self.send.call_count, 1)
        self.assertIn("dayanıb", self.send.call_args[0][1])

    def test_notify_fires_once_per_incident(self):
        wd.tick(rows=[_row("ads", False)], local=self.local, now=1000.0)
        wd.tick(rows=[_row("ads", False)], local=self.local, now=1010.0)
        wd.tick(rows=[_row("ads", False)], local=self.local, now=1020.0)
        self.assertEqual(self.send.call_count, 1)  # only the first "down" ping

    def test_not_local_service_ignored(self):
        r = wd.tick(rows=[_row("ga4", False, port=8850)], local=self.local,
                    now=1000.0)
        for _ in range(5):
            r = wd.tick(rows=[_row("ga4", False, port=8850)], local=self.local,
                        now=1000.0)
        self.assertEqual(r["down"], [])
        self.assertNotIn("ga4", self.state.get("services", {}))

    def test_circuit_breaker_gives_up_after_max_restarts(self):
        t = 1000.0
        seen_gave_up = []
        with mock.patch.object(wd, "_MAX_RESTARTS", 2), mock.patch.object(wd, "_GRACE_CHECKS", 1):
            for _ in range(5):
                r = wd.tick(rows=[_row("ads", False)], local=self.local, now=t)
                seen_gave_up += r["gave_up"]
                t += 10
        self.assertEqual(seen_gave_up, ["ads"])  # circuit trips exactly once
        launch_calls = wd._launch.call_count
        self.assertEqual(launch_calls, 2)  # never exceeds MAX_RESTARTS
        gave_up_pings = [c for c in self.send.call_args_list if "insan baxışı" in c[0][1]]
        self.assertEqual(len(gave_up_pings), 1)

    def test_recovery_pings_and_resets_state(self):
        wd.tick(rows=[_row("ads", False)], local=self.local, now=1000.0)
        wd.tick(rows=[_row("ads", False)], local=self.local, now=1010.0)
        self.send.reset_mock()
        r = wd.tick(rows=[_row("ads", True)], local=self.local, now=1020.0)
        self.assertEqual(r["recovered"], ["ads"])
        self.assertEqual(self.send.call_count, 1)
        self.assertIn("ayaqdadır", self.send.call_args[0][1])
        self.assertEqual(self.state["services"]["ads"]["down_count"], 0)

    def test_auto_restart_off_only_notifies(self):
        with mock.patch.object(wd, "_auto_restart", return_value=False):
            wd.tick(rows=[_row("ads", False)], local=self.local, now=1000.0)
            r = wd.tick(rows=[_row("ads", False)], local=self.local, now=1010.0)
        self.assertEqual(r["down"], ["ads"])
        self.assertEqual(r["restarted"], [])
        wd._launch.assert_not_called()
        self.assertEqual(self.send.call_count, 1)  # still told about the outage

    def test_never_raises_on_audit_failure(self):
        with mock.patch.object(wd, "_audit_rows", side_effect=RuntimeError("boom")):
            r = wd.tick(local=self.local)
        self.assertEqual(r, {"down": [], "restarted": [], "gave_up": [], "recovered": []})

    def test_never_raises_on_notify_failure(self):
        self.send.side_effect = RuntimeError("telegram down")
        wd.tick(rows=[_row("ads", False)], local=self.local, now=1000.0)
        r = wd.tick(rows=[_row("ads", False)], local=self.local, now=1010.0)
        self.assertEqual(r["down"], ["ads"])  # notify failure must not break the tick


class Defaults(unittest.TestCase):
    def test_auto_restart_on_by_default(self):
        # nothing to remember: healing a crashed local service is on unless
        # explicitly paused (WATCHDOG_AUTO_RESTART=0).
        with mock.patch.dict("os.environ", {}, clear=False):
            os_env = wd.os.environ
            os_env.pop("WATCHDOG_AUTO_RESTART", None)
            self.assertTrue(wd._auto_restart())

    def test_auto_restart_can_be_paused(self):
        with mock.patch.dict("os.environ", {"WATCHDOG_AUTO_RESTART": "0"}):
            self.assertFalse(wd._auto_restart())


class LocalKeys(unittest.TestCase):
    def test_local_keys_never_raises(self):
        with mock.patch.object(wd, "_local_services", side_effect=RuntimeError("no fs")):
            self.assertEqual(wd.local_keys(), set())


if __name__ == "__main__":
    unittest.main()
