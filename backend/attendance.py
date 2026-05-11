from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Attendance, AttendancePunch
from datetime import datetime, timedelta
from deps import get_current_user
from schemas import AttendanceResponse
from attendance_logic import (
    approved_leave_on,
    attendance_day_credit,
    attendance_total_hours,
    calculate_worked_time,
    get_shift_attendance,
    get_shift_window,
    latest_punch,
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


def require_attendance_user(user):
    if user.role == "super_admin":
        raise HTTPException(status_code=403, detail="Super admins do not use punch in or punch out")
    require_assignment_complete(user)


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
    shift_date, shift_start, grace_time, shift_end = get_shift_window(now, current_user.shift)

    if now < shift_start:
        raise HTTPException(status_code=400, detail="Outside allowed shift hours")

    record = get_shift_attendance(db, current_user.id, shift_date)

    if not record:
        raise HTTPException(status_code=400, detail="No active attendance found")

    last_punch = latest_punch(db, record.id)

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
    records = (
        db.query(Attendance)
        .filter(Attendance.employee_id == current_user.id)
        .order_by(Attendance.date.desc(), Attendance.login_time.desc())
        .all()
    )

    result = []

    for record in records:
        result.append({
            "date": record.date,
            "login_time": record.login_time,
            "logout_time": record.logout_time,
            "total_hours": str(attendance_total_hours(db, record)) if record.total_hours or latest_punch(db, record.id) else None,
            "is_late": record.is_late,
            "left_early": record.left_early
        })

    return result
