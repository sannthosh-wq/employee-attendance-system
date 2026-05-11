from calendar import monthrange
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import extract
from sqlalchemy.orm import Session

from models import Attendance, AttendancePunch, Employee, Leave


VALID_SHIFTS = {"morning", "night"}
MORNING_SHIFT_START = time(9, 0)
MORNING_SHIFT_END = time(18, 0)
NIGHT_SHIFT_START = time(21, 0)
NIGHT_SHIFT_DURATION = timedelta(hours=9)
NIGHT_SHIFT_POST_END_CUTOFF = time(12, 0)
SHIFT_GRACE_PERIOD = timedelta(minutes=15)
HALF_DAY_AFTER = timedelta(hours=3)
VALID_ROLES = {
    "employee",
    "admin",
    "super_admin",
    "developer",
    "frontend_developer",
    "backend_developer",
    "data_analyst",
    "data_scientist",
    "ml_developer",
    "software_engineer",
}
REPORT_START_YEAR = 2026
REPORT_START_MONTH = 5


def night_shift_start_date(now: datetime):
    if now.time() <= NIGHT_SHIFT_POST_END_CUTOFF:
        return now.date() - timedelta(days=1)
    return now.date()


def get_shift_window_for_date(shift_date: date, shift: str):
    if shift == "morning":
        shift_start = datetime.combine(shift_date, MORNING_SHIFT_START)
        shift_end = datetime.combine(shift_date, MORNING_SHIFT_END)
        return shift_start, shift_start + SHIFT_GRACE_PERIOD, shift_end

    if shift == "night":
        shift_start = datetime.combine(shift_date, NIGHT_SHIFT_START)
        shift_end = shift_start + NIGHT_SHIFT_DURATION
        return shift_start, shift_start + SHIFT_GRACE_PERIOD, shift_end

    raise HTTPException(status_code=400, detail="Invalid shift")


def get_shift_window(now: datetime, shift: str):
    if shift == "morning":
        shift_date = now.date()
        shift_start, grace_time, shift_end = get_shift_window_for_date(shift_date, shift)
        return shift_date, shift_start, grace_time, shift_end

    if shift == "night":
        shift_date = night_shift_start_date(now)
        shift_start, grace_time, shift_end = get_shift_window_for_date(shift_date, shift)
        return shift_date, shift_start, grace_time, shift_end

    raise HTTPException(status_code=400, detail="Invalid shift")


def is_assignment_complete(employee):
    return bool(employee.role and employee.shift)


def require_assignment_complete(employee):
    if not is_assignment_complete(employee):
        raise HTTPException(status_code=403, detail="Admin must assign role and shift before attendance is enabled")


def employee_join_date(employee):
    return employee.joined_at or date(REPORT_START_YEAR, REPORT_START_MONTH, 1)


def working_days_between(start_date: date, end_date: date):
    if end_date < start_date:
        return 0

    days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() != 6:
            days += 1
        current += timedelta(days=1)

    return days


def is_working_day(target_date: date):
    return target_date.weekday() != 6


def attendance_day_credit(record: Attendance, shift: str):
    if not record.login_time:
        return 0

    shift_start, _, _ = get_shift_window_for_date(record.date, shift)
    if record.login_time > shift_start + HALF_DAY_AFTER:
        return 0.5

    return 1


def current_shift_date(shift: str, now: datetime | None = None):
    now = now or datetime.now()
    return get_shift_window(now, shift)[0]


def latest_punch(db: Session, attendance_id: int):
    return (
        db.query(AttendancePunch)
        .filter(AttendancePunch.attendance_id == attendance_id)
        .order_by(AttendancePunch.punch_time.desc(), AttendancePunch.id.desc())
        .first()
    )


def calculate_worked_time(db: Session, attendance_id: int, until_time: datetime | None = None):
    punches = (
        db.query(AttendancePunch)
        .filter(AttendancePunch.attendance_id == attendance_id)
        .order_by(AttendancePunch.punch_time.asc(), AttendancePunch.id.asc())
        .all()
    )

    total = timedelta()
    active_in = None

    for punch in punches:
        if punch.punch_type == "in":
            active_in = punch.punch_time
        elif punch.punch_type == "out" and active_in:
            total += punch.punch_time - active_in
            active_in = None

    if active_in and until_time:
        total += until_time - active_in

    return total


def get_shift_attendance(db: Session, employee_id: int, shift_date: date):
    return (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date == shift_date,
        )
        .first()
    )


def approved_leave_on(db: Session, employee_id: int, target_date: date):
    return (
        db.query(Leave)
        .filter(
            Leave.employee_id == employee_id,
            Leave.status == "approved",
            Leave.start_date <= target_date,
            Leave.end_date >= target_date,
        )
        .first()
    )


def has_leave_overlap(
    db: Session,
    employee_id: int,
    start_date: date,
    end_date: date,
    statuses: tuple[str, ...] = ("pending", "approved"),
):
    return (
        db.query(Leave)
        .filter(
            Leave.employee_id == employee_id,
            Leave.status.in_(statuses),
            Leave.start_date <= end_date,
            Leave.end_date >= start_date,
        )
        .first()
    )


def employee_today_status(db: Session, employee, today: date | None = None):
    if not is_assignment_complete(employee):
        return "Pending Assignment"

    today = today or date.today()
    now = datetime.now()
    shift_date, shift_start, _, shift_end = get_shift_window(now, employee.shift)

    if approved_leave_on(db, employee.id, shift_date):
        return "On Leave"

    attendance = get_shift_attendance(db, employee.id, shift_date)

    if not attendance:
        if now < shift_start:
            return "Shift Not Started"
        return "Absent"

    last_punch = latest_punch(db, attendance.id)

    if last_punch and last_punch.punch_type == "in":
        return "Working (Punched In)"

    if attendance.login_time:
        return "Present"

    return "Absent"


def employee_shift_date_status(
    db: Session,
    employee,
    target_date: date,
    now: datetime | None = None,
):
    if not is_assignment_complete(employee):
        return "Pending Assignment"

    now = now or datetime.now()

    if emp_joined := employee.joined_at:
        if target_date < emp_joined:
            return "Pending Assignment"

    if target_date > now.date():
        return "Shift Not Started"

    shift_start, _, _ = get_shift_window_for_date(target_date, employee.shift)

    if approved_leave_on(db, employee.id, target_date):
        return "On Leave"

    attendance = get_shift_attendance(db, employee.id, target_date)

    if attendance:
        if not is_working_day(target_date):
            return "Extra Work"

        last_punch = latest_punch(db, attendance.id)
        if last_punch and last_punch.punch_type == "in":
            return "Working (Punched In)"
        if attendance.login_time:
            return "Present"

    if target_date == now.date() and now < shift_start:
        return "Shift Not Started"

    if target_date.weekday() == 6:
        return "Shift Not Started"

    return "Absent"


def working_days_in_month(month: int, year: int):
    total_days = monthrange(year, month)[1]
    return sum(
        1
        for day in range(1, total_days + 1)
        if date(year, month, day).weekday() != 6
    )


def elapsed_working_days_in_month(month: int, year: int, today: date | None = None):
    today = today or date.today()
    total_days = monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, total_days)

    if today < month_start:
        return 0

    cutoff = min(today, month_end)

    return sum(
        1
        for day in range(1, cutoff.day + 1)
        if date(year, month, day).weekday() != 6
    )


def working_leave_days(start_date: date, end_date: date):
    days = 0
    current = start_date

    while current <= end_date:
        if current.weekday() != 6:
            days += 1
        current += timedelta(days=1)

    return days


def approved_leave_days_in_month(db: Session, employee_id: int, month: int, year: int):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return 0

    join_date = employee_join_date(employee)
    leaves = db.query(Leave).filter(
        Leave.employee_id == employee_id,
        Leave.status == "approved",
    ).all()

    leave_days = 0
    for leave in leaves:
        current = max(leave.start_date, join_date)
        leave_end = leave.end_date

        while current <= leave_end:
            if current.month == month and current.year == year and current.weekday() != 6:
                leave_days += 1
            current += timedelta(days=1)

    return leave_days


def elapsed_approved_leave_days_in_month(
    db: Session,
    employee_id: int,
    month: int,
    year: int,
    today: date | None = None,
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return 0

    today = today or date.today()
    total_days = monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, total_days)
    join_date = employee_join_date(employee)

    if today < month_start:
        return 0

    cutoff = min(today, month_end)
    leaves = db.query(Leave).filter(
        Leave.employee_id == employee_id,
        Leave.status == "approved",
    ).all()

    leave_days = 0
    for leave in leaves:
        current = max(leave.start_date, month_start, join_date)
        leave_end = min(leave.end_date, cutoff)

        while current <= leave_end:
            if current.weekday() != 6:
                leave_days += 1
            current += timedelta(days=1)

    return leave_days


def attendance_records_in_month(db: Session, employee_id: int, month: int, year: int):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    join_date = employee_join_date(employee) if employee else date(REPORT_START_YEAR, REPORT_START_MONTH, 1)

    return (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year,
            Attendance.date >= join_date,
        )
        .all()
    )


def attendance_total_hours(db: Session, record: Attendance, now: datetime | None = None):
    last = latest_punch(db, record.id)
    if last and last.punch_type == "in":
        return calculate_worked_time(db, record.id, now or datetime.now())
    return record.total_hours or timedelta()


def employee_monthly_summary(db: Session, employee_id: int, month: int, year: int):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee or not is_assignment_complete(employee):
        return {
            "has_data": False,
            "message": "Attendance starts after admin assigns role and shift",
            "working_days": 0,
            "approved_leave_days": 0,
            "effective_working_days": 0,
            "present_days": 0,
            "absent_days": 0,
            "extra_work_days": 0,
            "extra_work_hours": 0,
            "total_hours_worked": 0,
            "attendance_percentage": 0,
        }

    if (year, month) < (REPORT_START_YEAR, REPORT_START_MONTH):
        return {
            "has_data": False,
            "message": "No data available before May 2026",
            "working_days": 0,
            "approved_leave_days": 0,
            "effective_working_days": 0,
            "present_days": 0,
            "absent_days": 0,
            "extra_work_days": 0,
            "extra_work_hours": 0,
            "total_hours_worked": 0,
            "attendance_percentage": 0,
        }

    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    join_date = employee_join_date(employee)
    attendance_start = max(month_start, join_date)

    if month_end < join_date:
        return {
            "has_data": False,
            "message": "Employee had not joined in this month",
            "working_days": 0,
            "approved_leave_days": 0,
            "effective_working_days": 0,
            "present_days": 0,
            "absent_days": 0,
            "extra_work_days": 0,
            "extra_work_hours": 0,
            "total_hours_worked": 0,
            "attendance_percentage": 0,
        }

    working_days = working_days_between(attendance_start, month_end)
    attendance_records = attendance_records_in_month(db, employee_id, month, year)
    working_day_records = [record for record in attendance_records if is_working_day(record.date)]
    extra_work_records = [record for record in attendance_records if not is_working_day(record.date)]
    present_days = sum(
        attendance_day_credit(record, employee.shift)
        for record in working_day_records
    )
    extra_work_days = len(extra_work_records)
    leave_days = approved_leave_days_in_month(db, employee_id, month, year)
    effective_working_days = max(working_days - leave_days, 0)

    elapsed_end = min(date.today(), month_end)
    elapsed_working_days = working_days_between(attendance_start, elapsed_end)
    elapsed_leave_days = elapsed_approved_leave_days_in_month(db, employee_id, month, year)
    elapsed_present_days = sum(
        attendance_day_credit(record, employee.shift)
        for record in working_day_records
        if record.date <= date.today()
    )
    absent_days = max(elapsed_working_days - elapsed_leave_days - elapsed_present_days, 0)

    total_hours = sum(
        attendance_total_hours(db, record).total_seconds() / 3600
        for record in attendance_records
    )
    extra_work_hours = sum(
        attendance_total_hours(db, record).total_seconds() / 3600
        for record in extra_work_records
    )

    attendance_percentage = 0
    if effective_working_days > 0:
        attendance_percentage = round((present_days / effective_working_days) * 100, 2)

    return {
        "has_data": True,
        "message": None,
        "working_days": working_days,
        "approved_leave_days": leave_days,
        "effective_working_days": effective_working_days,
        "present_days": present_days,
        "absent_days": absent_days,
        "extra_work_days": extra_work_days,
        "extra_work_hours": round(extra_work_hours, 2),
        "total_hours_worked": round(total_hours, 2),
        "attendance_percentage": attendance_percentage,
    }
