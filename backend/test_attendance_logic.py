import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from attendance_logic import (
    JOINED_TODAY_STATUS,
    active_attendance_for_punch_out,
    attendance_day_credit,
    employee_shift_date_status,
    get_shift_window,
    get_shift_window_for_date,
    is_working_day,
    leave_allowance,
)
from payroll_service import payroll_components


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

    def test_night_shift_punch_out_can_find_open_previous_shift_after_noon(self):
        db = PunchOutQueryStub()

        record, shift_date, shift_start, _, shift_end, last_punch = active_attendance_for_punch_out(
            db=db,
            employee_id=1,
            shift="night",
            now=datetime(2026, 5, 11, 13, 0),
        )

        self.assertEqual(record.id, 10)
        self.assertEqual(shift_date, date(2026, 5, 10))
        self.assertEqual(shift_start, datetime(2026, 5, 10, 21, 0))
        self.assertEqual(shift_end, datetime(2026, 5, 11, 6, 0))
        self.assertEqual(last_punch.punch_type, "in")

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

    def test_employee_joining_today_starts_work_tomorrow(self):
        db = QueryStub()
        employee = SimpleNamespace(
            id=1,
            role="employee",
            shift="morning",
            joined_at=date(2026, 5, 12),
        )

        status = employee_shift_date_status(
            db=db,
            employee=employee,
            target_date=date(2026, 5, 12),
            now=datetime(2026, 5, 12, 10, 0),
        )

        self.assertEqual(status, JOINED_TODAY_STATUS)

    def test_existing_employee_before_policy_keeps_join_day_attendance(self):
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

    def test_leave_allowance_keeps_seventy_percent_attendance(self):
        employee = SimpleNamespace(joined_at=date(2026, 5, 1))

        self.assertEqual(leave_allowance(employee, month=5, year=2026), 7)

    def test_leave_allowance_uses_join_date_inside_month(self):
        employee = SimpleNamespace(joined_at=date(2026, 5, 18))

        self.assertEqual(leave_allowance(employee, month=5, year=2026), 3)

    def test_payroll_components_calculate_net_salary(self):
        salary = SimpleNamespace(
            basic_salary=Decimal("30000"),
            hra=Decimal("12000"),
            travel_allowance=Decimal("2000"),
            medical_allowance=Decimal("1500"),
        )
        summary = {
            "absent_days": Decimal("2"),
            "extra_work_hours": Decimal("8"),
        }

        result = payroll_components(salary, summary, Decimal("10"))

        self.assertEqual(result["gross_salary"], Decimal("45500.00"))
        self.assertEqual(result["overtime_pay"], Decimal("0.00"))
        self.assertEqual(result["loss_of_pay"], Decimal("2000.00"))
        self.assertEqual(result["pf"], Decimal("3600.00"))
        self.assertEqual(result["tax"], Decimal("4550.00"))
        self.assertEqual(result["net_salary"], Decimal("35350.00"))


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


class PunchOutQueryStub(QueryStub):
    def __init__(self):
        self.model_name = None
        self.attendance_calls = 0

    def query(self, model, *args, **kwargs):
        self.model_name = model.__name__
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if self.model_name == "Attendance":
            self.attendance_calls += 1
            if self.attendance_calls == 1:
                return SimpleNamespace(id=10)
            return None

        if self.model_name == "AttendancePunch":
            return SimpleNamespace(punch_type="in")

        return None


if __name__ == "__main__":
    unittest.main()
