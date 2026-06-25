"""Unified hierarchical memory (blackboard L1–L4) — deterministic, no LLM/network.

Each test uses an isolated SQLite DB via MEM_DB_PATH so the live gateway DB is
never touched.
"""

import os
import tempfile
import unittest


class _IsolatedDB(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._saved = os.environ.get("MEM_DB_PATH")
        os.environ["MEM_DB_PATH"] = os.path.join(self._dir, "mem.db")
        # low thresholds so summary rollup triggers in a small test
        self._saved_after = os.environ.get("MEM_SUMMARIZE_AFTER")
        self._saved_turns = os.environ.get("MEM_L1_MAX_TURNS")
        os.environ["MEM_SUMMARIZE_AFTER"] = "6"
        os.environ["MEM_L1_MAX_TURNS"] = "4"
        import importlib
        import brain.blackboard as bb
        importlib.reload(bb)  # pick up the test env thresholds
        self.bb = bb

    def tearDown(self):
        for k, v in (("MEM_DB_PATH", self._saved),
                     ("MEM_SUMMARIZE_AFTER", self._saved_after),
                     ("MEM_L1_MAX_TURNS", self._saved_turns)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class L1WorkingBuffer(_IsolatedDB):
    def test_records_and_returns_recent_turns_oldest_first(self):
        bb = self.bb
        bb.observe("t1", "user", "Salam, kampaniya planı lazımdır")
        bb.observe("t1", "assistant", "Bəli, başlayaq")
        buf = bb.working_buffer("t1")
        self.assertEqual([t["role"] for t in buf], ["user", "assistant"])
        self.assertIn("kampaniya", buf[0]["content"])

    def test_thread_isolation(self):
        bb = self.bb
        bb.observe("t1", "user", "thread one")
        bb.observe("t2", "user", "thread two")
        self.assertEqual(len(bb.working_buffer("t1")), 1)
        self.assertEqual(len(bb.working_buffer("t2")), 1)
        self.assertIn("two", bb.working_buffer("t2")[0]["content"])

    def test_buffer_is_bounded_by_max_turns(self):
        bb = self.bb
        for i in range(10):
            bb.observe("t1", "user", f"mesaj {i}")
        buf = bb.working_buffer("t1")  # MEM_L1_MAX_TURNS=4
        self.assertLessEqual(len(buf), 4)
        self.assertIn("mesaj 9", buf[-1]["content"])  # newest kept


class L3Entities(_IsolatedDB):
    def test_extracts_handles_brands_money(self):
        ents = dict((e[0], e[1]) for e in self.bb.extract_entities(
            "@aytac_travels Xalq Sığorta üçün 50 AZN büdcə"))
        self.assertEqual(ents.get("@aytac_travels"), "handle")
        self.assertEqual(ents.get("xalq sığorta"), "brand")
        self.assertTrue(any(v == "money" for v in ents.values()))

    def test_entities_accumulate_mentions_per_thread(self):
        bb = self.bb
        bb.observe("t1", "user", "Xalq Sığorta kampaniyası")
        bb.observe("t1", "user", "Xalq Sığorta üçün KASKO")
        ents = {e["name"]: e for e in bb.entities_for("t1")}
        self.assertIn("xalq sığorta", ents)
        self.assertGreaterEqual(ents["xalq sığorta"]["mentions"], 2)


class L4Summary(_IsolatedDB):
    def test_summary_rolls_up_after_threshold(self):
        bb = self.bb
        for i in range(8):  # > MEM_SUMMARIZE_AFTER=6
            bb.observe("t1", "user", f"Addım {i}: planı müzakirə edirik.")
        s = bb.summary("t1")
        self.assertTrue(s)  # a summary now exists
        # buffer stays bounded even though 8 turns were observed
        self.assertLessEqual(len(bb.working_buffer("t1")), 4)


class BlackboardAssembly(_IsolatedDB):
    def test_assembles_layered_context_block(self):
        bb = self.bb
        bb.observe("t1", "user", "@aytac_travels ilə Xalq Sığorta kampaniyası")
        block = bb.assemble_context("kampaniya", "t1", include_recall=False)
        self.assertIn("Yaddaş konteksti", block)
        self.assertIn("Son danışıq (L1)", block)
        self.assertIn("Əlaqəli obyektlər (L3)", block)
        self.assertIn("@aytac_travels", block)

    def test_empty_when_no_thread_and_no_recall(self):
        block = self.bb.assemble_context("anything", None, include_recall=False)
        self.assertEqual(block, "")

    def test_observe_never_raises_on_bad_input(self):
        self.bb.observe("", "user", "no thread -> ignored")
        self.bb.observe("t1", "user", "")  # empty -> ignored
        self.assertEqual(self.bb.working_buffer("t1"), [])


class GatewayBridge(unittest.TestCase):
    def test_knowledge_bridges_are_guarded(self):
        try:
            from gateway import knowledge
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"gateway deps unavailable: {exc}")
        # None thread / empty content must be safe no-ops, never raise.
        knowledge.record_turn(None, "user", "x")
        knowledge.record_turn("t", "user", "")
        self.assertEqual(knowledge.thread_context("q", None), knowledge.recall_context("q"))


if __name__ == "__main__":
    unittest.main()
