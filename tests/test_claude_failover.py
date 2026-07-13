"""Guards for two-account Claude failover (gateway.claude_bridge).

The operator runs two Claude subscriptions to survive the 5-hour cap; when one
is capped the bridge must rest it and switch to the other, then stick with
whichever works. _run_once (the actual `claude -p` call) is stubbed.
"""

import json
import time
import unittest
from unittest.mock import patch

from gateway import claude_bridge as cb


class Failover(unittest.TestCase):
    def setUp(self):
        self._orig = cb._ACCOUNTS_FILE
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        cb._ACCOUNTS_FILE = pathlib.Path(self.tmp) / "acc.json"
        cb._ACCOUNTS_FILE.write_text(json.dumps({"active": 0, "accounts": [
            {"name": "A", "token": "tok-A", "cooldown_until": 0},
            {"name": "B", "token": "tok-B", "cooldown_until": 0},
        ]}))

    def tearDown(self):
        cb._ACCOUNTS_FILE = self._orig

    def test_capped_account_fails_over_to_second(self):
        seen = []

        def fake(prompt, thread, cwd, timeout, token):
            seen.append(token)
            if token == "tok-A":
                raise RuntimeError("Claude AI usage limit reached")
            return "cavab B", {"session_id": "s"}

        with patch.object(cb, "_run_once", fake):
            text, meta = cb.ask("salam")

        self.assertEqual(text, "cavab B")
        self.assertEqual(meta["account"], "B")
        self.assertEqual(seen, ["tok-A", "tok-B"])  # tried A, failed over to B
        # A is now resting; active persisted to B
        data = json.loads(cb._ACCOUNTS_FILE.read_text())
        self.assertEqual(data["active"], 1)
        self.assertGreater(data["accounts"][0]["cooldown_until"], time.time())

    def test_resting_account_is_skipped(self):
        data = json.loads(cb._ACCOUNTS_FILE.read_text())
        data["accounts"][0]["cooldown_until"] = time.time() + 9999  # A resting
        cb._ACCOUNTS_FILE.write_text(json.dumps(data))
        seen = []

        def fake(prompt, thread, cwd, timeout, token):
            seen.append(token)
            return "ok", {}

        with patch.object(cb, "_run_once", fake):
            cb.ask("salam")
        self.assertEqual(seen, ["tok-B"])  # A skipped entirely

    def test_non_limit_error_does_not_burn_second_account(self):
        seen = []

        def fake(prompt, thread, cwd, timeout, token):
            seen.append(token)
            raise RuntimeError("network boom")

        with patch.object(cb, "_run_once", fake):
            with self.assertRaises(RuntimeError):
                cb.ask("salam")
        self.assertEqual(seen, ["tok-A"])  # stopped — didn't waste account B

    def test_status_never_leaks_token(self):
        st = cb.account_status()
        self.assertEqual({s["name"] for s in st}, {"A", "B"})
        self.assertNotIn("token", json.dumps(st))


if __name__ == "__main__":
    unittest.main()
