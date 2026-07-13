"""Guards for the Hermes-style learning loop (gateway.skills)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway import skills


class LearnGate(unittest.TestCase):
    def setUp(self):
        self._orig = skills._DIR
        skills._DIR = Path(tempfile.mkdtemp()) / "skills"

    def tearDown(self):
        skills._DIR = self._orig

    def _card(self, *a, **k):
        return {"title": "Build a landing page",
                "triggers": ["landing", "sayt", "html"],
                "steps": ["Author DESIGN.md first", "Build to the palette",
                          "Run it and check output"]}

    def test_learns_from_successful_work_job(self):
        with patch.object(skills, "_distill", self._card):
            slug = skills.learn_from_job(
                "bizim üçün yeni landing sayt qur zəhmət olmasa",
                "_[agentic-tools:gemini]_\n\nSayt hazırdır.")
        self.assertEqual(slug, "build-a-landing-page")
        self.assertTrue((skills._DIR / "build-a-landing-page.md").exists())

    def test_ignores_chat_turns(self):
        with patch.object(skills, "_distill", self._card):
            self.assertIsNone(skills.learn_from_job(
                "salam necəsən dostum", "_[chat:router:groq]_\n\nYaxşıyam."))

    def test_ignores_failures(self):
        with patch.object(skills, "_distill", self._card):
            self.assertIsNone(skills.learn_from_job(
                "bizim üçün yeni sayt qur", "_[agentic-tools:x]_\n\n❌ İcra xətası: boom"))

    def test_relevant_matches_by_trigger_overlap(self):
        with patch.object(skills, "_distill", self._card):
            skills.learn_from_job("bizim üçün yeni landing sayt qur indi",
                                  "_[agentic-tools:x]_\n\nok")
        hit = skills.relevant("mənə bir landing sayt lazımdır")
        self.assertIn("Build a landing page", hit)
        self.assertIn("DESIGN.md", hit)

    def test_relevant_empty_when_no_match(self):
        self.assertEqual(skills.relevant("tamam fərqli mövzu haqqında"), "")


if __name__ == "__main__":
    unittest.main()
