import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "social-studio" / "google_media" / "planner.py"
SPEC = importlib.util.spec_from_file_location("google_media_planner", MODULE_PATH)
planner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(planner)


class GoogleMediaPlannerTests(unittest.TestCase):
    def campaign(self):
        return json.loads((ROOT / "social-studio" / "google_media" / "campaign.example.json").read_text(encoding="utf-8"))

    def test_example_is_valid(self):
        self.assertEqual(planner.validate_campaign(self.campaign()), [])

    def test_build_is_draft_only_and_creates_requested_handoffs(self):
        with tempfile.TemporaryDirectory() as temp:
            out = planner.build_package(self.campaign(), Path(temp) / "package")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft_only")
            self.assertTrue(manifest["human_approval_required"])
            self.assertFalse(manifest["external_calls_performed"])
            self.assertTrue((out / "canvas-operator-brief.md").exists())
            self.assertTrue((out / "handoffs" / "video.md").exists())
            self.assertTrue((out / "handoffs" / "music.md").exists())

    def test_credential_field_fails_closed(self):
        campaign = self.campaign()
        campaign["objective"]["api_key"] = "do-not-accept"
        errors = planner.validate_campaign(campaign)
        self.assertTrue(any("credential-like fields are forbidden" in item for item in errors))

    def test_private_source_url_fails_closed(self):
        campaign = self.campaign()
        campaign["evidence"]["facts"] = [{"claim":"Private claim","source_url":"https://127.0.0.1/source","status":"approved"}]
        errors = planner.validate_campaign(campaign)
        self.assertTrue(any("only public HTTPS sources" in item for item in errors))

    def test_secret_like_value_fails_without_echoing_it(self):
        campaign = self.campaign()
        secret = "AIza" + "x" * 30
        campaign["objective"]["topic"] = secret
        errors = planner.validate_campaign(campaign)
        self.assertTrue(any("secret-like content is forbidden" in item for item in errors))
        self.assertFalse(any(secret in item for item in errors))


if __name__ == "__main__":
    unittest.main()
