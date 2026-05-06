from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Employee, Attendance, Leave
from deps import get_current_user
from datetime import date
from calendar import monthrange
from datetime import date
from sqlalchemy import extract

router = APIRouter(prefix="/employee")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/dashboard")
def employee_dashboard(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    today = date.today()

    # ✅ 1. Calculate total approved leave days
    approved_leaves = db.query(Leave).filter(
        Leave.employee_id == current_user.id,
        Leave.status == "approved"
    ).all()

    total_leave_days = 0
    for leave in approved_leaves:
        total_leave_days += (leave.end_date - leave.start_date).days + 1


    # ✅ 2. Count total attendance records
    total_attendance_days = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.logout_time != None
    ).count()


    # ✅ 3. Check today's status
    today_leave = db.query(Leave).filter(
        Leave.employee_id == current_user.id,
        Leave.status == "approved",
        Leave.start_date <= today,
        Leave.end_date >= today
    ).first()

    today_attendance = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today
    ).first()

    if today_leave:
        today_status = "On Leave"
    elif today_attendance and today_attendance.logout_time:
        today_status = "Present"
    elif today_attendance:
        today_status = "Working (Punched In)"
    else:
        today_status = "Not Marked"


    return {
        "employee_id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "shift": current_user.shift,
        "total_approved_leave_days": total_leave_days,
        "total_attendance_days": total_attendance_days,
        "today_status": today_status
    }
    
from calendar import monthrange
from datetime import date, timedelta
from sqlalchemy import extract

@router.get("/monthly-summary")
def monthly_summary(
    month: int,
    year: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    total_days = monthrange(year, month)[1]

    # 🔹 Calculate Working Days (Exclude Sundays)
    working_days = 0
    for day in range(1, total_days + 1):
        current_date = date(year, month, day)
        if current_date.weekday() != 6:  # 6 = Sunday
            working_days += 1

    # 🔹 Present Days
    attendance_records = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        extract("month", Attendance.date) == month,
        extract("year", Attendance.date) == year,
        Attendance.logout_time != None
    ).all()

    present_days = len(attendance_records)

    # 🔹 Approved Leave Days in that month
    approved_leaves = db.query(Leave).filter(
        Leave.employee_id == current_user.id,
        Leave.status == "approved"
    ).all()

    leave_days = 0
    for leave in approved_leaves:
        current = leave.start_date
        while current <= leave.end_date:
            if current.month == month and current.year == year and current.weekday() != 6:
                leave_days += 1
            current += timedelta(days=1)

    # 🔹 Total Hours
    total_hours = 0
    for record in attendance_records:
        if record.total_hours:
            total_hours += record.total_hours.total_seconds() / 3600

    # 🔹 Attendance Percentage
    effective_working_days = working_days - leave_days

    attendance_percentage = 0
    if effective_working_days > 0:
        attendance_percentage = round(
            (present_days / effective_working_days) * 100, 2
        )

    absent_days = effective_working_days - present_days

    return {
        "month": month,
        "year": year,
        "working_days": working_days,
        "approved_leave_days": leave_days,
        "effective_working_days": effective_working_days,
        "present_days": present_days,
        "absent_days": absent_days,
        "total_hours_worked": round(total_hours, 2),
        "attendance_percentage": attendance_percentage
    }