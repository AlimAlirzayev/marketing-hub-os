"""The visual front office: deliverables gallery + the sandboxed file server.

The security-critical part is _safe_resolve — it must serve deliverables from the
output roots and NEVER .env, source, or anything reached by path traversal.
"""

import json
import unittest
from pathlib import Path

from gateway import panel


class FileServerSandbox(unittest.TestCase):
    def test_serves_a_real_output_file(self):
        # any existing deliverable under output/ resolves
        out = panel.ROOT / "output"
        sample = next((p for p in out.rglob("*") if p.is_file()), None)
        if sample is None:
            self.skipTest("no output files to serve")
        rel = sample.relative_to(panel.ROOT).as_posix()
        self.assertIsNotNone(panel._safe_resolve(rel))

    def test_never_serves_dotenv(self):
        self.assertIsNone(panel._safe_resolve(".env"))
        self.assertIsNone(panel._safe_resolve("gateway/bot.py"))
        self.assertIsNone(panel._safe_resolve("services.json"))

    def test_blocks_path_traversal(self):
        for evil in ("output/../.env", "output/../../.env",
                     "output/../gateway/keyvault.py", "../.env",
                     "workspace/../../.ssh/id_ed25519"):
            self.assertIsNone(panel._safe_resolve(evil), evil)

    def test_absolute_path_outside_roots_rejected(self):
        self.assertIsNone(panel._safe_resolve(str(panel.ROOT / ".env")))

    def test_serve_endpoint_404s_on_disallowed(self):
        resp = panel.serve_file(".env")
        self.assertEqual(resp.status_code, 404)


class SiteGrouping(unittest.TestCase):
    """A directory with index.html is ONE site tile; its inner files fold in."""

    def setUp(self):
        import shutil
        self.dir = panel.ROOT / "workspace" / "_t_site_group_test"
        (self.dir / "css").mkdir(parents=True, exist_ok=True)
        (self.dir / "index.html").write_text("<html><body>test site</body></html>", encoding="utf-8")
        (self.dir / "css" / "style.css").write_text("body{}", encoding="utf-8")
        (self.dir / "logo.png").write_bytes(b"\x89PNG_fake")
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))

    def test_folder_site_is_one_tile(self):
        data = json.loads(panel.deliverables(limit=200).body)
        mine = [d for d in data if "_t_site_group_test" in d["path"]]
        self.assertEqual(len(mine), 1, mine)          # ONE tile, not three
        tile = mine[0]
        self.assertEqual(tile["kind"], "site")
        self.assertEqual(tile["name"], "_t_site_group_test")   # named by the site dir
        self.assertTrue(tile["url"].endswith("/index.html"))

    def test_site_assets_still_served_for_the_iframe(self):
        rel = (self.dir / "css" / "style.css").relative_to(panel.ROOT).as_posix()
        self.assertIsNotNone(panel._safe_resolve(rel))  # relative asset resolves


class ChatApi(unittest.TestCase):
    def test_history_reads_the_one_mic_thread(self):
        from unittest import mock
        turns = [{"role": "user", "content": "[telegram] salam"},
                 {"role": "assistant", "content": "salam!"}]
        with mock.patch("brain.blackboard.init"), \
             mock.patch("brain.blackboard.working_buffer", return_value=turns) as wb:
            data = json.loads(panel.chat_history(n=40).body)
        wb.assert_called_once()
        self.assertEqual(wb.call_args.args[0], "main")   # the ONE mic thread
        self.assertEqual(data["turns"], turns)

    def test_history_never_raises_without_brain(self):
        from unittest import mock
        with mock.patch("brain.blackboard.init", side_effect=RuntimeError("no db")):
            data = json.loads(panel.chat_history().body)
        self.assertEqual(data["turns"], [])


class DeliverablesApi(unittest.TestCase):
    def test_classifies_and_orders(self):
        data = json.loads(panel.deliverables(limit=60).body)
        self.assertIsInstance(data, list)
        kinds = {"site", "image", "report", "video", "audio", "pdf", "bundle", "file"}
        for d in data:
            self.assertIn(d["kind"], kinds)
            self.assertTrue(d["url"].startswith("/file/"))
            self.assertNotIn("..", d["path"])
        # newest first
        mtimes = [d["mtime"] for d in data]
        self.assertEqual(mtimes, sorted(mtimes, reverse=True))

    def test_kind_mapping(self):
        self.assertEqual(panel._kind_of(".html"), "site")
        self.assertEqual(panel._kind_of(".png"), "image")
        self.assertEqual(panel._kind_of(".md"), "report")
        self.assertEqual(panel._kind_of(".mp4"), "video")
        self.assertEqual(panel._kind_of(".zip"), "bundle")
        self.assertEqual(panel._kind_of(".xyz"), "file")


if __name__ == "__main__":
    unittest.main()
