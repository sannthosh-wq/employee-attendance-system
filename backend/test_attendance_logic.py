import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from attendance_logic import (
    attendance_day_credit,
    employee_shift_date_status,
    get_shift_window,
    get_shift_window_for_date,
    is_working_day,
)


class ShiftWindowTests(unittest.TestCase):
    def test_morning_shift_uses_same_calendar_date(self):
        shift_date, shift_start, _, shift_end = get_shift_window(
            datetime(2026, 5, 10, 9, 0),
            "morning",
        )

        self.assertEqual(shift_date, date(2026, 5, 10))
        self.assertEqual(shift_start, datetime(2026, 5, 10, 9, 0))
        self.assertEqual(shift_end, datetime(2026, 5, 10, 18, 0))

    def test_night_shift_uses_start_date_before_midnight(self):
        shift_date, shift_start, _, shift_end = get_shift_window(
            datetime(2026, 5, 10, 21, 0),
            "night",
        )

        self.assertEqual(shift_date, date(2026, 5, 10))
        self.assertEqual(shift_start, datetime(2026, 5, 10, 21, 0))
        self.assertEqual(shift_end, datetime(2026, 5, 11, 6, 0))

    def test_night_shift_still_uses_start_date_after_midnight(self):
        shift_date, shift_start, _, shift_end = get_shift_window(
            datetime(2026, 5, 11, 6, 0),
            "night",
        )

        self.assertEqual(shift_date, date(2026, 5, 10))
        self.assertEqual(shift_start, datetime(2026, 5, 10, 21, 0))
        self.assertEqual(shift_end, datetime(2026, 5, 11, 6, 0))

    def test_calendar_night_shift_for_may_11_starts_on_may_11_evening(self):
        shift_start, _, shift_end = get_shift_window_for_date(date(2026, 5, 11), "night")

        self.assertEqual(shift_start, datetime(2026, 5, 11, 21, 0))
        self.assertEqual(shift_end, datetime(2026, 5, 12, 6, 0))

    def test_calendar_status_does_not_count_previous_night_before_evening(self):
        db = QueryStub()
        employee = SimpleNamespace(
            id=1,
            role="employee",
            shift="night",
            joined_at=date(2026, 5, 1),
        )

        status = employee_shift_date_status(
            db=db,
            employee=employee,
            target_date=date(2026, 5, 11),
            now=datetime(2026, 5, 11, 10, 0),
        )

        self.assertEqual(status, "Shift Not Started")

    def test_sunday_is_not_a_working_day(self):
        self.assertFalse(is_working_day(date(2026, 5, 10)))
        self.assertTrue(is_working_day(date(2026, 5, 11)))

    def test_sunday_attendance_is_extra_work_not_present(self):
        db = AttendanceQueryStub()
        employee = SimpleNamespace(
            id=1,
            role="employee",
            shift="morning",
            joined_at=date(2026, 5, 1),
        )

        status = employee_shift_date_status(
            db=db,
            employee=employee,
            target_date=date(2026, 5, 10),
            now=datetime(2026, 5, 10, 12, 0),
        )

        self.assertEqual(status, "Extra Work")

    def test_late_by_more_than_three_hours_counts_half_day(self):
        record = SimpleNamespace(
            date=date(2026, 5, 11),
            login_time=datetime(2026, 5, 11, 12, 1),
        )

        self.assertEqual(attendance_day_credit(record, "morning"), 0.5)

    def test_late_within_three_hours_counts_full_day(self):
        record = SimpleNamespace(
            date=date(2026, 5, 11),
            login_time=datetime(2026, 5, 11, 12, 0),
        )

        self.assertEqual(attendance_day_credit(record, "morning"), 1)

    def test_night_shift_half_day_uses_shift_start_date(self):
        record = SimpleNamespace(
            date=date(2026, 5, 11),
            login_time=datetime(2026, 5, 12, 0, 1),
        )

        self.assertEqual(attendance_day_credit(record, "night"), 0.5)


class QueryStub:
    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class AttendanceQueryStub(QueryStub):
    def __init__(self):
        self.calls = 0

    def query(self, *args, **kwargs):
        self.calls += 1
        return self

    def first(self):
        if self.calls == 1:
            return None

        return SimpleNamespace(
            id=1,
            login_time=datetime(2026, 5, 10, 9, 0),
        )


if __name__ == "__main__":
    unittest.main()
