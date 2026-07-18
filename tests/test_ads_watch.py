"""Ads morning pulse rail — pure anomaly math + honest degradation.

analyze() is a pure function over synthetic daily rows, so every threshold is
tested offline; report() is tested with the HTTP seam mocked (no live 8800).
"""

import unittest
from unittest import mock


def _days(rows):
    """rows: [(date, spend, impressions, clicks, leads, messages)] -> dicts."""
    return [{"date": d, "spend": s, "impressions": i, "clicks": c,
             "leads": l, "messages": m} for d, s, i, c, l, m in rows]


BASE_WEEK = [(f"2026-07-{10 + n:02d}", 10.0, 20000, 200, 2, 4) for n in range(7)]


class AnalyzeMath(unittest.TestCase):
    def setUp(self):
        from gateway import ads_watch
        self.aw = ads_watch

    def _run(self, yesterday, today="2026-07-18"):
        return self.aw.analyze(_days(BASE_WEEK + [yesterday]), today=today)

    def test_normal_day_has_no_anomalies(self):
        out = self._run(("2026-07-17", 11.0, 21000, 210, 2, 4))
        self.assertTrue(out["enough_history"])
        self.assertEqual(out["anomalies"], [])

    def test_todays_partial_row_is_excluded(self):
        rows = _days(BASE_WEEK + [("2026-07-17", 11.0, 21000, 210, 2, 4),
                                  ("2026-07-18", 0.5, 300, 2, 0, 0)])
        out = self.aw.analyze(rows, today="2026-07-18")
        self.assertEqual(out["yesterday"]["date"], "2026-07-17")

    def test_delivery_stop_flagged(self):
        out = self._run(("2026-07-17", 0.0, 0, 0, 0, 0))
        self.assertIn("delivery_stop", [a["kind"] for a in out["anomalies"]])

    def test_spend_spike_flagged(self):
        out = self._run(("2026-07-17", 25.0, 40000, 400, 4, 8))
        self.assertIn("spend_spike", [a["kind"] for a in out["anomalies"]])

    def test_cpr_spike_flagged_when_results_dry_up(self):
        # Same spend, zero results -> cost per result explodes.
        out = self._run(("2026-07-17", 10.0, 20000, 200, 0, 0))
        self.assertIn("cpr_spike", [a["kind"] for a in out["anomalies"]])

    def test_ctr_collapse_flagged(self):
        out = self._run(("2026-07-17", 10.0, 20000, 40, 2, 4))
        self.assertIn("ctr_collapse", [a["kind"] for a in out["anomalies"]])

    def test_thin_history_disables_ratio_checks(self):
        rows = _days([("2026-07-16", 10.0, 20000, 200, 2, 4),
                      ("2026-07-17", 0.0, 0, 0, 0, 0)])
        out = self.aw.analyze(rows, today="2026-07-18")
        self.assertFalse(out["enough_history"])
        self.assertEqual(out["anomalies"], [])

    def test_no_complete_days_is_safe(self):
        out = self.aw.analyze(_days([("2026-07-18", 1.0, 100, 1, 0, 0)]),
                              today="2026-07-18")
        self.assertIsNone(out["yesterday"])
        self.assertEqual(out["anomalies"], [])


class ReportFormat(unittest.TestCase):
    def setUp(self):
        from gateway import ads_watch
        self.aw = ads_watch

    def test_unreachable_source_degrades_honestly(self):
        with mock.patch.object(self.aw, "_fetch_sales", return_value=None):
            text = self.aw.report()
        self.assertIn("əlçatan deyil", text)
        self.assertNotIn("Anomaliya yoxdur", text)

    def test_report_carries_anomaly_and_totals(self):
        sales = {"status": "live", "currency": "USD",
                 "daily": _days(BASE_WEEK + [("2026-07-17", 0.0, 0, 0, 0, 0)]),
                 "totals": {"spend": 70.0, "leads": 14, "messages": 28},
                 "campaigns": [{"name": "Sale", "spend": 50.0}]}
        with mock.patch.object(self.aw, "_fetch_sales", return_value=sales), \
             mock.patch.object(self.aw._dt, "date", wraps=self.aw._dt.date) as d:
            d.today.return_value = self.aw._dt.date(2026, 7, 18)
            text = self.aw.report()
        self.assertIn("DAYANIB", text)
        self.assertIn("70.00", text)
        self.assertIn("Sale", text)


if __name__ == "__main__":
    unittest.main()
