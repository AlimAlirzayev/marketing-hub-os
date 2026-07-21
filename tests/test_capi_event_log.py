"""Offline tests for meta-capi/event_log.py — the durable CAPI event journal.

Pure log→read→aggregate roundtrip in a temp dir (CAPI_EVENT_LOG override); no
network, no Meta. Guards the contract the İcra Paneli CAPI card charts against.
"""

from __future__ import annotations

import datetime as dt
import importlib
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "meta-capi"))

import event_log  # noqa: E402


def _ts(days_ago: float) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    return int((now - dt.timedelta(days=days_ago)).timestamp())


class EventLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["CAPI_EVENT_LOG"] = os.path.join(self.tmp.name, "events.jsonl")
        importlib.reload(event_log)

    def tearDown(self) -> None:
        os.environ.pop("CAPI_EVENT_LOG", None)
        self.tmp.cleanup()

    # --- write side ---------------------------------------------------------
    def test_log_appends_and_defaults(self):
        self.assertTrue(event_log.log_event({"event": "Lead", "status": "ok"}))
        self.assertTrue(event_log.log_event({"event": "Step_FormStart", "status": "ok"}))
        rows = list(event_log.read_events())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event"], "Lead")
        self.assertEqual(rows[0]["count"], 1)          # default
        self.assertIsInstance(rows[0]["t"], int)       # default timestamp

    def test_log_never_raises_on_bad_path(self):
        # A directory component that is actually a FILE → open/makedirs must fail.
        blocker = os.path.join(self.tmp.name, "blocker")
        with open(blocker, "w", encoding="utf-8") as f:
            f.write("x")
        os.environ["CAPI_EVENT_LOG"] = os.path.join(blocker, "sub", "x.jsonl")
        importlib.reload(event_log)
        self.assertFalse(event_log.log_event({"event": "X"}))  # False, no raise

    def test_corrupt_lines_are_skipped(self):
        event_log.log_event({"event": "Lead", "status": "ok"})
        with open(os.environ["CAPI_EVENT_LOG"], "a", encoding="utf-8") as f:
            f.write("{broken json\n\n")
        event_log.log_event({"event": "Purchase", "status": "ok"})
        self.assertEqual(len(list(event_log.read_events())), 2)

    # --- aggregate (pure) ---------------------------------------------------
    def test_aggregate_counts_by_event_and_day(self):
        recs = [
            {"t": _ts(0.1), "event": "Lead", "status": "ok", "count": 1},
            {"t": _ts(0.2), "event": "Lead", "status": "ok", "count": 1},
            {"t": _ts(1.1), "event": "Step_FormStart", "status": "ok", "count": 1},
            {"t": _ts(1.2), "event": "Purchase", "status": "ok", "count": 3,
             "value": 360.0, "currency": "AZN"},
            {"t": _ts(0.3), "event": "Lead", "status": "error", "count": 1},
        ]
        agg = event_log.aggregate(recs)
        self.assertEqual(agg["total"], 7)
        self.assertEqual(agg["sent_ok"], 6)
        self.assertEqual(agg["failed"], 1)
        self.assertEqual(agg["value_sum"], 360.0)
        self.assertEqual(agg["currency"], "AZN")
        # Lead and Purchase tie at 3; order among ties is insertion-stable, so
        # assert the counts, not the tie order.
        counts = {r["event"]: r["count"] for r in agg["by_event"]}
        self.assertEqual(counts, {"Lead": 3, "Purchase": 3, "Step_FormStart": 1})
        self.assertEqual(len(agg["daily"]), 2)                       # two UTC days
        self.assertTrue(agg["daily"][0]["date"] < agg["daily"][1]["date"])

    def test_test_events_excluded_by_default(self):
        recs = [
            {"t": _ts(0.1), "event": "Lead", "status": "ok", "test": True},
            {"t": _ts(0.1), "event": "Lead", "status": "ok", "test": False},
        ]
        self.assertEqual(event_log.aggregate(recs)["total"], 1)
        self.assertEqual(event_log.aggregate(recs, include_test=True)["total"], 2)

    # --- report (IO + window) ----------------------------------------------
    def test_report_window_filters_old_events(self):
        event_log.log_event({"t": _ts(40), "event": "Old", "status": "ok"})
        event_log.log_event({"t": _ts(2), "event": "New", "status": "ok"})
        rep = event_log.report(30)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["total"], 1)
        self.assertEqual(rep["by_event"][0]["event"], "New")
        self.assertEqual(rep["source"], "jurnal (events.jsonl)")


if __name__ == "__main__":
    unittest.main()
