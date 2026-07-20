"""Guards for publisher.privacy_guard — the child/family/real-person publish gate
(lab prototype 'publisher-privacy-guard', score 10). All offline, no network."""

import json
import tempfile
import unittest
from pathlib import Path

from publisher import privacy_guard as pg


def _plan(slug="autumn-launch", caption="Yeni kampaniya başladı", media=None, entries=None):
    e = entries if entries is not None else [{"platform": "instagram", "caption": caption, "media": media}]
    return {"asset": slug, "slug": slug, "media": media, "kind": "video",
            "type": "now", "entries": e}


class Scan(unittest.TestCase):
    def test_clean_plan_not_flagged(self):
        self.assertFalse(pg.scan_plan(_plan())["flagged"])

    def test_az_word_flags(self):
        s = pg.scan_plan(_plan(caption="Bizim balaca uşaq üçün sığorta"))
        self.assertTrue(s["flagged"])
        self.assertIn("uşaq", s["words"])

    def test_az_inflection_flags(self):
        # uşağın (genitive) must still fire via the uşağ stem
        self.assertTrue(pg.scan_plan(_plan(caption="uşağın gələcəyi"))["flagged"])

    def test_en_word_flags(self):
        self.assertTrue(pg.scan_plan(_plan(caption="A happy family testimonial"))["flagged"])

    def test_slug_flags(self):
        self.assertTrue(pg.scan_plan(_plan(slug="family-day-2026", caption="clean"))["flagged"])

    def test_media_filename_flags(self):
        self.assertTrue(pg.scan_plan(_plan(caption="clean", media="/x/baby-ad.mp4"))["flagged"])

    def test_word_boundary_no_false_positive(self):
        # "kidney" / "familiar" / "minority" must NOT trip kid / family / minor
        self.assertFalse(pg.scan_plan(_plan(caption="kidney health seminar for a familiar minority"))["flagged"])

    def test_ugc_strict_boundary(self):
        self.assertTrue(pg.scan_plan(_plan(caption="fresh ugc drop"))["flagged"])


class Sidecar(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.media = self.dir / "clip.mp4"
        self.media.write_bytes(b"x")

    def _sidecar(self, data):
        (self.dir / "privacy.json").write_text(json.dumps(data), encoding="utf-8")

    def test_minors_true_flags_even_with_clean_text(self):
        self._sidecar({"minors": True})
        s = pg.scan_plan(_plan(caption="totally clean words", media=str(self.media)))
        self.assertTrue(s["flagged"])
        self.assertTrue(any("minor" in r for r in s["reasons"]))

    def test_people_without_consent_flags(self):
        self._sidecar({"people": ["Real Name"], "consent": False})
        self.assertTrue(pg.scan_plan(_plan(caption="clean", media=str(self.media)))["flagged"])

    def test_people_with_consent_ok(self):
        self._sidecar({"people": ["Real Name"], "consent": True})
        self.assertFalse(pg.scan_plan(_plan(caption="clean", media=str(self.media)))["flagged"])

    def test_unreadable_sidecar_fails_safe(self):
        (self.dir / "privacy.json").write_text("{not json", encoding="utf-8")
        self.assertTrue(pg.scan_plan(_plan(caption="clean", media=str(self.media)))["flagged"])


class Enforce(unittest.TestCase):
    def setUp(self):
        self._orig = pg.REPO
        pg.REPO = Path(tempfile.mkdtemp())

    def tearDown(self):
        pg.REPO = self._orig

    def test_clean_allowed_no_checklist(self):
        allowed, scan, checklist = pg.enforce(_plan(), ack=False, dry_run=False)
        self.assertTrue(allowed)
        self.assertIsNone(checklist)

    def test_flagged_live_blocked_and_checklist_written(self):
        allowed, scan, checklist = pg.enforce(_plan(caption="uşaq sığortası"), ack=False, dry_run=False)
        self.assertFalse(allowed)
        self.assertTrue(checklist.exists())
        body = checklist.read_text(encoding="utf-8")
        self.assertIn("consent", body.lower())
        self.assertIn("--privacy-ack", body)

    def test_flagged_with_ack_allowed(self):
        allowed, *_ = pg.enforce(_plan(caption="uşaq"), ack=True, dry_run=False)
        self.assertTrue(allowed)

    def test_flagged_dry_run_allowed_but_surfaced(self):
        allowed, scan, checklist = pg.enforce(_plan(caption="family day"), ack=False, dry_run=True)
        self.assertTrue(allowed)          # no network on dry-run
        self.assertTrue(scan["flagged"])  # but still surfaced
        self.assertTrue(checklist.exists())

    def test_scan_error_fails_safe(self):
        allowed, scan, _ = pg.enforce({"entries": 123}, ack=False, dry_run=False)  # entries not iterable of dicts
        self.assertFalse(allowed)
        self.assertTrue(scan["flagged"])

    def test_minor_edit_predicate(self):
        self.assertFalse(pg.minor_edit_allowed(_plan(caption="uşaq"), ack=False))
        self.assertTrue(pg.minor_edit_allowed(_plan(caption="uşaq"), ack=True))
        self.assertTrue(pg.minor_edit_allowed(_plan(caption="clean"), ack=False))


if __name__ == "__main__":
    unittest.main()
