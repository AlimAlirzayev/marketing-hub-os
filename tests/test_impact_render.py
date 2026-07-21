"""Impact Ledger report-grade render: the pure HTML must show real values, source
badges, and delta direction — and NEVER a fabricated value for a down source.
"""

import unittest

from gateway import impact_render as ir


def _scorecard(**over):
    sc = {
        "month": "2026-06",
        "results": {
            "leads": {"value": 412, "prev": 330, "delta_pct": 24.8, "source": "CANLI"},
            "cpa": {"value": 3.15, "prev": 4.02, "delta_pct": -21.6,
                    "lower_is_better": True, "source": "CANLI"},
            "conversions": {"value": None, "source": "ƏLÇATMAZ"},
            "sla": {"value": 92.4, "signals": 57, "source": "DEMO"},
        },
        "work": {"deliverables": 38, "requests_answered": 41,
                 "by_category": {"content": 14, "report": 9, "other": 0},
                 "hours_saved_est": 28.5},
        "sources": {"ads": "CANLI", "ga4": "ƏLÇATMAZ", "cx": "DEMO"},
        "headline": "412 müraciət · CPA yaxşılaşdı — bir adam, bir komandanın işi.",
    }
    sc.update(over)
    return sc


class RenderHtml(unittest.TestCase):
    def test_is_self_contained_document(self):
        h = ir.render_html(_scorecard())
        self.assertIn("<!DOCTYPE html>", h)
        self.assertIn("<style>", h)          # inline CSS, no external deps
        self.assertNotIn("http://", h.split("<style>")[0] if "<style>" in h else h)

    def test_shows_real_values_and_headline(self):
        h = ir.render_html(_scorecard())
        self.assertIn("412", h)
        self.assertIn("3.15", h)
        self.assertIn("92.4%", h)
        self.assertIn("komandanın işi", h)

    def test_down_source_renders_dash_not_a_number(self):
        h = ir.render_html(_scorecard())
        # the conversions card is ƏLÇATMAZ → shows an em dash, never "None"
        self.assertIn("ƏLÇATMAZ", h)
        self.assertNotIn("None", h)

    def test_source_and_delta_badges_present(self):
        h = ir.render_html(_scorecard())
        self.assertIn("CANLI", h)
        self.assertIn("DEMO", h)
        self.assertIn("badge live", h)
        self.assertIn("↑", h)   # leads up
        self.assertIn("↓", h)   # cpa down (improvement)

    def test_delta_never_colour_only(self):
        # a good delta carries a ✓ glyph, not just a colour class
        h = ir.render_html(_scorecard())
        self.assertIn("✓", h)

    def test_no_leftover_template_artifacts(self):
        h = ir.render_html(_scorecard())
        for junk in ("written", "{{", "}}", "None"):
            self.assertNotIn(junk, h)

    def test_empty_measures_do_not_crash(self):
        sc = _scorecard(results={
            "leads": {"value": None, "source": "ƏLÇATMAZ"},
            "cpa": {"value": None, "source": "ƏLÇATMAZ"},
            "conversions": {"value": None, "source": "ƏLÇATMAZ"},
            "sla": {"value": None, "source": "ƏLÇATMAZ"},
        }, sources={"ads": "ƏLÇATMAZ", "ga4": "ƏLÇATMAZ", "cx": "ƏLÇATMAZ"})
        h = ir.render_html(sc)
        self.assertIn("<!DOCTYPE html>", h)
        self.assertNotIn("None", h)


if __name__ == "__main__":
    unittest.main()
