from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Employee, Attendance
from deps import get_current_user
from schemas import ShiftUpdateSchema
from schemas import RoleUpdateSchema
from models import Leave
from datetime import date, timedelta
from sqlalchemy import extract
from calendar import monthrange


router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/employees")
def get_employees(current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    return db.query(Employee).all()

@router.delete("/employee/{id}")
def delete_employee(
    id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    emp = db.query(Employee).filter(Employee.id == id).first()

    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    
    if current_user.id == id:
        raise HTTPException(
            status_code=400,
            detail="Admin cannot delete their own account"
        )

    
    if emp.role == "admin":
        admin_count = db.query(Employee).filter(Employee.role == "admin").count()
        if admin_count == 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the only admin"
            )

    # 🧹 Delete attendance first
    db.query(Attendance).filter(Attendance.employee_id == id).delete()

    
    db.delete(emp)
    db.commit()

    return {"message": "Employee deleted successfully"}

@router.get("/attendance")
def all_attendance(db: Session = Depends(get_db)):
    return db.query(Attendance).all()


@router.put("/employee/{id}/shift")
def update_shift(
    id: int,
    shift_data: ShiftUpdateSchema,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    emp = db.query(Employee).filter(Employee.id == id).first()

    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if shift_data.shift not in ["morning", "night"]:
        raise HTTPException(status_code=400, detail="Invalid shift")

    emp.shift = shift_data.shift
    db.commit()

    return {"message": "Shift updated successfully"}

@router.put("/employee/{id}/role")
def update_role(
    id: int,
    role_data: RoleUpdateSchema,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only admin allowed
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    emp = db.query(Employee).filter(Employee.id == id).first()

    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if current_user.id == id and role_data.role != "admin":
        raise HTTPException(
        status_code=400,
        detail="Admin cannot remove their own admin role"
    )

    # validate role
    if role_data.role not in ["employee", "admin","developer"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    if role_data.role == "admin":
        existing_admin = db.query(Employee).filter(Employee.role == "admin").first()

        # remove old admin (if exists and not same user)
        if existing_admin and existing_admin.id != id:
            existing_admin.role = "employee"

    # assign new role
    emp.role = role_data.role
    db.commit()

    return {"message": "Role updated successfully"}

@router.get("/employee/{id}/leave-count")
def employee_leave_count(
    id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    approved_leaves = db.query(Leave).filter(
        Leave.employee_id == id,
        Leave.status == "approved"
    ).all()

    total_days = 0

    for leave in approved_leaves:
        days = (leave.end_date - leave.start_date).days + 1
        total_days += days

    return {
        "employee_id": id,
        "total_approved_leave_days": total_days
    }
    
@router.get("/dashboard")
def admin_dashboard(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    today = date.today()
    month = today.month
    year = today.year

    # 👥 Total Employees
    total_employees = db.query(Employee).count()

    # 🟢 Present Today (completed attendance)
    present_today = db.query(Attendance).filter(
        Attendance.date == today,
        Attendance.logout_time != None
    ).count()

    # 🟡 On Leave Today
    on_leave_today = db.query(Leave).filter(
        Leave.status == "approved",
        Leave.start_date <= today,
        Leave.end_date >= today
    ).count()

    # 🔴 Absent Today
    absent_today = total_employees - (present_today + on_leave_today)

    # 🗓 Pending Leave Requests
    pending_leaves = db.query(Leave).filter(
        Leave.status == "pending"
    ).count()

    # 📊 Monthly Attendance Summary
    monthly_attendance = db.query(Attendance).filter(
        extract("month", Attendance.date) == month,
        extract("year", Attendance.date) == year,
        Attendance.logout_time != None
    ).count()

    # 🕒 Monthly Working Hours (All Employees)
    monthly_records = db.query(Attendance).filter(
        extract("month", Attendance.date) == month,
        extract("year", Attendance.date) == year,
        Attendance.logout_time != None
    ).all()

    total_hours = 0
    for record in monthly_records:
        if record.total_hours:
            total_hours += record.total_hours.total_seconds() / 3600

    return {
        "date": str(today),
        "total_employees": total_employees,
        "present_today": present_today,
        "on_leave_today": on_leave_today,
        "absent_today": absent_today,
        "pending_leave_requests": pending_leaves,
        "monthly_attendance_records": monthly_attendance,
        "monthly_total_working_hours": round(total_hours, 2)
    }
    
@router.get("/monthly-attendance-report")
def monthly_attendance_report(
    month: int,
    year: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    employees = db.query(Employee).all()

    total_days = monthrange(year, month)[1]

    # 🔹 Calculate working days (exclude Sundays)
    working_days = 0
    for day in range(1, total_days + 1):
        d = date(year, month, day)
        if d.weekday() != 6:
            working_days += 1

    report = []

    for emp in employees:

        # Present Days
        attendance_records = db.query(Attendance).filter(
            Attendance.employee_id == emp.id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year,
            Attendance.logout_time != None
        ).all()

        present_days = len(attendance_records)

        # Approved Leave Days
        approved_leaves = db.query(Leave).filter(
            Leave.employee_id == emp.id,
            Leave.status == "approved"
        ).all()

        leave_days = 0
        for leave in approved_leaves:
            current = leave.start_date
            while current <= leave.end_date:
                if current.month == month and current.year == year and current.weekday() != 6:
                    leave_days += 1
                current += timedelta(days=1)

        effective_working_days = working_days - leave_days

        attendance_percentage = 0
        if effective_working_days > 0:
            attendance_percentage = round(
                (present_days / effective_working_days) * 100, 2
            )

        report.append({
            "employee_id": emp.id,
            "name": emp.name,
            "present_days": present_days,
            "approved_leave_days": leave_days,
            "effective_working_days": effective_working_days,
            "attendance_percentage": attendance_percentage
        })

    return {
        "month": month,
        "year": year,
        "total_employees": len(employees),
        "report": report
    }
    
@router.get("/low-attendance-warning")
def low_attendance_warning(
    month: int,
    year: int,
    threshold: float = 75.0,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    employees = db.query(Employee).all()
    total_days = monthrange(year, month)[1]

    # 🔹 Calculate working days (exclude Sundays)
    working_days = 0
    for day in range(1, total_days + 1):
        d = date(year, month, day)
        if d.weekday() != 6:
            working_days += 1

    warning_list = []

    for emp in employees:

        # Present Days
        attendance_records = db.query(Attendance).filter(
            Attendance.employee_id == emp.id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year,
            Attendance.logout_time != None
        ).all()

        present_days = len(attendance_records)

        # Approved Leave Days
        approved_leaves = db.query(Leave).filter(
            Leave.employee_id == emp.id,
            Leave.status == "approved"
        ).all()

        leave_days = 0
        for leave in approved_leaves:
            current = leave.start_date
            while current <= leave.end_date:
                if current.month == month and current.year == year and current.weekday() != 6:
                    leave_days += 1
                current += timedelta(days=1)

        effective_working_days = working_days - leave_days

        attendance_percentage = 0
        if effective_working_days > 0:
            attendance_percentage = round(
                (present_days / effective_working_days) * 100, 2
            )

        # 🚨 Only include employees below threshold
        if attendance_percentage < threshold:
            warning_list.append({
                "employee_id": emp.id,
                "name": emp.name,
                "attendance_percentage": attendance_percentage,
                "present_days": present_days,
                "effective_working_days": effective_working_days,
                "status": "Low Attendance Warning"
            })

    return {
        "month": month,
        "year": year,
        "threshold": threshold,
        "total_warnings": len(warning_list),
        "employees": warning_list
    }