"""Tests for the Knowledge Core (brain).

These exercise the parts that must work with zero external services: the
markdown store, keyword recall, the pending review queue, and the index. The
LLM/embedding layers are off by default, so none of this touches the network.

    python -m unittest tests.test_brain
"""

from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from brain import retrieval as recall_mod
from brain import store


ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_DIR = ROOT_DIR / "tmp" / "brain-tests"


class BrainTestCase(unittest.TestCase):
    def setUp(self) -> None:
        TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
        self._tmp = TEST_TMP_DIR / f"brain-test-{uuid.uuid4().hex}"
        self._tmp.mkdir(parents=True, exist_ok=False)
        # Redirect the store at module level so nothing touches data/memory.
        self._orig = (store.STORE_DIR, store.PENDING_DIR, store.INDEX_FILE)
        store.STORE_DIR = self._tmp
        store.PENDING_DIR = self._tmp / "_pending"
        store.INDEX_FILE = self._tmp / "INDEX.md"

    def tearDown(self) -> None:
        store.STORE_DIR, store.PENDING_DIR, store.INDEX_FILE = self._orig
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ---- store ---------------------------------------------------------

    def test_remember_and_get_roundtrip(self):
        e = store.remember(
            "Use headless Edge for PDFs",
            "HTML rendered through headless Edge is the working PDF path.",
            type="decision",
            tags=["pdf", "Report"],
            confidence="high",
        )
        got = store.get(e.id)
        self.assertIsNotNone(got)
        self.assertEqual(got.title, "Use headless Edge for PDFs")
        self.assertEqual(got.type, "decision")
        self.assertEqual(got.confidence, "high")
        # tags are normalised to lowercase + sorted
        self.assertEqual(got.tags, ["pdf", "report"])

    def test_markdown_roundtrip_preserves_fields(self):
        e = store.Entry(
            id="x-roundtrip",
            type="lesson",
            title="A title with: a colon",
            body="Body line one.\n\nBody line two.",
            tags=["a", "b"],
            source="manual",
            confidence="low",
            related=["other-id"],
        )
        parsed = store.Entry.from_markdown(e.to_markdown(), "fallback")
        self.assertEqual(parsed.id, "x-roundtrip")
        self.assertEqual(parsed.title, "A title with: a colon")
        self.assertEqual(parsed.tags, ["a", "b"])
        self.assertEqual(parsed.related, ["other-id"])
        self.assertIn("Body line two.", parsed.body)

    def test_remember_is_idempotent_by_id(self):
        store.remember("T", "first", entry_id="fixed")
        store.remember("T2", "second", entry_id="fixed")
        self.assertEqual(len(store.all_entries()), 1)
        self.assertEqual(store.get("fixed").body, "second")

    # ---- recall --------------------------------------------------------

    def test_recall_ranks_relevant_entry_first(self):
        store.remember("KASKO campaign pricing", "How we price KASKO car insurance campaigns.", type="playbook", tags=["kasko", "pricing"])
        store.remember("Office coffee order", "Notes about the coffee machine.", type="lesson", tags=["misc"])
        store.remember("Instagram reel hooks", "Hook patterns for reels.", type="pattern", tags=["instagram"])

        hits = recall_mod.recall("how do we price a KASKO campaign", k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].entry.title, "KASKO campaign pricing")

    def test_recall_block_empty_store_returns_empty_string(self):
        self.assertEqual(recall_mod.recall_block("anything"), "")

    def test_recall_block_has_content_when_relevant(self):
        store.remember("Headless Edge PDF path", "Render HTML through headless Edge to make PDFs.", type="decision", tags=["pdf"])
        block = recall_mod.recall_block("how do I generate a pdf report")
        self.assertIn("Headless Edge PDF path", block)
        self.assertIn("Institutional knowledge", block)

    def test_recall_respects_char_budget(self):
        long_body = "word " * 1000
        store.remember("Big entry", long_body, type="lesson", tags=["pdf"])
        block = recall_mod.recall_block("big entry pdf", char_budget=300)
        self.assertLessEqual(len(block), 600)  # header + trimmed body, generous bound

    # ---- pending queue -------------------------------------------------

    def test_pending_approve_promotes_to_store(self):
        e = store.Entry(id="cand-1", type="lesson", title="Candidate", body="A suggested lesson.")
        path = store.add_pending(e)
        pend = store.list_pending()
        self.assertEqual(len(pend), 1)
        store.approve_pending(path)
        self.assertIsNotNone(store.get("cand-1"))
        self.assertEqual(len(store.list_pending()), 0)

    def test_pending_reject_discards(self):
        e = store.Entry(id="cand-2", type="lesson", title="Candidate 2", body="Another suggestion.")
        path = store.add_pending(e)
        store.reject_pending(path)
        self.assertEqual(len(store.list_pending()), 0)
        self.assertIsNone(store.get("cand-2"))

    # ---- index + stats -------------------------------------------------

    def test_index_lists_titles(self):
        store.remember("Alpha decision", "body a", type="decision")
        store.remember("Beta lesson", "body b", type="lesson")
        index_text = store.INDEX_FILE.read_text(encoding="utf-8")
        self.assertIn("Alpha decision", index_text)
        self.assertIn("Beta lesson", index_text)

    def test_stats_counts_by_type(self):
        store.remember("d1", "b", type="decision")
        store.remember("d2", "b", type="decision")
        store.remember("l1", "b", type="lesson")
        s = store.stats()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["by_type"]["decision"], 2)
        self.assertEqual(s["by_type"]["lesson"], 1)

    def test_malformed_file_does_not_break_recall(self):
        store.STORE_DIR.mkdir(parents=True, exist_ok=True)
        (store.STORE_DIR / "broken.md").write_text("not really frontmatter", encoding="utf-8")
        store.remember("Good one", "valid body about pdf", type="lesson", tags=["pdf"])
        # Should not raise, and should still find the good entry.
        hits = recall_mod.recall("pdf", k=5)
        self.assertTrue(any(h.entry.title == "Good one" for h in hits))


if __name__ == "__main__":
    unittest.main()
