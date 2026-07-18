"""Tests for the autonomous lesson curator (brain/curator.py).

All LLM calls are stubbed; nothing touches the network. The safety property
under test everywhere: an item may only leave the pending queue via an
explicit KEEP/DROP verdict — LLM failure, partial replies, and dry-run all
leave the queue intact.

    python -m unittest tests.test_brain_curator
"""

from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

from brain import curator, store
from brain.store import Entry

ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_DIR = ROOT_DIR / "tmp" / "brain-tests"


def _pending_entry(n: int, *, etype: str = "lesson") -> Entry:
    return Entry(
        id=f"lesson-test-{n}",
        type=etype,
        title=f"Test lesson {n}",
        body=f"Body of test lesson {n}.",
        tags=["test"],
        source="reflect",
    )


class CuratorTestCase(unittest.TestCase):

    def setUp(self) -> None:
        TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
        self._tmp = TEST_TMP_DIR / f"brain-test-{uuid.uuid4().hex}"
        self._tmp.mkdir(parents=True, exist_ok=False)
        self._orig = (store.STORE_DIR, store.PENDING_DIR, store.INDEX_FILE)
        store.STORE_DIR = self._tmp
        store.PENDING_DIR = self._tmp / "_pending"
        store.INDEX_FILE = self._tmp / "INDEX.md"

    def tearDown(self) -> None:
        store.STORE_DIR, store.PENDING_DIR, store.INDEX_FILE = self._orig
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ---- verdict application ------------------------------------------

    def test_keep_promotes_and_drop_tombstones(self):
        store.add_pending(_pending_entry(1))
        store.add_pending(_pending_entry(2))
        reply = json.dumps(
            {"verdicts": [{"i": 1, "v": "KEEP"}, {"i": 2, "v": "DROP"}]}
        )
        with mock.patch.object(curator, "_llm_json", return_value=reply):
            s = curator.curate()

        self.assertEqual((s["kept"], s["dropped"], s["left"]), (1, 1, 0))
        self.assertEqual(len(store.list_pending()), 0)
        # kept lesson is now in the trusted store
        self.assertIsNotNone(store.get("lesson-test-1"))
        # dropped lesson left a tombstone so reflect cannot re-propose it
        tombs = {e.id for e in store.rejected_tombstones()}
        self.assertIn("lesson-test-2", tombs)
        self.assertIsNone(store.get("lesson-test-2"))

    def test_llm_unavailable_leaves_queue_untouched(self):
        store.add_pending(_pending_entry(1))
        store.add_pending(_pending_entry(2))
        with mock.patch.object(curator, "_llm_json", return_value=None):
            s = curator.curate()

        self.assertFalse(s["llm_ok"])
        self.assertEqual(s["reviewed"], 0)
        self.assertEqual(len(store.list_pending()), 2)

    def test_partial_reply_keeps_unjudged_items_pending(self):
        for n in (1, 2, 3):
            store.add_pending(_pending_entry(n))
        reply = json.dumps({"verdicts": [{"i": 2, "v": "DROP"}]})
        with mock.patch.object(curator, "_llm_json", return_value=reply):
            s = curator.curate()

        self.assertEqual((s["kept"], s["dropped"], s["left"]), (0, 1, 2))
        self.assertEqual(len(store.list_pending()), 2)

    def test_malformed_reply_is_a_noop_for_that_batch(self):
        store.add_pending(_pending_entry(1))
        with mock.patch.object(curator, "_llm_json", return_value="not json at all"):
            s = curator.curate()

        self.assertFalse(s["llm_ok"])
        self.assertEqual(len(store.list_pending()), 1)

    def test_dry_run_changes_nothing(self):
        store.add_pending(_pending_entry(1))
        reply = json.dumps({"verdicts": [{"i": 1, "v": "DROP"}]})
        with mock.patch.object(curator, "_llm_json", return_value=reply):
            s = curator.curate(dry_run=True)

        self.assertEqual(s["dropped"], 1)
        self.assertTrue(s["dry_run"])
        self.assertEqual(len(store.list_pending()), 1)
        self.assertEqual(store.rejected_tombstones(), [])

    def test_limit_caps_the_run(self):
        for n in range(5):
            store.add_pending(_pending_entry(n))
        reply = json.dumps(
            {"verdicts": [{"i": i, "v": "DROP"} for i in range(1, 3)]}
        )
        with mock.patch.object(curator, "_llm_json", return_value=reply):
            s = curator.curate(limit=2)

        self.assertEqual(s["dropped"], 2)
        self.assertEqual(s["left"], 3)
        self.assertEqual(len(store.list_pending()), 3)

    # ---- dedupe gate on KEEP -----------------------------------------

    def test_keep_of_near_duplicate_is_tombstoned_not_promoted(self):
        # An identical lesson already lives in the trusted store.
        store.remember(
            "Currency Identification",
            "Identify the currency from the query context.",
            type="lesson",
            entry_id="lesson-currency-identification",
        )
        dup = Entry(
            id="lesson-currency-identification-2",
            type="lesson",
            title="Currency Identification",
            body="Identify the currency from the query context.",
            source="reflect",
        )
        store.add_pending(dup)
        reply = json.dumps({"verdicts": [{"i": 1, "v": "KEEP"}]})
        with mock.patch.object(curator, "_llm_json", return_value=reply):
            s = curator.curate()
        # KEEP verdict, but the gate demotes it to a drop → not double-stored.
        self.assertEqual(s["kept"], 0)
        self.assertEqual(s["dropped"], 1)
        self.assertEqual(len(store.all_entries()), 1)

    def test_dedupe_store_collapses_cluster_keeps_highest_confidence(self):
        store.remember("Currency Identification", "Identify currency from context.",
                       type="lesson", confidence="low", entry_id="cur-1")
        store.remember("Currency Identification", "Identify currency from context.",
                       type="lesson", confidence="high", entry_id="cur-2")
        store.remember("Meta Connector Setup", "Wire the Meta MCP connector.",
                       type="playbook", confidence="medium", entry_id="meta-1")
        self.assertEqual(len(store.all_entries()), 3)

        s = curator.dedupe_store()
        self.assertEqual(s["removed"], 1)
        self.assertEqual(s["kept"], 2)
        # the high-confidence currency entry survived; the low one was removed
        self.assertIsNotNone(store.get("cur-2"))
        self.assertIsNone(store.get("cur-1"))
        self.assertIsNotNone(store.get("meta-1"))

    def test_dedupe_store_dry_run_changes_nothing(self):
        store.remember("Currency Identification", "Identify currency from context.",
                       type="lesson", confidence="low", entry_id="cur-1")
        store.remember("Currency Identification", "Identify currency from context.",
                       type="lesson", confidence="high", entry_id="cur-2")
        s = curator.dedupe_store(dry_run=True)
        self.assertEqual(s["removed"], 1)
        self.assertEqual(len(store.all_entries()), 2)

    # ---- digest -------------------------------------------------------

    def test_report_empty_queue_short_message(self):
        text = curator.report()
        self.assertIn("boşdur", text)

    def test_report_honest_when_llm_down(self):
        store.add_pending(_pending_entry(1))
        with mock.patch.object(curator, "_llm_json", return_value=None):
            text = curator.report()
        self.assertIn("qiymətləndirə bilmədim", text)
        self.assertEqual(len(store.list_pending()), 1)

    def test_report_lists_kept_titles(self):
        store.add_pending(_pending_entry(1))
        reply = json.dumps({"verdicts": [{"i": 1, "v": "KEEP"}]})
        with mock.patch.object(curator, "_llm_json", return_value=reply):
            text = curator.report()
        self.assertIn("Test lesson 1", text)
        self.assertIn("Qəbul: 1", text)

    # ---- executor routing ---------------------------------------------

    def test_executor_cue_routing(self):
        from gateway.executor import _is_brain_curate

        self.assertTrue(_is_brain_curate("dərs təftişi"))
        self.assertTrue(_is_brain_curate("/braincurate"))
        self.assertTrue(_is_brain_curate("Beyin təftişi zamanı"))
        # ordinary lesson chatter must NOT hit the rail
        self.assertFalse(_is_brain_curate("dərslər haqqında nə bilirsən?"))
        self.assertFalse(_is_brain_curate("bugünkü dərsi izah et"))


if __name__ == "__main__":
    unittest.main()
