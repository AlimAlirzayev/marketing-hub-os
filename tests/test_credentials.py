"""Governed credential-acquisition capability — security + adapter + dispatch.

No browser, no network: doit is monkeypatched. Proves the prime-directive
guarantees (allowlist, default-off checkpoint, raw key never returned).
"""

import os
import tempfile
import unittest

from gateway import security
from gateway.tools import credentials

_FLAG = "GATEWAY_ALLOW_CREDENTIALS"
_EVENTS = "SYSTEM_EVENTS_PATH"
_RAW_KEY = "deadbeef12mshSEKRET0000jsnDEADBEEF99"  # must NEVER appear in any output


class _EnvGuard(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get(_FLAG)
        os.environ.pop(_FLAG, None)
        # Isolate the nervous-system event log: a successful acquire emits a
        # "credential" event, and it must NOT pollute the real system_events.jsonl
        # (that leak is exactly what creates false "X acquired" contradictions).
        self._saved_events = os.environ.get(_EVENTS)
        self._evt_dir = tempfile.mkdtemp(prefix="cred_evt_")
        os.environ[_EVENTS] = os.path.join(self._evt_dir, "events.jsonl")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._saved
        if self._saved_events is None:
            os.environ.pop(_EVENTS, None)
        else:
            os.environ[_EVENTS] = self._saved_events


class CredentialSecurityGate(_EnvGuard):
    def test_unknown_provider_is_blocked(self):
        d = security.evaluate_credential_acquisition("facebook")
        self.assertFalse(d.allowed)
        self.assertEqual(d.category, "unknown_credential_provider")

    def test_allowlisted_provider_defaults_to_checkpoint(self):
        d = security.evaluate_credential_acquisition("rapidapi")
        self.assertFalse(d.allowed)
        self.assertEqual(d.category, "credential_checkpoint")
        self.assertEqual(d.severity, "checkpoint")  # not a hard block

    def test_operator_approval_allows(self):
        os.environ[_FLAG] = "1"
        d = security.evaluate_credential_acquisition("rapidapi")
        self.assertTrue(d.allowed)
        self.assertEqual(d.category, "credential_acquisition")


class CredentialAdapter(_EnvGuard):
    def test_unknown_provider_returns_block_message(self):
        msg = credentials.acquire("twitter")
        self.assertIn("Security Guard blocked", msg)

    def test_default_is_checkpoint_and_never_launches_doit(self):
        import doit
        original = doit.acquire
        doit.acquire = lambda *a, **k: self.fail("doit must not run without approval")
        try:
            msg = credentials.acquire("rapidapi")  # flag off, approved=None
        finally:
            doit.acquire = original
        self.assertIn("Checkpoint", msg)
        self.assertIn("GATEWAY_ALLOW_CREDENTIALS", msg)

    def test_approved_path_masks_key_and_never_exposes_raw(self):
        import doit
        original = doit.acquire

        def fake_acquire(provider, headless=False):
            # doit returns ONLY a masked preview, never the raw key.
            return {"ok": True, "env_var": "RAPIDAPI_KEY", "action": "updated",
                    "key_preview": "deadbe…EF99", "browser": "chrome"}

        doit.acquire = fake_acquire
        try:
            msg = credentials.acquire("rapidapi", approved=True)
        finally:
            doit.acquire = original
        self.assertIn("RAPIDAPI_KEY", msg)
        self.assertIn("deadbe…EF99", msg)
        self.assertNotIn(_RAW_KEY, msg)  # raw key must never surface

    def test_failure_is_redacted(self):
        import doit
        original = doit.acquire
        doit.acquire = lambda *a, **k: {"ok": False, "error": f"api_key={_RAW_KEY} rejected"}
        try:
            msg = credentials.acquire("rapidapi", approved=True)
        finally:
            doit.acquire = original
        self.assertNotIn(_RAW_KEY, msg)  # redact() scrubs the leaked secret


class ExecutorDispatch(unittest.TestCase):
    def _executor(self):
        try:
            from gateway import executor
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"executor deps unavailable: {exc}")
        return executor

    def test_detects_credential_intent(self):
        ex = self._executor()
        self.assertEqual(ex._credential_provider("doit rapidapi"), "rapidapi")
        self.assertEqual(ex._credential_provider("rapidapi açarını gətir"), "rapidapi")
        self.assertEqual(ex._credential_provider("get rapidapi api key please"), "rapidapi")

    def test_ignores_normal_and_unlisted(self):
        ex = self._executor()
        self.assertIsNone(ex._credential_provider("research rapidapi pricing trends"))
        self.assertIsNone(ex._credential_provider("write 3 instagram posts"))
        self.assertIsNone(ex._credential_provider("acquire a facebook api key"))  # not allowlisted


if __name__ == "__main__":
    unittest.main()
