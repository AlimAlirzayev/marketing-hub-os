"""A conversation is not a deliverable.

Every job's text used to be filed as output/jobs/job-N.md, so the front office
gallery listed dozens of chat turns ("salam, necəsən?") as "nəticələr". These
tests lock the separation in: chat/router/security/credential replies go to
output/replies (which the gallery does not scan); real work products stay.
"""

import unittest
from pathlib import Path
from unittest import mock

from gateway import executor, panel


class ArtifactRouting(unittest.TestCase):
    def test_reply_goes_to_replies_dir(self):
        with mock.patch.object(Path, "write_text"), mock.patch.object(Path, "mkdir"):
            p = executor._save_artifact(1, "salam", reply=True)
        self.assertIn("output/replies/", p.replace("\\", "/"))

    def test_work_product_goes_to_jobs_dir(self):
        with mock.patch.object(Path, "write_text"), mock.patch.object(Path, "mkdir"):
            p = executor._save_artifact(1, "## AI Council neticesi", reply=False)
        self.assertIn("output/jobs/", p.replace("\\", "/"))

    def test_the_two_dirs_are_not_the_same(self):
        self.assertNotEqual(executor._OUTPUT_DIR, executor._REPLIES_DIR)


class GalleryExcludesReplies(unittest.TestCase):
    def test_replies_dir_is_excluded_from_the_gallery(self):
        self.assertIn(panel.ROOT / "output" / "replies", panel._NOT_DELIVERABLE)

    def test_a_reply_file_never_appears_as_a_deliverable(self):
        replies = panel.ROOT / "output" / "replies"
        replies.mkdir(parents=True, exist_ok=True)
        probe = replies / "_t_reply_probe.md"
        probe.write_text("salam, necəsən?", encoding="utf-8")
        try:
            data = panel.deliverables(limit=200).body.decode()
            self.assertNotIn("_t_reply_probe", data)
        finally:
            probe.unlink(missing_ok=True)

    def test_reply_files_are_still_servable_by_path(self):
        # The gallery hides them; a job's artifact link must still resolve.
        replies = panel.ROOT / "output" / "replies"
        replies.mkdir(parents=True, exist_ok=True)
        probe = replies / "_t_reply_serve.md"
        probe.write_text("hi", encoding="utf-8")
        try:
            self.assertIsNotNone(panel._safe_resolve("output/replies/_t_reply_serve.md"))
        finally:
            probe.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
