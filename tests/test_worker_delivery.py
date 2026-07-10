"""Guards for the human-facing Telegram delivery in gateway.worker.

The executor tags every stored result with a leading `_[label]_` source tag
(the panel renders it as a chip). A human in Telegram must never see that tag
raw — this is exactly the 2026-07-10 owner complaint (jobs 36-39: replies
opened with `_[chat:router:...]_`).
"""

import unittest

from gateway.worker import _split_source_tag


class SplitSourceTag(unittest.TestCase):
    def test_chat_tag_is_split_off(self):
        label, clean = _split_source_tag(
            "_[chat:router:gemini/gemini-2.5-flash]_\n\nSalam, necəsən?"
        )
        self.assertEqual(label, "chat:router:gemini/gemini-2.5-flash")
        self.assertEqual(clean, "Salam, necəsən?")

    def test_work_labels_are_split_off_too(self):
        label, clean = _split_source_tag("_[browser:gemini-2.5-pro]_\n\nHesabat hazır.")
        self.assertEqual(label, "browser:gemini-2.5-pro")
        self.assertEqual(clean, "Hesabat hazır.")

    def test_untagged_result_passes_through(self):
        label, clean = _split_source_tag("❌ **İcra xətası:** boom")
        self.assertIsNone(label)
        self.assertEqual(clean, "❌ **İcra xətası:** boom")

    def test_tag_only_matches_at_the_start(self):
        text = "Cavabın içində _[chat:x]_ görünsə, toxunulmur."
        label, clean = _split_source_tag(text)
        self.assertIsNone(label)
        self.assertEqual(clean, text)


if __name__ == "__main__":
    unittest.main()
