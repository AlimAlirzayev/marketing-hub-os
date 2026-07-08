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
