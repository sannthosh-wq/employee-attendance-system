import os
from datetime import date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .attendance_logic import auto_close_stale_active_attendance, current_shift_date, employee_leave_balance, employee_monthly_summary, employee_today_status, employee_work_start_date, get_shift_window, internship_end_date, is_assignment_complete, is_working_day, mark_missed_shift_absent, working_leave_days
from .database import SessionLocal
from .deps import get_current_user
from .models import Attendance, Employee, Leave

router = APIRouter(prefix="/employee")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def mark_current_missed_shift(db: Session, employee):
    if auto_close_stale_active_attendance(db):
        db.commit()
    if not is_assignment_complete(employee):
        return False
    return mark_missed_shift_absent(db, employee, current_shift_date(employee.shift))


def punch_action_state(employee, status: str):
    if not is_assignment_complete(employee):
        return {"can_punch_in": False, "can_punch_out": False}

    now = datetime.now()
    _, shift_start, _, shift_end = get_shift_window(now, employee.shift)
    inside_shift = shift_start <= now <= shift_end

    return {
        "can_punch_in": inside_shift and status in ["Absent", "No Attendance", "Present"],
        "can_punch_out": status == "Working (Punched In)",
    }


@router.get("/dashboard")
def employee_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    if mark_current_missed_shift(db, current_user):
        db.commit()

    approved_leaves = db.query(Leave).filter(
        Leave.employee_id == current_user.id,
        Leave.status == "approved",
    ).all()
    total_leave_days = sum(
        working_leave_days(leave.start_date, leave.end_date)
        for leave in approved_leaves
    )

    joined_at = current_user.joined_at or date(2026, 1, 1)
    work_start_date = employee_work_start_date(current_user)
    attendance_query = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date >= work_start_date,
    )
    if end_date := internship_end_date(current_user):
        attendance_query = attendance_query.filter(Attendance.date <= end_date)
    attendance_records = attendance_query.all()
    total_attendance_days = sum(1 for record in attendance_records if is_working_day(record.date))

    today_status = employee_today_status(db, current_user, today)
    punch_actions = punch_action_state(current_user, today_status)

    return {
        "employee_id": current_user.id,
        "employee_code": current_user.employee_code,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "shift": current_user.shift,
        "employment_type": current_user.employment_type or "full_time",
        "profile_photo": current_user.profile_photo,
        "joined_at": joined_at,
        "work_start_date": work_start_date,
        "assigned_at": current_user.assigned_at,
        "is_assigned": bool(current_user.role and current_user.shift),
        "total_approved_leave_days": total_leave_days,
        "leave_balance": employee_leave_balance(db, current_user.id),
        "total_attendance_days": total_attendance_days,
        "today_status": today_status,
        **punch_actions,
    }


@router.post("/profile-photo")
def upload_profile_photo(
    photo: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if photo.content_type not in ["image/jpeg", "image/png", "image/webp", "image/gif"]:
        raise HTTPException(status_code=400, detail="Profile photo must be an image")

    extension = os.path.splitext(photo.filename or "")[1].lower()
    if extension not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        extension = ".jpg"

    os.makedirs("uploads/profile_photos", exist_ok=True)
    filename = f"{current_user.id}-{uuid4().hex}{extension}"
    path = os.path.join("uploads", "profile_photos", filename)

    with open(path, "wb") as output:
        output.write(photo.file.read())

    employee = db.query(Employee).filter(Employee.id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.profile_photo = f"/uploads/profile_photos/{filename}"
    db.commit()

    return {
        "message": "Profile photo uploaded successfully",
        "profile_photo": employee.profile_photo,
    }


@router.get("/monthly-summary")
def monthly_summary(
    month: int,
    year: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if mark_current_missed_shift(db, current_user):
        db.commit()

    return {
        "month": month,
        "year": year,
        **employee_monthly_summary(db, current_user.id, month, year),
    }
