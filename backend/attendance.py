from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Attendance, AttendancePunch
from datetime import date, datetime, timedelta
from deps import get_current_user
from schemas import AttendanceResponse
from attendance_logic import (
    active_attendance_for_punch_out,
    approved_leave_on,
    attendance_day_credit,
    attendance_total_hours,
    calculate_worked_time,
    employee_work_start_date,
    get_shift_attendance,
    get_shift_window,
    internship_end_date,
    is_internship_over,
    is_working_day,
    latest_punch,
    late_minutes,
    mark_missed_shift_absent,
    require_assignment_complete,
)

router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def attendance_history_status(record: Attendance | None, history_date: date, has_punches: bool = False) -> str:
    if not is_working_day(history_date) and not record:
        return "Holiday"

    if not record:
        return "No Attendance"

    if not is_working_day(history_date) and not has_punches:
        return "Holiday"

    if not is_working_day(history_date):
        return "Extra Work"

    return record.status or ("Present" if record.login_time else "No Attendance")


def attendance_history_row(db: Session, employee, history_date: date, record: Attendance | None):
    if not record:
        return {
            "date": history_date,
            "login_time": None,
            "logout_time": None,
            "total_hours": None,
            "status": attendance_history_status(None, history_date),
            "is_late": False,
            "late_minutes": 0,
            "left_early": False,
        }

    has_punches = bool(record.login_time or record.logout_time or record.total_hours or latest_punch(db, record.id))
    return {
        "date": record.date,
        "login_time": record.login_time,
        "logout_time": record.logout_time,
        "total_hours": str(attendance_total_hours(db, record)) if has_punches else None,
        "status": attendance_history_status(record, record.date, has_punches),
        "is_late": record.is_late,
        "late_minutes": late_minutes(record, employee.shift),
        "left_early": record.left_early,
    }


def require_attendance_user(user):
    if user.role == "super_admin":
        raise HTTPException(status_code=403, detail="Super admins do not use punch in or punch out")
    require_assignment_complete(user)
    if datetime.now().date() < employee_work_start_date(user):
        raise HTTPException(status_code=400, detail="Today only you have joined. Your work starts from tomorrow")
    if is_internship_over(user):
        raise HTTPException(status_code=403, detail="Your internship period is over so you cannot login")


@router.post("/punch-in")
def punch_in(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_attendance_user(current_user)

    now = datetime.now()
    shift_date, shift_start, grace_time, shift_end = get_shift_window(now, current_user.shift)

    if now < shift_start or now > shift_end:
        raise HTTPException(status_code=400, detail="Outside allowed shift hours")

    if approved_leave_on(db, current_user.id, shift_date):
        raise HTTPException(status_code=400, detail="Cannot punch in on approved leave")

    record = get_shift_attendance(db, current_user.id, shift_date)

    if not record:
        is_late = now > grace_time

        record = Attendance(
            employee_id=current_user.id,
            date=shift_date,
            login_time=now,
            logout_time=None,
            total_hours=timedelta(),
            is_late=is_late,
            left_early=False
        )
        db.add(record)
        db.flush()

        db.add(AttendancePunch(
            attendance_id=record.id,
            employee_id=current_user.id,
            punch_type="in",
            punch_time=now
        ))
        attendance_credit = attendance_day_credit(record, current_user.shift)
        half_day_deducted = attendance_credit == 0.5
        message = "Punch in successful"

        if half_day_deducted:
            message = "Punch in successful. Half day attendance is deducted because you punched in more than 3 hours after shift start"

        db.commit()

        return {
            "message": message,
            "is_late": is_late,
            "attendance_credit": attendance_credit,
            "half_day_deducted": half_day_deducted,
            "type": "attendance_start"
        }

    last_punch = latest_punch(db, record.id)

    if not record.login_time and record.status == "Absent":
        is_late = now > grace_time

        record.login_time = now
        record.logout_time = None
        record.total_hours = timedelta()
        record.status = "Present"
        record.is_late = is_late
        record.left_early = False
        record.late_minutes = 0
        record.early_minutes = 0
        record.working_hours = 0

        db.add(AttendancePunch(
            attendance_id=record.id,
            employee_id=current_user.id,
            punch_type="in",
            punch_time=now
        ))

        attendance_credit = attendance_day_credit(record, current_user.shift)
        half_day_deducted = attendance_credit == 0.5
        message = "Punch in successful"

        if half_day_deducted:
            message = "Punch in successful. Half day attendance is deducted because you punched in more than 3 hours after shift start"

        db.commit()

        return {
            "message": message,
            "is_late": is_late,
            "attendance_credit": attendance_credit,
            "half_day_deducted": half_day_deducted,
            "type": "attendance_start"
        }

    if last_punch and last_punch.punch_type == "in":
        raise HTTPException(status_code=400, detail="Already punched in")

    punch = AttendancePunch(
        attendance_id=record.id,
        employee_id=current_user.id,
        punch_type="in",
        punch_time=now
    )
    db.add(punch)
    db.flush()

    record.logout_time = None
    record.left_early = False
    record.total_hours = calculate_worked_time(db, record.id, now)

    db.commit()

    return {
        "message": "Break ended. Punch in recorded",
        "is_late": record.is_late,
        "type": "break_return"
    }


@router.post("/punch-out")
def punch_out(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_attendance_user(current_user)

    now = datetime.now()
    (
        record,
        shift_date,
        shift_start,
        grace_time,
        shift_end,
        last_punch,
    ) = active_attendance_for_punch_out(db, current_user.id, current_user.shift, now)

    if now < shift_start and not record:
        raise HTTPException(status_code=400, detail="Outside allowed shift hours")

    if not record:
        raise HTTPException(status_code=400, detail="No active attendance found")

    if not last_punch or last_punch.punch_type != "in":
        raise HTTPException(status_code=400, detail="No active session found")

    db.add(AttendancePunch(
        attendance_id=record.id,
        employee_id=current_user.id,
        punch_type="out",
        punch_time=now
    ))
    db.flush()

    record.logout_time = now
    record.total_hours = calculate_worked_time(db, record.id)
    record.left_early = now < shift_end

    db.commit()

    if now < shift_end:
        message = "Punch out recorded. It will be treated as logout unless you punch in again after a break"
    else:
        message = "Punch out successful. Shift logout recorded"

    return {
        "message": message,
        "left_early": record.left_early,
        "type": "punch_out" if now < shift_end else "shift_logout"
    }


@router.get("/my-attendance", response_model=list[AttendanceResponse])
def my_attendance(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    start_date = employee_work_start_date(current_user)
    end_date = date.today()
    if intern_end := internship_end_date(current_user):
        end_date = min(end_date, intern_end)

    if end_date < start_date:
        return []

    current = start_date
    created_absences = 0
    while current <= end_date:
        if mark_missed_shift_absent(db, current_user, current):
            created_absences += 1
        current += timedelta(days=1)

    if created_absences:
        db.commit()

    records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == current_user.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date,
        )
        .all()
    )
    records_by_date = {record.date: record for record in records}
    result = []
    current = end_date

    while current >= start_date:
        result.append(attendance_history_row(db, current_user, current, records_by_date.get(current)))
        current -= timedelta(days=1)

    return result
