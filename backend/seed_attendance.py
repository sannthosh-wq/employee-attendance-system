from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import text

from database import SessionLocal, engine
from models import Attendance, AttendancePunch, Employee, Leave


START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 5, 12)
SHIFT_START = time(9, 0)
SHIFT_END = time(18, 0)
RANDOM_SEED = 20260101
TOTAL_EMPLOYEES_FOR_DEMO = 13

APPROVED_REASONS = ["Fever", "Medical emergency", "Family function", "Marriage", "Exam"]
CASUAL_REASONS = ["No reason", "Going out", "Tired", "Not feeling like working"]
DEPARTMENTS = ["Engineering", "HR", "Finance", "Sales", "Operations", "Support"]

MAX_CASUAL_APPROVALS_PER_MONTH = 2
MAX_TOTAL_APPROVED_LEAVES_PER_MONTH = 5


@dataclass
class LeaveDecision:
    employee: Employee
    reason: str
    leave_type: str
    status: str


def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def random_time_on(day: date, start_at: time, end_at: time) -> datetime:
    start = datetime.combine(day, start_at)
    end = datetime.combine(day, end_at)
    seconds = random.randint(0, int((end - start).total_seconds()))
    return start + timedelta(seconds=seconds)


def minutes_between(later: datetime, earlier: time) -> int:
    baseline = datetime.combine(later.date(), earlier)
    return max(0, int((later - baseline).total_seconds() // 60))


def hours_between(start: datetime | None, end: datetime | None) -> float:
    if not start or not end:
        return 0.0
    return round((end - start).total_seconds() / 3600, 2)


def month_key(day: date) -> tuple[int, int]:
    return day.year, day.month


def is_working_day(day: date) -> bool:
    return day.weekday() != 6


def ensure_seed_schema() -> None:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS department VARCHAR"))
        connection.execute(text("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'Present'"))
        connection.execute(text("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS working_hours DOUBLE PRECISION DEFAULT 0"))
        connection.execute(text("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS late_minutes INTEGER DEFAULT 0"))
        connection.execute(text("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS early_minutes INTEGER DEFAULT 0"))
        connection.execute(text("ALTER TABLE leaves ADD COLUMN IF NOT EXISTS leave_date DATE"))
        connection.execute(text("ALTER TABLE leaves ADD COLUMN IF NOT EXISTS leave_type VARCHAR"))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_attendance_employee_date
            ON attendance(employee_id, date)
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_attendance_date_status
            ON attendance(date, status)
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_attendance_late_date
            ON attendance(date)
            WHERE is_late = TRUE
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_attendance_early_date
            ON attendance(date)
            WHERE left_early = TRUE
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_leaves_date_status
            ON leaves(leave_date, status)
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_employees_department
            ON employees(department)
        """))


def load_demo_employees(db) -> list[Employee]:
    employees = (
        db.query(Employee)
        .filter((Employee.role.is_(None)) | (Employee.role != "super_admin"))
        .order_by(Employee.id)
        .limit(TOTAL_EMPLOYEES_FOR_DEMO)
        .all()
    )

    if len(employees) < TOTAL_EMPLOYEES_FOR_DEMO:
        raise RuntimeError(
            f"Expected {TOTAL_EMPLOYEES_FOR_DEMO} employees for the demo, found {len(employees)}. "
            "Create employees first, then run this seeder."
        )

    for index, employee in enumerate(employees):
        employee.joined_at = START_DATE
        employee.department = employee.department or DEPARTMENTS[index % len(DEPARTMENTS)]
        employee.shift = employee.shift or "morning"

    return employees


def remove_existing_seed_data(db) -> None:
    attendance_ids = [
        row.id
        for row in db.query(Attendance.id)
        .filter(Attendance.date >= START_DATE, Attendance.date <= END_DATE)
        .all()
    ]

    if attendance_ids:
        db.query(AttendancePunch).filter(AttendancePunch.attendance_id.in_(attendance_ids)).delete(
            synchronize_session=False
        )

    db.query(Attendance).filter(Attendance.date >= START_DATE, Attendance.date <= END_DATE).delete(
        synchronize_session=False
    )
    db.query(Leave).filter(Leave.start_date >= START_DATE, Leave.start_date <= END_DATE).delete(
        synchronize_session=False
    )
    db.flush()


def leave_application_count(day: date) -> int:
    # Most days have 1-3 applications. A few busier days have 4-5 for approval-ratio demos.
    if day.day in {5, 12, 19, 26} or random.random() < 0.22:
        return random.randint(3, 5)
    return random.randint(1, 3)


def choose_leave_reason() -> tuple[str, str]:
    if random.random() < 0.68:
        return random.choice(APPROVED_REASONS), "Approved-type"
    return random.choice(CASUAL_REASONS), "Casual-type"


def decide_leave_status(
    day: date,
    leave_type: str,
    same_day_position: int,
    casual_approvals: dict[tuple[int, int, int], int],
    total_approved_leaves: dict[tuple[int, int, int], int],
    employee_id: int,
) -> str:
    key = (employee_id, *month_key(day))

    if total_approved_leaves[key] >= MAX_TOTAL_APPROVED_LEAVES_PER_MONTH:
        return "rejected"

    if same_day_position > 3:
        return "rejected"

    if leave_type == "Casual-type":
        if casual_approvals[key] >= MAX_CASUAL_APPROVALS_PER_MONTH:
            return "rejected"
        approved = random.random() < 0.60
    else:
        approved = random.random() < 0.86

    if not approved:
        return "rejected"

    total_approved_leaves[key] += 1
    if leave_type == "Casual-type":
        casual_approvals[key] += 1

    return "approved"


def plan_leave_decisions(
    day: date,
    employees: list[Employee],
    casual_approvals: dict[tuple[int, int, int], int],
    total_approved_leaves: dict[tuple[int, int, int], int],
    employee_activity_score: dict[int, float],
) -> list[LeaveDecision]:
    count = min(leave_application_count(day), len(employees))
    shuffled = employees[:]
    random.shuffle(shuffled)
    candidates = sorted(shuffled, key=lambda employee: employee_activity_score[employee.id])[:count]

    decisions = []
    for position, employee in enumerate(candidates, start=1):
        reason, leave_type = choose_leave_reason()
        status = decide_leave_status(
            day,
            leave_type,
            position,
            casual_approvals,
            total_approved_leaves,
            employee.id,
        )
        decisions.append(
            LeaveDecision(
                employee=employee,
                reason=reason,
                leave_type=leave_type,
                status=status,
            )
        )
        employee_activity_score[employee.id] += 0.7

    return decisions


def choose_absent_employee(
    working_day_number: int,
    employees: list[Employee],
    unavailable_ids: set[int],
    employee_activity_score: dict[int, float],
) -> int | None:
    if working_day_number % 8 != 0:
        return None

    candidates = [employee for employee in employees if employee.id not in unavailable_ids]
    if not candidates:
        return None

    employee = min(candidates, key=lambda item: employee_activity_score[item.id] + random.random())
    employee_activity_score[employee.id] += 1.2
    return employee.id


def balance_present_count(
    employees: list[Employee],
    unavailable_ids: set[int],
    employee_activity_score: dict[int, float],
) -> set[int]:
    # For 13 employees, 70-80% present means roughly 9-10 present employees.
    target_present = random.choice([9, 9, 10, 10])
    target_unavailable = max(0, len(employees) - target_present)
    extra_absent_ids: set[int] = set()

    while len(unavailable_ids | extra_absent_ids) < target_unavailable:
        candidates = [
            employee
            for employee in employees
            if employee.id not in unavailable_ids and employee.id not in extra_absent_ids
        ]
        if not candidates:
            break
        employee = min(candidates, key=lambda item: employee_activity_score[item.id] + random.random())
        extra_absent_ids.add(employee.id)
        employee_activity_score[employee.id] += 1.0

    return extra_absent_ids


def build_attendance_for_day(
    day: date,
    employees: list[Employee],
    leave_decisions: list[LeaveDecision],
    scheduled_absent_id: int | None,
    extra_absent_ids: set[int],
) -> tuple[list[Attendance], list[tuple[Attendance, str, datetime]], list[Leave]]:
    leave_by_employee = {decision.employee.id: decision for decision in leave_decisions}
    unavailable_ids = set(leave_by_employee)
    if scheduled_absent_id:
        unavailable_ids.add(scheduled_absent_id)
    unavailable_ids.update(extra_absent_ids)

    present_employees = [employee for employee in employees if employee.id not in unavailable_ids]
    late_count = min(len(present_employees), random.choice([1, 1, 2]))
    late_ids = {employee.id for employee in random.sample(present_employees, late_count)}
    early_id = random.choice(present_employees).id if present_employees else None

    attendance_rows: list[Attendance] = []
    punch_rows: list[tuple[Attendance, str, datetime]] = []
    leave_rows: list[Leave] = []

    for employee in employees:
        decision = leave_by_employee.get(employee.id)
        status = "Present"
        punch_in = None
        punch_out = None
        late_minutes = 0
        early_minutes = 0

        if decision:
            leave_rows.append(
                Leave(
                    employee_id=employee.id,
                    start_date=day,
                    end_date=day,
                    leave_date=day,
                    reason=decision.reason,
                    leave_type=decision.leave_type,
                    status=decision.status,
                    cancelled_at=datetime.now(UTC) if decision.status == "rejected" else None,
                )
            )
            status = "Leave" if decision.status == "approved" else "Absent"
        elif employee.id == scheduled_absent_id or employee.id in extra_absent_ids:
            status = "Absent"
        else:
            if employee.id in late_ids:
                punch_in = random_time_on(day, time(9, 10), time(10, 0))
                late_minutes = minutes_between(punch_in, SHIFT_START)
            else:
                punch_in = random_time_on(day, time(8, 55), time(9, 5))

            if employee.id == early_id:
                punch_out = random_time_on(day, time(15, 30), time(16, 30))
                early_minutes = minutes_between(datetime.combine(day, SHIFT_END), punch_out.time())
            else:
                punch_out = random_time_on(day, time(17, 45), time(18, 15))

        work_hours = hours_between(punch_in, punch_out)
        attendance = Attendance(
            employee_id=employee.id,
            date=day,
            login_time=punch_in,
            logout_time=punch_out,
            total_hours=timedelta(hours=work_hours),
            status=status,
            is_late=late_minutes > 0,
            left_early=early_minutes > 0,
            late_minutes=late_minutes,
            early_minutes=early_minutes,
            working_hours=work_hours,
        )
        attendance_rows.append(attendance)

        if status == "Present" and punch_in and punch_out:
            punch_rows.append((attendance, "in", punch_in))
            punch_rows.append((attendance, "out", punch_out))

    return attendance_rows, punch_rows, leave_rows


def seed_attendance() -> None:
    random.seed(RANDOM_SEED)
    ensure_seed_schema()

    db = SessionLocal()
    try:
        employees = load_demo_employees(db)
        remove_existing_seed_data(db)

        casual_approvals: dict[tuple[int, int, int], int] = defaultdict(int)
        total_approved_leaves: dict[tuple[int, int, int], int] = defaultdict(int)
        employee_activity_score = {employee.id: random.random() for employee in employees}

        all_attendance: list[Attendance] = []
        all_punches: list[tuple[Attendance, str, datetime]] = []
        all_leaves: list[Leave] = []
        working_day_number = 0

        for day in daterange(START_DATE, END_DATE):
            if not is_working_day(day):
                continue

            working_day_number += 1
            leave_decisions = plan_leave_decisions(
                day,
                employees,
                casual_approvals,
                total_approved_leaves,
                employee_activity_score,
            )
            unavailable_ids = {decision.employee.id for decision in leave_decisions}
            scheduled_absent_id = choose_absent_employee(
                working_day_number,
                employees,
                unavailable_ids,
                employee_activity_score,
            )
            if scheduled_absent_id:
                unavailable_ids.add(scheduled_absent_id)

            extra_absent_ids = balance_present_count(employees, unavailable_ids, employee_activity_score)
            attendance_rows, punch_rows, leave_rows = build_attendance_for_day(
                day,
                employees,
                leave_decisions,
                scheduled_absent_id,
                extra_absent_ids,
            )

            all_attendance.extend(attendance_rows)
            all_punches.extend(punch_rows)
            all_leaves.extend(leave_rows)

        db.add_all(all_leaves)
        db.add_all(all_attendance)
        db.flush()

        db.add_all(
            AttendancePunch(
                attendance_id=attendance.id,
                employee_id=attendance.employee_id,
                punch_type=punch_type,
                punch_time=punch_time,
            )
            for attendance, punch_type, punch_time in all_punches
        )

        db.commit()

        present_count = sum(1 for row in all_attendance if row.status == "Present")
        absent_count = sum(1 for row in all_attendance if row.status == "Absent")
        leave_count = sum(1 for row in all_attendance if row.status == "Leave")
        late_count = sum(1 for row in all_attendance if row.is_late)
        early_count = sum(1 for row in all_attendance if row.left_early)

        print(f"Seeded {len(all_attendance)} attendance rows for {len(employees)} employees.")
        print(f"Seeded {len(all_leaves)} leave applications.")
        print(f"Present: {present_count}, Absent: {absent_count}, Leave: {leave_count}")
        print(f"Late entries: {late_count}, Early exits: {early_count}")
        print(f"Date range: {START_DATE} to {END_DATE}. Sundays excluded.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_attendance()
