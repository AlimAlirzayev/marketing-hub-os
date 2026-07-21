"""Impact Ledger scoring — the pure heart must be correct and honest offline.

Pins: task→category classification, hours-saved estimate, source labels
(CANLI/DEMO/ƏLÇATMAZ), CPA/lead deltas, and the no-fabrication contract (a down
source is labelled, never invented with a number).
"""

import unittest

from gateway import impact_ledger as il


class Classify(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(il.classify_task("3 instagram post yaz"), "content")
        self.assertEqual(il.classify_task("iyul hesabatı hazırla"), "report")
        self.assertEqual(il.classify_task("rəqib radar skan"), "research")
        self.assertEqual(il.classify_task("saytın SEO auditi"), "seo")
        self.assertEqual(il.classify_task("KASKO kampaniya planı"), "campaign")
        self.assertEqual(il.classify_task("random zad"), "other")

    def test_priority_seo_before_content(self):
        # "SEO üçün məzmun/post" -> seo wins (checked first), not content
        self.assertEqual(il.classify_task("SEO üçün post mətni"), "seo")


class Activity(unittest.TestCase):
    def test_counts_and_hours(self):
        tasks = ["post yaz", "post yaz", "hesabat çıxar", "SEO audit"]
        a = il.activity_from_tasks(tasks)
        self.assertEqual(a["deliverables"], 4)
        self.assertEqual(a["requests_answered"], 4)
        self.assertEqual(a["by_category"]["content"], 2)
        self.assertEqual(a["by_category"]["report"], 1)
        self.assertEqual(a["by_category"]["seo"], 1)
        # 2*30 + 1*40 + 1*60 = 160 min = 2.7h
        self.assertAlmostEqual(a["hours_saved_est"], round(160 / 60, 1))

    def test_empty_is_zero_not_crash(self):
        a = il.activity_from_tasks([])
        self.assertEqual(a["deliverables"], 0)
        self.assertEqual(a["hours_saved_est"], 0.0)


class SourceLabels(unittest.TestCase):
    def test_live_demo_unavailable(self):
        self.assertEqual(il._source_label({"mode": "live"}), "CANLI")
        self.assertEqual(il._source_label({"mode": "demo"}), "DEMO")
        self.assertEqual(il._source_label(None), "ƏLÇATMAZ")


class Scorecard(unittest.TestCase):
    def _activity(self):
        return il.activity_from_tasks(["post yaz", "hesabat"])

    def test_blended_scorecard_live(self):
        ads = {"mode": "live", "totals": {"spend": 300.0, "leads": 100, "messages": 42}}
        ads_prev = {"mode": "live", "totals": {"spend": 320.0, "leads": 80, "messages": 40}}
        cx = {"mode": "live", "totals": {"messages": 210, "resolution_rate": 94.0}}
        sc = il.compute_scorecard(month="2026-07", ads=ads, ads_prev=ads_prev,
                                  ga4=None, cx=cx, activity=self._activity())
        self.assertEqual(sc["results"]["leads"]["value"], 142)
        self.assertEqual(sc["results"]["leads"]["prev"], 120)
        self.assertGreater(sc["results"]["leads"]["delta_pct"], 0)  # 142 vs 120 up
        # CPA = 300/142 ≈ 2.11 now vs 320/120 ≈ 2.67 before → improved (negative delta)
        self.assertLess(sc["results"]["cpa"]["delta_pct"], 0)
        self.assertEqual(sc["results"]["cpa"]["source"], "CANLI")
        self.assertEqual(sc["results"]["sla"]["value"], 94.0)
        self.assertEqual(sc["results"]["sla"]["signals"], 210)
        self.assertEqual(sc["sources"]["ga4"], "ƏLÇATMAZ")
        self.assertIn("142", sc["headline"])

    def test_down_source_is_labelled_not_invented(self):
        sc = il.compute_scorecard(month="2026-07", ads=None, ads_prev=None,
                                  ga4=None, cx=None, activity=self._activity())
        self.assertIsNone(sc["results"]["leads"]["value"])
        self.assertEqual(sc["results"]["leads"]["source"], "ƏLÇATMAZ")
        self.assertEqual(sc["results"]["conversions"]["source"], "ƏLÇATMAZ")
        # work side still real (came from the queue, not a fetched source)
        self.assertEqual(sc["work"]["deliverables"], 2)

    def test_ga4_conversions_pulled_defensively(self):
        ga4 = {"mode": "live", "totals": {"conversions": 37}}
        sc = il.compute_scorecard(month="2026-07", ads=None, ads_prev=None,
                                  ga4=ga4, cx=None, activity=self._activity())
        self.assertEqual(sc["results"]["conversions"]["value"], 37)
        self.assertEqual(sc["results"]["conversions"]["source"], "CANLI")


class Bounds(unittest.TestCase):
    def test_prev_month_rolls_year(self):
        self.assertEqual(il._prev_month("2026-01"), "2025-12")
        self.assertEqual(il._prev_month("2026-07"), "2026-06")

    def test_month_bounds_cover_full_month(self):
        start, end = il._month_bounds("2026-02")  # 28 days
        self.assertLess(start, end)
        import datetime as dt
        self.assertEqual(dt.datetime.fromtimestamp(start).day, 1)


class ReportText(unittest.TestCase):
    def test_report_runs_offline_labels_sources(self):
        # every source down → report still renders and flags the honesty note
        from unittest import mock
        with mock.patch.object(il, "_get_json", return_value=None), \
                mock.patch.object(il, "_collect_activity",
                                  return_value=il.activity_from_tasks(["post"])):
            text = il.report("2026-07")
        self.assertIn("XALQ TƏSİR JURNALI", text)
        self.assertIn("ƏLÇATMAZ", text)
        self.assertIn("uydurulmur", text)


if __name__ == "__main__":
    unittest.main()
