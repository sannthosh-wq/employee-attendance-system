from calendar import monthrange
from datetime import date, datetime, time, timedelta
from math import ceil

from fastapi import HTTPException
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
VALID_EMPLOYMENT_TYPES = {"full_time", "intern", "contract"}
MIN_ATTENDANCE_PERCENTAGE = 70
REPORT_START_YEAR = 2026
REPORT_START_MONTH = 1
JOINED_TODAY_STATUS = "Joined Today - Work Starts Tomorrow"


def normalized_shift(shift: str | None):
    if shift == "day":
        return "morning"
    return shift


def night_shift_start_date(now: datetime):
    if now.time() <= NIGHT_SHIFT_POST_END_CUTOFF:
        return now.date() - timedelta(days=1)
    return now.date()


def get_shift_window_for_date(shift_date: date, shift: str):
    shift = normalized_shift(shift)

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
    shift = normalized_shift(shift)

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


def employee_work_start_date(employee):
    if getattr(employee, "role", None) in ["admin", "super_admin"]:
        return employee_join_date(employee)
    return employee_join_date(employee) + timedelta(days=1)


def add_months(start_date: date, months: int):
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def intern_period_dates(employee):
    if getattr(employee, "employment_type", None) != "intern":
        return None, None

    start_date = employee_join_date(employee) + timedelta(days=1)
    months = getattr(employee, "intern_months", None) or 0
    if not months:
        return start_date, None

    return start_date, add_months(start_date, months)


def internship_end_date(employee):
    _, end_date = intern_period_dates(employee)
    return end_date


def is_internship_over(employee, target_date: date | None = None):
    end_date = internship_end_date(employee)
    target_date = target_date or date.today()
    return bool(end_date and target_date > end_date)


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


def late_minutes(record: Attendance, shift: str):
    if not record.login_time or not shift:
        return 0

    _, grace_time, _ = get_shift_window_for_date(record.date, shift)
    if record.login_time <= grace_time:
        return 0

    return max(round((record.login_time - grace_time).total_seconds() / 60), 0)


def month_bounds(month: int, year: int):
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    return month_start, month_end


def leave_allowance(employee, month: int | None = None, year: int | None = None):
    today = date.today()
    month = month or today.month
    year = year or today.year
    month_start, month_end = month_bounds(month, year)
    attendance_start = max(month_start, employee_work_start_date(employee))

    if month_end < attendance_start:
        return 0

    working_days = working_days_between(attendance_start, month_end)
    minimum_attendance_days = ceil(working_days * (MIN_ATTENDANCE_PERCENTAGE / 100))
    return max(working_days - minimum_attendance_days, 0)


def leave_days_in_month_by_status(
    db: Session,
    employee_id: int,
    month: int,
    year: int,
    statuses: tuple[str, ...],
    exclude_leave_id: int | None = None,
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return 0

    month_start, month_end = month_bounds(month, year)
    join_date = employee_work_start_date(employee)
    query = db.query(Leave).filter(
        Leave.employee_id == employee_id,
        Leave.status.in_(statuses),
        Leave.start_date <= month_end,
        Leave.end_date >= month_start,
    )

    if exclude_leave_id is not None:
        query = query.filter(Leave.id != exclude_leave_id)

    leave_days = 0
    for leave in query.all():
        current = max(leave.start_date, month_start, join_date)
        leave_end = min(leave.end_date, month_end)

        while current <= leave_end:
            if current.weekday() != 6:
                leave_days += 1
            current += timedelta(days=1)

    return leave_days


def employee_leave_balance(
    db: Session,
    employee_id: int,
    month: int | None = None,
    year: int | None = None,
    exclude_leave_id: int | None = None,
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return {
            "month": month or date.today().month,
            "year": year or date.today().year,
            "minimum_attendance_percentage": MIN_ATTENDANCE_PERCENTAGE,
            "working_days": 0,
            "minimum_attendance_days": 0,
            "allowance": 0,
            "approved_days": 0,
            "pending_days": 0,
            "remaining_days": 0,
        }

    today = date.today()
    month = month or today.month
    year = year or today.year
    month_start, month_end = month_bounds(month, year)
    attendance_start = max(month_start, employee_work_start_date(employee))
    working_days = working_days_between(attendance_start, month_end) if month_end >= attendance_start else 0
    minimum_attendance_days = ceil(working_days * (MIN_ATTENDANCE_PERCENTAGE / 100))
    allowance = max(working_days - minimum_attendance_days, 0)
    approved_days = leave_days_in_month_by_status(
        db,
        employee_id,
        month,
        year,
        ("approved",),
        exclude_leave_id,
    )
    pending_days = leave_days_in_month_by_status(
        db,
        employee_id,
        month,
        year,
        ("pending",),
        exclude_leave_id,
    )

    return {
        "month": month,
        "year": year,
        "minimum_attendance_percentage": MIN_ATTENDANCE_PERCENTAGE,
        "working_days": working_days,
        "minimum_attendance_days": minimum_attendance_days,
        "allowance": allowance,
        "approved_days": approved_days,
        "pending_days": pending_days,
        "remaining_days": max(allowance - approved_days - pending_days, 0),
    }


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
    records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date == shift_date,
        )
        .all()
    )

    if not records:
        return None

    return max(
        records,
        key=lambda record: (
            bool(record.login_time or record.logout_time or record.total_hours),
            record.login_time or datetime.min,
            record.id or 0,
        ),
    )


def active_attendance_for_punch_out(
    db: Session,
    employee_id: int,
    shift: str,
    now: datetime,
):
    shift_date, shift_start, grace_time, shift_end = get_shift_window(now, shift)
    candidate_dates = [shift_date]

    if shift == "night" and now < shift_start:
        candidate_dates.insert(0, shift_date - timedelta(days=1))

    for candidate_date in candidate_dates:
        records = (
            db.query(Attendance)
            .filter(
                Attendance.employee_id == employee_id,
                Attendance.date == candidate_date,
            )
            .all()
        )

        for record in sorted(records, key=lambda item: item.id or 0, reverse=True):
            last_punch = latest_punch(db, record.id)
            if last_punch and last_punch.punch_type == "in":
                shift_start, grace_time, shift_end = get_shift_window_for_date(candidate_date, shift)
                return record, candidate_date, shift_start, grace_time, shift_end, last_punch

    return None, shift_date, shift_start, grace_time, shift_end, None


def auto_close_stale_active_attendance(db: Session, now: datetime | None = None):
    now = now or datetime.now()
    active_records = (
        db.query(Attendance, Employee)
        .join(Employee, Attendance.employee_id == Employee.id)
        .filter(
            Attendance.login_time.isnot(None),
            Attendance.logout_time.is_(None),
            Employee.shift.isnot(None),
        )
        .all()
    )
    closed = 0

    for record, employee in active_records:
        last_punch = latest_punch(db, record.id)
        if not last_punch or last_punch.punch_type != "in":
            continue

        shift = normalized_shift(employee.shift)
        if shift not in VALID_SHIFTS:
            continue

        try:
            _, _, shift_end = get_shift_window_for_date(record.date, shift)
            next_shift_start, _, _ = get_shift_window_for_date(record.date + timedelta(days=1), shift)
        except HTTPException:
            continue

        if now < next_shift_start:
            continue

        logout_time = max(shift_end, last_punch.punch_time)
        db.add(AttendancePunch(
            attendance_id=record.id,
            employee_id=record.employee_id,
            punch_type="out",
            punch_time=logout_time,
        ))
        db.flush()

        record.logout_time = logout_time
        record.total_hours = calculate_worked_time(db, record.id)
        record.left_early = False
        closed += 1

    return closed


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


def should_mark_missed_shift_absent(
    db: Session,
    employee,
    target_date: date,
    now: datetime | None = None,
):
    now = now or datetime.now()

    if not is_assignment_complete(employee):
        return False

    if is_internship_over(employee, target_date):
        return False

    if target_date < employee_work_start_date(employee):
        return False

    if not is_working_day(target_date):
        return False

    shift_start, _, _ = get_shift_window_for_date(target_date, employee.shift)
    if now < shift_start:
        return False

    if approved_leave_on(db, employee.id, target_date):
        return False

    return get_shift_attendance(db, employee.id, target_date) is None


def mark_missed_shift_absent(
    db: Session,
    employee,
    target_date: date,
    now: datetime | None = None,
):
    if not should_mark_missed_shift_absent(db, employee, target_date, now):
        return None

    record = Attendance(
        employee_id=employee.id,
        date=target_date,
        login_time=None,
        logout_time=None,
        total_hours=timedelta(),
        status="Absent",
        is_late=False,
        left_early=False,
        late_minutes=0,
        early_minutes=0,
        working_hours=0,
    )
    db.add(record)
    db.flush()
    return record


def mark_missed_shifts_absent(
    db: Session,
    employees,
    target_date: date,
    now: datetime | None = None,
):
    created = 0
    for employee in employees:
        if mark_missed_shift_absent(db, employee, target_date, now):
            created += 1
    return created


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
    today = today or date.today()
    if today < employee_work_start_date(employee):
        return JOINED_TODAY_STATUS

    if not is_assignment_complete(employee):
        return "Pending Assignment"

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
    now = now or datetime.now()
    if is_internship_over(employee, target_date):
        return "Internship Over"

    work_start = employee_work_start_date(employee)
    attendance = get_shift_attendance(db, employee.id, target_date)

    if target_date < work_start:
        if attendance:
            if not is_working_day(target_date):
                return "Extra Work"
            if attendance.status == "Leave":
                return "On Leave"
            if attendance.status == "Absent" and not attendance.login_time:
                return "Absent"
            if attendance.login_time:
                return "Present"
        if target_date == employee_join_date(employee):
            return JOINED_TODAY_STATUS
        return "Pending Assignment"

    if not is_assignment_complete(employee):
        return "Pending Assignment"

    if emp_joined := employee.joined_at:
        if target_date < emp_joined:
            return "Pending Assignment"

    if target_date > now.date():
        return "Shift Not Started"

    shift_start, _, shift_end = get_shift_window_for_date(target_date, employee.shift)

    if approved_leave_on(db, employee.id, target_date):
        return "On Leave"

    if attendance:
        if not is_working_day(target_date):
            return "Extra Work"

        if attendance.status == "Leave":
            return "On Leave"
        if attendance.status == "Absent" and not attendance.login_time:
            return "Absent"

        last_punch = latest_punch(db, attendance.id)
        if last_punch and last_punch.punch_type == "in":
            return "Working (Punched In)"
        if attendance.login_time:
            return "Present"

    if target_date == now.date():
        if now < shift_start:
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

    month_start, month_end = month_bounds(month, year)
    if end_date := internship_end_date(employee):
        month_end = min(month_end, end_date)
        if month_end < month_start:
            return 0

    join_date = reporting_start_date(db, employee, month_start, month_end)
    leaves = db.query(Leave).filter(
        Leave.employee_id == employee_id,
        Leave.status == "approved",
    ).all()

    leave_days = 0
    for leave in leaves:
        current = max(leave.start_date, join_date)
        leave_end = min(leave.end_date, month_end)

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
    if end_date := internship_end_date(employee):
        month_end = min(month_end, end_date)
        if month_end < month_start:
            return 0

    join_date = reporting_start_date(db, employee, month_start, month_end)

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


def attendance_records_between(db: Session, employee_id: int, start_date: date, end_date: date):
    return (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date >= start_date,
            Attendance.date <= end_date,
        )
        .all()
    )


def first_attendance_date_between(db: Session, employee_id: int, start_date: date, end_date: date):
    row = (
        db.query(Attendance.date)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date >= start_date,
            Attendance.date <= end_date,
        )
        .order_by(Attendance.date.asc())
        .first()
    )

    return row[0] if row else None


def reporting_start_date(db: Session, employee, start_date: date, end_date: date):
    work_start = employee_work_start_date(employee)
    first_attendance = first_attendance_date_between(db, employee.id, start_date, end_date)

    if first_attendance and first_attendance < work_start:
        work_start = first_attendance

    return max(start_date, work_start)


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
            "message": "No data available before January 2026",
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
    if end_date := internship_end_date(employee):
        month_end = min(month_end, end_date)
        if month_end < month_start:
            return {
                "has_data": False,
                "message": "Internship period is over",
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

    join_date = reporting_start_date(db, employee, month_start, month_end)
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
    leave_days = approved_leave_days_in_month(db, employee_id, month, year)
    effective_working_days = max(working_days - leave_days, 0)

    today = date.today()
    summary_end = min(today, month_end)
    if summary_end < attendance_start:
        summary_records = []
        elapsed_working_days = 0
    else:
        summary_records = attendance_records_between(db, employee_id, attendance_start, summary_end)
        elapsed_working_days = working_days_between(attendance_start, summary_end)

    working_day_records = [record for record in summary_records if is_working_day(record.date)]
    extra_work_records = [record for record in summary_records if not is_working_day(record.date)]
    present_days = sum(
        attendance_day_credit(record, employee.shift)
        for record in working_day_records
    )
    extra_work_days = len(extra_work_records)
    elapsed_leave_days = elapsed_approved_leave_days_in_month(db, employee_id, month, year)
    elapsed_effective_working_days = max(elapsed_working_days - elapsed_leave_days, 0)
    elapsed_present_days = sum(
        attendance_day_credit(record, employee.shift)
        for record in working_day_records
    )
    absent_days = max(elapsed_working_days - elapsed_leave_days - elapsed_present_days, 0)

    total_hours = sum(
        attendance_total_hours(db, record).total_seconds() / 3600
        for record in summary_records
    )
    extra_work_hours = sum(
        attendance_total_hours(db, record).total_seconds() / 3600
        for record in extra_work_records
    )

    attendance_percentage = 0
    if elapsed_effective_working_days > 0:
        attendance_percentage = round((present_days / elapsed_effective_working_days) * 100, 2)

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
