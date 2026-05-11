from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract
from sqlalchemy.orm import Session

from attendance_logic import (
    VALID_ROLES,
    VALID_SHIFTS,
    attendance_total_hours,
    employee_monthly_summary,
    employee_shift_date_status,
    working_leave_days,
)
from database import SessionLocal
from deps import get_current_user
from models import Attendance, AttendancePunch, Employee, Leave
from schemas import RoleUpdateSchema, ShiftUpdateSchema

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(user):
    if user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")


def require_super_admin(user):
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")


def employee_payload(emp: Employee):
    return {
        "id": emp.id,
        "name": emp.name,
        "email": emp.email,
        "role": emp.role,
        "shift": emp.shift,
        "joined_at": emp.joined_at,
        "assigned_at": emp.assigned_at,
        "assignment_pending": not (emp.role and emp.shift),
    }


def mark_assigned_if_ready(emp: Employee):
    if emp.role and emp.shift and not emp.assigned_at:
        emp.assigned_at = datetime.utcnow()


def empty_shift_summary():
    return {
        "total": 0,
        "present_today": 0,
        "absent_today": 0,
        "on_leave_today": 0,
    }


def build_shift_summary(db: Session, target_date: date | None = None):
    target_date = target_date or date.today()
    summary = {
        "morning": empty_shift_summary(),
        "night": empty_shift_summary(),
    }

    for emp in db.query(Employee).filter(Employee.role != "super_admin", Employee.role.isnot(None), Employee.shift.isnot(None)).all():
        shift_key = emp.shift if emp.shift in summary else "morning"
        status = employee_shift_date_status(db, emp, target_date)

        summary[shift_key]["total"] += 1

        if status in ["Present", "Working (Punched In)"]:
            summary[shift_key]["present_today"] += 1
        elif status == "On Leave":
            summary[shift_key]["on_leave_today"] += 1
        elif status == "Absent":
            summary[shift_key]["absent_today"] += 1

    return summary


@router.get("/employees")
def get_employees(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    employees = db.query(Employee).order_by(Employee.id.asc()).all()
    return [employee_payload(emp) for emp in employees]


@router.get("/onboarding-notifications")
def onboarding_notifications(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    pending = (
        db.query(Employee)
        .filter(Employee.role.is_(None) | Employee.shift.is_(None))
        .order_by(Employee.joined_at.desc(), Employee.id.desc())
        .all()
    )

    return {
        "total": len(pending),
        "notifications": [
            {
                "employee_id": emp.id,
                "name": emp.name,
                "email": emp.email,
                "joined_at": emp.joined_at,
                "message": f"New employee {emp.name} joined. Assign role and shift.",
            }
            for emp in pending
        ],
    }


@router.delete("/employee/{id}")
def delete_employee(
    id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    emp = db.query(Employee).filter(Employee.id == id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if current_user.id == id:
        raise HTTPException(status_code=400, detail="Admin cannot delete their own account")

    if emp.role == "super_admin":
        raise HTTPException(status_code=400, detail="Super admin cannot be deleted")

    if emp.role == "admin" and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can delete admins")

    if emp.role in ["admin", "super_admin"]:
        admin_count = db.query(Employee).filter(Employee.role.in_(["admin", "super_admin"])).count()
        if admin_count == 1:
            raise HTTPException(status_code=400, detail="Cannot delete the only admin account")

    db.query(AttendancePunch).filter(AttendancePunch.employee_id == id).delete()
    db.query(Attendance).filter(Attendance.employee_id == id).delete()
    db.query(Leave).filter(Leave.employee_id == id).delete()
    db.delete(emp)
    db.commit()

    return {"message": "Employee deleted successfully"}


@router.get("/attendance")
def all_attendance(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    records = (
        db.query(Attendance, Employee)
        .join(Employee, Attendance.employee_id == Employee.id)
        .filter(Employee.role != "super_admin")
        .filter(Attendance.date >= Employee.joined_at)
        .order_by(Attendance.date.desc(), Attendance.login_time.desc())
        .all()
    )

    return [
        {
            "id": attendance.id,
            "employee_id": employee.id,
            "employee_name": employee.name,
            "email": employee.email,
            "role": employee.role,
            "shift": employee.shift,
            "joined_at": employee.joined_at,
            "date": attendance.date,
            "login_time": attendance.login_time,
            "logout_time": attendance.logout_time,
            "total_hours": str(attendance_total_hours(db, attendance)),
            "is_late": attendance.is_late,
            "left_early": attendance.left_early,
        }
        for attendance, employee in records
    ]


@router.get("/today-status")
def today_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    today = date.today()
    employees = db.query(Employee).order_by(Employee.id.asc()).all()

    return {
        "date": str(today),
        "employees": [
            {
                "employee_id": emp.id,
                "name": emp.name,
                "email": emp.email,
                "role": emp.role,
                "shift": emp.shift,
                "joined_at": emp.joined_at,
                "status": "No Attendance" if emp.role == "super_admin" else employee_shift_date_status(db, emp, today),
            }
            for emp in employees
        ],
    }


@router.get("/shift-summary")
def shift_summary(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    return {
        "date": str(date.today()),
        "shifts": build_shift_summary(db),
    }


@router.get("/daily-attendance-summary")
def daily_attendance_summary(
    selected_date: date,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    shift_totals = build_shift_summary(db, selected_date)
    present = sum(item["present_today"] for item in shift_totals.values())
    leave = sum(item["on_leave_today"] for item in shift_totals.values())
    absent = sum(item["absent_today"] for item in shift_totals.values())

    return {
        "date": str(selected_date),
        "total_employees": sum(item["total"] for item in shift_totals.values()),
        "present_today": present,
        "on_leave_today": leave,
        "absent_today": absent,
        "shifts": shift_totals,
    }


@router.put("/employee/{id}/shift")
def update_shift(
    id: int,
    shift_data: ShiftUpdateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    emp = db.query(Employee).filter(Employee.id == id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if shift_data.shift not in VALID_SHIFTS:
        raise HTTPException(status_code=400, detail="Invalid shift")

    if emp.role == "super_admin":
        raise HTTPException(status_code=400, detail="Super admin does not have a shift")

    if emp.role == "admin" and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can change admin shifts")

    emp.shift = shift_data.shift
    mark_assigned_if_ready(emp)
    db.commit()

    return {"message": "Shift updated successfully"}


@router.put("/employee/{id}/role")
def update_role(
    id: int,
    role_data: RoleUpdateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    emp = db.query(Employee).filter(Employee.id == id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if role_data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    if emp.role == "super_admin":
        raise HTTPException(status_code=400, detail="Super admin role cannot be changed")

    if role_data.role == "super_admin":
        require_super_admin(current_user)
        existing_super_admin = db.query(Employee).filter(Employee.role == "super_admin").first()
        if existing_super_admin and existing_super_admin.id != id:
            raise HTTPException(status_code=400, detail="Only one super admin is allowed")

    if current_user.role != "super_admin" and (emp.role == "admin" or role_data.role == "admin"):
        raise HTTPException(status_code=403, detail="Only super admin can change admin roles")

    if current_user.id == id and role_data.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=400, detail="Admin cannot remove their own admin role")

    if emp.role in ["admin", "super_admin"] and role_data.role not in ["admin", "super_admin"]:
        admin_count = db.query(Employee).filter(Employee.role.in_(["admin", "super_admin"])).count()
        if admin_count == 1:
            raise HTTPException(status_code=400, detail="Cannot remove the only admin account")

    emp.role = role_data.role
    if emp.role == "super_admin":
        emp.shift = None
    mark_assigned_if_ready(emp)
    db.commit()

    return {"message": "Role updated successfully"}


@router.get("/employee/{id}/leave-count")
def employee_leave_count(
    id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    employee = db.query(Employee).filter(Employee.id == id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    approved_leaves = db.query(Leave).filter(
        Leave.employee_id == id,
        Leave.status == "approved",
    ).all()
    total_days = sum(
        working_leave_days(leave.start_date, leave.end_date)
        for leave in approved_leaves
    )

    return {
        "employee_id": id,
        "total_approved_leave_days": total_days,
    }


@router.get("/dashboard")
def admin_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    today = date.today()
    shift_totals = build_shift_summary(db)
    present_today = sum(item["present_today"] for item in shift_totals.values())
    on_leave_today = sum(item["on_leave_today"] for item in shift_totals.values())
    absent_today = sum(item["absent_today"] for item in shift_totals.values())

    pending_leaves = db.query(Leave).filter(Leave.status == "pending").count()
    pending_assignments = db.query(Employee).filter(
        Employee.role.is_(None) | Employee.shift.is_(None)
    ).count()

    monthly_records = (
        db.query(Attendance)
        .join(Employee, Attendance.employee_id == Employee.id)
        .filter(
            Employee.role != "super_admin",
            Attendance.date >= Employee.joined_at,
            extract("month", Attendance.date) == today.month,
            extract("year", Attendance.date) == today.year,
        )
        .all()
    )
    total_hours = sum(
        attendance_total_hours(db, record).total_seconds() / 3600
        for record in monthly_records
    )

    return {
        "date": str(today),
        "total_employees": db.query(Employee).filter(Employee.role != "super_admin").count(),
        "present_today": present_today,
        "on_leave_today": on_leave_today,
        "absent_today": absent_today,
        "pending_leave_requests": pending_leaves,
        "pending_assignment_requests": pending_assignments,
        "monthly_attendance_records": len(monthly_records),
        "monthly_total_working_hours": round(total_hours, 2),
    }


@router.get("/monthly-attendance-report")
def monthly_attendance_report(
    month: int,
    year: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    employees = db.query(Employee).filter(Employee.role != "super_admin").order_by(Employee.id.asc()).all()
    report = []

    for emp in employees:
        summary = employee_monthly_summary(db, emp.id, month, year)
        report.append({
            "employee_id": emp.id,
            "name": emp.name,
            "joined_at": emp.joined_at,
            "present_days": summary["present_days"],
            "approved_leave_days": summary["approved_leave_days"],
            "effective_working_days": summary["effective_working_days"],
            "extra_work_days": summary["extra_work_days"],
            "extra_work_hours": summary["extra_work_hours"],
            "attendance_percentage": summary["attendance_percentage"],
        })

    return {
        "month": month,
        "year": year,
        "total_employees": len(employees),
        "report": report,
    }


@router.get("/low-attendance-warning")
def low_attendance_warning(
    month: int,
    year: int,
    threshold: float = 70.0,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    warning_list = []

    assigned_employees = (
        db.query(Employee)
        .filter(Employee.role != "super_admin", Employee.role.isnot(None), Employee.shift.isnot(None))
        .order_by(Employee.id.asc())
        .all()
    )

    for emp in assigned_employees:
        summary = employee_monthly_summary(db, emp.id, month, year)

        if summary["attendance_percentage"] < threshold:
            warning_list.append({
                "employee_id": emp.id,
                "name": emp.name,
                "attendance_percentage": summary["attendance_percentage"],
                "present_days": summary["present_days"],
                "extra_work_days": summary["extra_work_days"],
                "extra_work_hours": summary["extra_work_hours"],
                "effective_working_days": summary["effective_working_days"],
                "status": "Low Attendance Warning",
            })

    return {
        "month": month,
        "year": year,
        "threshold": threshold,
        "total_warnings": len(warning_list),
        "employees": warning_list,
    }
