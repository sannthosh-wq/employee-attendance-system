from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from attendance_logic import employee_monthly_summary, employee_shift_date_status, is_working_day, working_leave_days
from database import SessionLocal
from deps import get_current_user
from models import Attendance, Leave

router = APIRouter(prefix="/employee")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/dashboard")
def employee_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()

    approved_leaves = db.query(Leave).filter(
        Leave.employee_id == current_user.id,
        Leave.status == "approved",
    ).all()
    total_leave_days = sum(
        working_leave_days(leave.start_date, leave.end_date)
        for leave in approved_leaves
    )

    joined_at = current_user.joined_at or date(2026, 5, 1)
    attendance_records = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date >= joined_at,
    ).all()
    total_attendance_days = sum(1 for record in attendance_records if is_working_day(record.date))

    today_status = employee_shift_date_status(db, current_user, today)
    if today_status == "Absent":
        today_status = "Not Marked"

    return {
        "employee_id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "shift": current_user.shift,
        "joined_at": joined_at,
        "assigned_at": current_user.assigned_at,
        "is_assigned": bool(current_user.role and current_user.shift),
        "total_approved_leave_days": total_leave_days,
        "total_attendance_days": total_attendance_days,
        "today_status": today_status,
    }


@router.get("/monthly-summary")
def monthly_summary(
    month: int,
    year: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "month": month,
        "year": year,
        **employee_monthly_summary(db, current_user.id, month, year),
    }
