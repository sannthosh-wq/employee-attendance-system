from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Attendance
from datetime import datetime, date, time, timedelta
from deps import get_current_user
from schemas import AttendanceResponse

router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"]
)

# ---------------- DB SESSION ----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- HELPER ----------------
def is_within_shift(current_time, start, end):
    """
    Handles normal + overnight shift ranges
    (e.g., 21:00 to 06:00)
    """
    if start < end:
        return start <= current_time <= end
    return current_time >= start or current_time <= end


# ---------------- PUNCH IN ----------------
@router.post("/punch-in")
def punch_in(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    today = date.today()
    now = datetime.now()
    current_time = now.time()

    # prevent duplicate punch-in
    existing = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
        Attendance.logout_time == None
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Already punched in")

    # shift logic
    if current_user.shift == "morning":
        shift_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        start = time(9, 0)
        end = time(18, 0)

    elif current_user.shift == "night":
        shift_start = now.replace(hour=21, minute=0, second=0, microsecond=0)
        start = time(21, 0)
        end = time(6, 0)

    else:
        raise HTTPException(status_code=400, detail="Invalid shift")

    # validate shift window
    if not is_within_shift(current_time, start, end):
        raise HTTPException(
            status_code=400,
            detail="Outside allowed shift hours"
        )

    # grace period (15 min)
    grace_time = shift_start + timedelta(minutes=15)
    is_late = now > grace_time

    record = Attendance(
        employee_id=current_user.id,
        date=today,
        login_time=now,
        is_late=is_late
    )

    db.add(record)
    db.commit()

    return {
        "message": "Punch in successful",
        "is_late": is_late
    }


# ---------------- PUNCH OUT ----------------
@router.post("/punch-out")
def punch_out(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    today = date.today()

    record = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
        Attendance.logout_time == None
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="No active session found")

    now = datetime.now()
    record.logout_time = now
    record.total_hours = now - record.login_time

    # shift end logic
    if current_user.shift == "morning":
        shift_end = record.login_time.replace(
            hour=18, minute=0, second=0, microsecond=0
        )

    elif current_user.shift == "night":
        shift_end = (record.login_time + timedelta(days=1)).replace(
            hour=6, minute=0, second=0, microsecond=0
        )

    else:
        shift_end = now

    record.left_early = now < shift_end

    db.commit()

    return {
        "message": "Punch out successful",
        "left_early": record.left_early
    }


# ---------------- ATTENDANCE HISTORY ----------------
@router.get("/my-attendance", response_model=list[AttendanceResponse])
def my_attendance(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    records = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id
    ).all()

    result = []

    for record in records:

        result.append({
            "date": record.date,
            "login_time": record.login_time,
            "logout_time": record.logout_time,
            "total_hours": str(record.total_hours) if record.total_hours else None,
            "is_late": record.is_late,
            "left_early": record.left_early
        })

    return result