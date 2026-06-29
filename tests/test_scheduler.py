"""Recurring-job scheduler — pure due-logic + run_pending dispatch (no threads)."""

import datetime as dt
import os
import tempfile
import unittest


class _IsolatedSchedDB(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._saved = os.environ.get("SCHED_DB_PATH")
        os.environ["SCHED_DB_PATH"] = os.path.join(self._dir, "jobs.sqlite")
        from gateway import scheduler
        self.scheduler = scheduler

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("SCHED_DB_PATH", None)
        else:
            os.environ["SCHED_DB_PATH"] = self._saved


class DueLogic(_IsolatedSchedDB):
    def test_due_after_time_when_not_run_today(self):
        now = dt.datetime(2026, 6, 24, 9, 5)
        self.assertTrue(self.scheduler.is_due("09:00", now, last_run_date=None))

    def test_not_due_before_time(self):
        now = dt.datetime(2026, 6, 24, 8, 59)
        self.assertFalse(self.scheduler.is_due("09:00", now, last_run_date=None))

    def test_not_due_if_already_ran_today(self):
        now = dt.datetime(2026, 6, 24, 9, 5)
        self.assertFalse(self.scheduler.is_due("09:00", now, last_run_date="2026-06-24"))

    def test_due_again_next_day(self):
        now = dt.datetime(2026, 6, 25, 9, 5)
        self.assertTrue(self.scheduler.is_due("09:00", now, last_run_date="2026-06-24"))

    def test_invalid_time_never_due(self):
        self.assertFalse(self.scheduler.is_due("99:99", dt.datetime.now(), None))


class CrudAndDispatch(_IsolatedSchedDB):
    def test_add_validates_time_format(self):
        with self.assertRaises(ValueError):
            self.scheduler.add_schedule("9am", "morning digest")

    def test_add_list_remove(self):
        sid = self.scheduler.add_schedule("07:30", "Səhər brifinqi hazırla")
        rows = self.scheduler.list_schedules()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["at_hhmm"], "07:30")
        self.assertTrue(self.scheduler.remove_schedule(sid))
        self.assertEqual(self.scheduler.list_schedules(), [])

    def test_run_pending_submits_due_once_per_day(self):
        sched = self.scheduler
        sched.add_schedule("07:00", "Günaydın hesabatı")
        calls = []
        orig = sched.queue.submit
        sched.queue.submit = lambda task, source="cli", chat_id=None: (calls.append((task, source)) or 1)
        try:
            now = dt.datetime(2026, 6, 24, 7, 30)
            first = sched.run_pending(now)
            second = sched.run_pending(now)  # same day -> must NOT submit again
        finally:
            sched.queue.submit = orig
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(calls, [("Günaydın hesabatı", "schedule")])

    def test_run_pending_skips_when_duplicate_already_queued(self):
        sched = self.scheduler
        sched.add_schedule("07:00", "Günaydın hesabatı")
        calls = []
        orig_submit, orig_has = sched.queue.submit, sched.queue.has_queued_task
        sched.queue.submit = lambda task, source="cli", chat_id=None: (calls.append(task) or 1)
        sched.queue.has_queued_task = lambda task, source=None: True  # one already waits
        try:
            out = sched.run_pending(dt.datetime(2026, 6, 24, 7, 30))
        finally:
            sched.queue.submit, sched.queue.has_queued_task = orig_submit, orig_has
        self.assertEqual(out, [])     # nothing newly submitted
        self.assertEqual(calls, [])   # submit must NOT be called
        # still marked handled for today, so it doesn't retry on every tick
        self.assertEqual(sched.list_schedules()[0]["last_run_date"], "2026-06-24")


class SupervisorSmoke(unittest.TestCase):
    def test_supervisor_imports_and_supervise_respects_stop(self):
        try:
            from gateway import supervisor
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"supervisor deps unavailable: {exc}")
        # _supervise must exit promptly when the stop event is set.
        supervisor._stop.set()
        try:
            supervisor._supervise("t", lambda: False, idle=0.01)  # returns immediately
        finally:
            supervisor._stop.clear()


if __name__ == "__main__":
    unittest.main()
