"""Nervous system — event bus, the env reflex, snapshot, and council thread-memory."""

import json
import os
import tempfile
import unittest


class EventBus(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._saved = os.environ.get("SYSTEM_EVENTS_PATH")
        os.environ["SYSTEM_EVENTS_PATH"] = os.path.join(self._dir, "ev.jsonl")
        from gateway import sense
        self.sense = sense

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("SYSTEM_EVENTS_PATH", None)
        else:
            os.environ["SYSTEM_EVENTS_PATH"] = self._saved

    def test_emit_then_recent_roundtrip_and_filter(self):
        self.sense.emit("job", "#1 done")
        self.sense.emit("schedule", "due -> #2")
        self.sense.emit("job", "#3 done")
        self.assertEqual(len(self.sense.recent()), 3)
        jobs = self.sense.recent(kind="job")
        self.assertEqual([e["summary"] for e in jobs], ["#1 done", "#3 done"])

    def test_emit_redacts_secrets(self):
        self.sense.emit("credential", "got token api_key=supersecretvalue123 ok", {"k": "Bearer abcdef123456"})
        rec = self.sense.recent()[-1]
        blob = json.dumps(rec)
        self.assertNotIn("supersecretvalue123", blob)
        self.assertIn("REDACTED", blob)

    def test_emit_never_raises_on_bad_path(self):
        os.environ["SYSTEM_EVENTS_PATH"] = self._dir  # a directory -> open() fails
        try:
            self.sense.emit("x", "y")  # must swallow the error, not raise
        finally:
            os.environ["SYSTEM_EVENTS_PATH"] = os.path.join(self._dir, "ev.jsonl")


class EnvReflex(unittest.TestCase):
    """The exact fix for the 'is the token set?' stale-memory mistake."""

    def setUp(self):
        from gateway import sense
        self.sense = sense
        self._dir = tempfile.mkdtemp()
        self._envp = os.path.join(self._dir, ".env")
        with open(self._envp, "w", encoding="utf-8") as f:
            f.write("# comment\nTELEGRAM_BOT_TOKEN=12345:ABCDEF_realtokenvalue_rVdU\n")
            f.write("RAPIDAPI_KEY=\n")  # present but empty

    def test_reads_reality_not_memory(self):
        st = self.sense.env_status(
            keys=("TELEGRAM_BOT_TOKEN", "RAPIDAPI_KEY", "NEVER_SET_KEY"),
            env_path=self._envp,
        )
        self.assertTrue(st["TELEGRAM_BOT_TOKEN"].startswith("SET"))
        self.assertTrue(st["TELEGRAM_BOT_TOKEN"].endswith("rVdU)"))  # masked tail only
        self.assertEqual(st["RAPIDAPI_KEY"], "EMPTY")
        self.assertEqual(st["NEVER_SET_KEY"], "MISSING")

    def test_status_value_is_masked_not_the_secret(self):
        st = self.sense.env_status(keys=("TELEGRAM_BOT_TOKEN",), env_path=self._envp)
        self.assertNotIn("realtokenvalue", st["TELEGRAM_BOT_TOKEN"])


class Snapshot(unittest.TestCase):
    def test_snapshot_has_all_organs_and_never_raises(self):
        from gateway import sense
        snap = sense.snapshot()
        for organ in ("env", "queue", "memory", "schedules", "git", "recent_events"):
            self.assertIn(organ, snap)
        self.assertIsInstance(sense.pulse(), str)


class CouncilThreadMemory(unittest.TestCase):
    """recall_context must reflect the active thread (so the council path, which
    calls recall_context, gets hierarchical thread memory without editing council.py)."""

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._saved = os.environ.get("MEM_DB_PATH")
        os.environ["MEM_DB_PATH"] = os.path.join(self._dir, "mem.db")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("MEM_DB_PATH", None)
        else:
            os.environ["MEM_DB_PATH"] = self._saved

    def test_recall_context_follows_current_thread(self):
        try:
            from gateway import knowledge
            import brain.blackboard as bb
            import importlib
            importlib.reload(bb)
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"deps unavailable: {exc}")

        bb.observe("chat-42", "user", "@xalq_sigorta KASKO kampaniyası planı")
        try:
            knowledge.set_current_thread("chat-42")
            ctx = knowledge.recall_context("kampaniya")
        finally:
            knowledge.set_current_thread(None)
        self.assertIn("Yaddaş konteksti", ctx)
        self.assertIn("@xalq_sigorta", ctx)
        # with no active thread, it must NOT carry the thread's L1/L3 block
        self.assertNotIn("Son danışıq (L1)", knowledge.recall_context("kampaniya"))


if __name__ == "__main__":
    unittest.main()
