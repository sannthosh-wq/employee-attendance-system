from calendar import monthrange
from datetime import date, datetime, timedelta
from html import escape

import os
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from .attendance_logic import (
    VALID_ROLES,
    VALID_EMPLOYMENT_TYPES,
    VALID_SHIFTS,
    approved_leave_on,
    attendance_day_credit,
    attendance_total_hours,
    auto_close_stale_active_attendance,
    employee_leave_balance,
    employee_monthly_summary,
    employee_shift_date_status,
    intern_period_dates,
    internship_end_date,
    is_working_day,
    late_minutes,
    mark_missed_shifts_absent,
    normalized_shift,
    reporting_start_date,
    working_leave_days,
)
from .database import SessionLocal
from .deps import get_current_user
from .models import Announcement, Attendance, AttendancePunch, Employee, Leave
from .notifications import notify_all_employees
from .schemas import AnnouncementCreateSchema, AnnouncementUpdateSchema, EmploymentTypeUpdateSchema, RoleUpdateSchema, ShiftUpdateSchema

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
        "employee_code": emp.employee_code,
        "name": emp.name,
        "email": emp.email,
        "role": emp.role,
        "shift": normalized_shift(emp.shift),
        "employment_type": emp.employment_type or "full_time",
        "intern_months": emp.intern_months,
        "profile_photo": emp.profile_photo,
        "joined_at": emp.joined_at,
        "assigned_at": emp.assigned_at,
        "assignment_pending": not (emp.role and emp.shift),
    }


def announcement_payload(item: Announcement):
    return {
        "id": item.id,
        "title": item.title,
        "message": item.message,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def save_profile_photo(photo: UploadFile, employee_id: int) -> str:
    if photo.content_type not in ["image/jpeg", "image/png", "image/webp", "image/gif"]:
        raise HTTPException(status_code=400, detail="Profile photo must be an image")

    extension = os.path.splitext(photo.filename or "")[1].lower()
    if extension not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        extension = ".jpg"

    os.makedirs("uploads/profile_photos", exist_ok=True)
    filename = f"{employee_id}-{uuid4().hex}{extension}"
    path = os.path.join("uploads", "profile_photos", filename)

    with open(path, "wb") as output:
        output.write(photo.file.read())

    return f"/uploads/profile_photos/{filename}"


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
    employees = db.query(Employee).filter(Employee.role != "super_admin", Employee.role.isnot(None), Employee.shift.isnot(None)).all()
    employees = [emp for emp in employees if include_employee_in_running_month(emp, target_date.month, target_date.year)]
    if mark_missed_shifts_absent(db, employees, target_date):
        db.commit()

    summary = {
        "morning": empty_shift_summary(),
        "night": empty_shift_summary(),
    }

    for emp in employees:
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


COMPANY_NAME = "Employee Attendance System"


def include_employee_in_running_month(employee: Employee, month: int, year: int):
    today = date.today()
    if employee.employment_type != "intern":
        return True

    end_date = internship_end_date(employee)
    if not end_date:
        return True

    month_start = date(year, month, 1)
    if month_start >= end_date:
        return False

    if (year, month) == (today.year, today.month) and today >= end_date:
        return False

    return True


def excel_response(headers, rows, filename: str, title: str = "Attendance Report", subtitle: str = ""):
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    column_count = len(headers)
    visible_subtitle = subtitle or "Official company attendance and workforce report"
    html = [
        "<html><head><meta charset='utf-8'><style>",
        "body{font-family:Calibri,Arial,sans-serif;color:#172033;background:#ffffff}",
        "table{border-collapse:collapse;width:100%}",
        "td,th{border:1px solid #b8c4d6;padding:8px;mso-number-format:'\\@';vertical-align:middle}",
        ".company{background:#0f172a;color:#fff;font-size:22px;font-weight:bold;border-color:#0f172a;padding:14px}",
        ".report{background:#0b7a75;color:#fff;font-size:16px;font-weight:bold;border-color:#0b7a75;padding:10px}",
        ".meta-label{background:#e8eef5;color:#334155;font-weight:bold;width:170px}",
        ".meta-value{background:#f8fafc;color:#172033;font-weight:bold}",
        ".confidential{background:#fff7ed;color:#9a3412;font-weight:bold}",
        ".spacer{height:12px;background:#ffffff;border-left-color:#ffffff;border-right-color:#ffffff}",
        ".header{background:#26364f;color:#fff;font-weight:bold;text-align:center}",
        ".row-alt{background:#f8fafc}",
        ".success{background:#dcfce7;color:#166534;font-weight:bold}",
        ".warning{background:#fef3c7;color:#92400e;font-weight:bold}",
        ".danger{background:#fee2e2;color:#991b1b;font-weight:bold}",
        ".neutral{background:#f1f5f9;color:#334155;font-weight:bold}",
        ".footer{background:#eef2f7;color:#475569;font-size:11px;font-style:italic}",
        "</style></head><body><table>",
        f"<tr><td class='company' colspan='{column_count}'>{escape(COMPANY_NAME)} - Official Company Report</td></tr>",
        f"<tr><td class='report' colspan='{column_count}'>{escape(title)}</td></tr>",
        f"<tr><td class='meta-label'>Report Description</td><td class='meta-value' colspan='{max(column_count - 1, 1)}'>{escape(visible_subtitle)}</td></tr>",
        f"<tr><td class='meta-label'>Generated At</td><td class='meta-value' colspan='{max(column_count - 1, 1)}'>{escape(generated_at)}</td></tr>",
        f"<tr><td class='meta-label'>Prepared By</td><td class='meta-value' colspan='{max(column_count - 1, 1)}'>HR Operations / Admin Console</td></tr>",
        f"<tr><td class='confidential' colspan='{column_count}'>Confidential: For internal company use only. Do not distribute outside authorized HR and management channels.</td></tr>",
        f"<tr><td class='spacer' colspan='{column_count}'></td></tr>",
        "<tr>" + "".join(f"<th class='header'>{escape(str(header))}</th>" for header in headers) + "</tr>",
    ]

    for index, row in enumerate(rows):
        cells = []
        for value in row:
            text = str(value if value is not None else "")
            css_classes = ["row-alt"] if index % 2 else []
            if text in {"Present", "Working (Punched In)", "Yes"}:
                css_classes.append("success")
            elif text in {"Leave", "On Leave"}:
                css_classes.append("warning")
            elif text in {"Absent", "No"}:
                css_classes.append("danger")
            elif text in {"No Attendance", "Holiday", "Shift Not Started", "Pending Assignment"}:
                css_classes.append("neutral")
            css_class = f" class='{' '.join(css_classes)}'" if css_classes else ""
            cells.append(f"<td{css_class}>{escape(text)}</td>")
        html.append("<tr>" + "".join(cells) + "</tr>")

    html.extend([
        f"<tr><td class='spacer' colspan='{column_count}'></td></tr>",
        f"<tr><td class='footer' colspan='{column_count}'>{escape(COMPANY_NAME)} | Generated by Employee Management System | Company confidential</td></tr>",
        "</table></body></html>",
    ])
    stream = iter(["".join(html).encode("utf-8")])

    return StreamingResponse(
        stream,
        media_type="application/vnd.ms-excel",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def attendance_record_for_date(db: Session, employee_id: int, target_date: date):
    return (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date == target_date,
        )
        .first()
    )


def employee_period_attendance_summary(db: Session, employee: Employee, start_date: date, end_date: date):
    if intern_end := internship_end_date(employee):
        end_date = min(end_date, intern_end)

    attendance_start = reporting_start_date(db, employee, start_date, end_date)

    if end_date < attendance_start:
        return {
            "working_days": 0,
            "present_days": 0,
            "approved_leave_days": 0,
            "absent_days": 0,
            "extra_work_days": 0,
            "extra_work_hours": 0,
            "total_hours": 0,
            "late_count": 0,
            "early_count": 0,
            "attendance_percentage": 0,
        }

    records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.date >= attendance_start,
            Attendance.date <= end_date,
        )
        .all()
    )
    working_records = [record for record in records if is_working_day(record.date)]
    extra_records = [record for record in records if not is_working_day(record.date)]
    present_days = sum(
        attendance_day_credit(record, employee.shift)
        for record in working_records
        if employee.shift
    )

    leave_days = 0
    current = attendance_start
    while current <= end_date:
        if is_working_day(current) and approved_leave_on(db, employee.id, current):
            leave_days += 1
        current += timedelta(days=1)

    working_days = sum(
        1
        for offset in range((end_date - attendance_start).days + 1)
        if is_working_day(attendance_start + timedelta(days=offset))
    )
    effective_working_days = max(working_days - leave_days, 0)
    absent_days = max(effective_working_days - present_days, 0)
    total_hours = sum(attendance_total_hours(db, record).total_seconds() / 3600 for record in records)
    extra_hours = sum(attendance_total_hours(db, record).total_seconds() / 3600 for record in extra_records)
    attendance_percentage = round((present_days / effective_working_days) * 100, 2) if effective_working_days else 0

    return {
        "working_days": working_days,
        "present_days": present_days,
        "approved_leave_days": leave_days,
        "absent_days": absent_days,
        "extra_work_days": len(extra_records),
        "extra_work_hours": round(extra_hours, 2),
        "total_hours": round(total_hours, 2),
        "late_count": sum(1 for record in working_records if record.is_late),
        "early_count": sum(1 for record in working_records if record.left_early and record.logout_time),
        "attendance_percentage": attendance_percentage,
    }


def parse_week_input(week: str):
    try:
        year_text, week_text = week.split("-W", 1)
        week_start = date.fromisocalendar(int(year_text), int(week_text), 1)
    except (AttributeError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Week must use YYYY-Www format")

    return week_start, week_start + timedelta(days=6)


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
    month: int | None = None,
    year: int | None = None,
    shift: str = "all",
    role: str = "all",
    employee_id: int | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    if auto_close_stale_active_attendance(db):
        db.commit()

    query = (
        db.query(Attendance, Employee)
        .join(Employee, Attendance.employee_id == Employee.id)
        .filter(
            Employee.role != "super_admin",
            Attendance.date <= date.today(),
        )
    )

    if month:
        query = query.filter(extract("month", Attendance.date) == month)
    if year:
        query = query.filter(extract("year", Attendance.date) == year)
    if shift != "all":
        if shift == "morning":
            query = query.filter(Employee.shift.in_(["morning", "day"]))
        else:
            query = query.filter(Employee.shift == shift)
    if role != "all":
        query = query.filter(Employee.role == role)
    if employee_id:
        query = query.filter(Employee.id == employee_id)

    records = query.order_by(Attendance.date.desc(), Attendance.login_time.desc(), Attendance.id.desc()).all()
    unique_records = {}

    for attendance, employee in records:
        key = (employee.id, attendance.date)
        existing = unique_records.get(key)

        if not existing:
            unique_records[key] = (attendance, employee)
            continue

        existing_attendance, _ = existing
        current_has_punch = bool(attendance.login_time or attendance.logout_time)
        existing_has_punch = bool(existing_attendance.login_time or existing_attendance.logout_time)

        if current_has_punch and not existing_has_punch:
            unique_records[key] = (attendance, employee)
        elif current_has_punch == existing_has_punch and attendance.id > existing_attendance.id:
            unique_records[key] = (attendance, employee)

    rows_by_day = {}

    for attendance, employee in unique_records.values():
        rows_by_day[(employee.id, attendance.date)] = {
            "id": attendance.id,
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "employee_name": employee.name,
            "email": employee.email,
            "role": employee.role,
            "shift": normalized_shift(employee.shift),
            "employment_type": employee.employment_type,
            "joined_at": employee.joined_at,
            "date": attendance.date,
            "login_time": attendance.login_time,
            "logout_time": attendance.logout_time,
            "total_hours": str(attendance_total_hours(db, attendance))
            if attendance.login_time and not attendance.logout_time
            else str(attendance.total_hours or timedelta()),
            "status": attendance.status,
            "is_late": attendance.is_late,
            "late_minutes": late_minutes(attendance, employee.shift),
            "left_early": attendance.left_early,
        }

    leave_query = (
        db.query(Leave, Employee)
        .join(Employee, Leave.employee_id == Employee.id)
        .filter(
            Employee.role != "super_admin",
            Leave.status == "approved",
        )
    )

    if shift != "all":
        if shift == "morning":
            leave_query = leave_query.filter(Employee.shift.in_(["morning", "day"]))
        else:
            leave_query = leave_query.filter(Employee.shift == shift)
    if role != "all":
        leave_query = leave_query.filter(Employee.role == role)
    if employee_id:
        leave_query = leave_query.filter(Employee.id == employee_id)

    leave_rows = leave_query.all()
    for leave, employee in leave_rows:
        current = leave.start_date
        while current <= leave.end_date:
            if (
                is_working_day(current)
                and current <= date.today()
                and (not month or current.month == month)
                and (not year or current.year == year)
            ):
                key = (employee.id, current)
                existing = rows_by_day.get(key)
                existing_has_punch = bool(existing and (existing["login_time"] or existing["logout_time"]))

                if not existing_has_punch:
                    rows_by_day[key] = {
                        "id": f"leave-{leave.id}-{current.isoformat()}",
                        "employee_id": employee.id,
                        "employee_code": employee.employee_code,
                        "employee_name": employee.name,
                        "email": employee.email,
                        "role": employee.role,
                        "shift": normalized_shift(employee.shift),
                        "employment_type": employee.employment_type,
                        "joined_at": employee.joined_at,
                        "date": current,
                        "login_time": None,
                        "logout_time": None,
                        "total_hours": "0:00:00",
                        "status": "On Leave",
                        "is_late": False,
                        "late_minutes": 0,
                        "left_early": False,
                    }
            current += timedelta(days=1)

    return sorted(
        rows_by_day.values(),
        key=lambda item: (item["date"], item["login_time"] or datetime.min),
        reverse=True,
    )


@router.get("/today-status")
def today_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    if auto_close_stale_active_attendance(db):
        db.commit()

    today = date.today()
    employees = db.query(Employee).order_by(Employee.id.asc()).all()
    eligible_employees = [emp for emp in employees if emp.role != "super_admin"]
    if mark_missed_shifts_absent(db, eligible_employees, today):
        db.commit()

    return {
        "date": str(today),
        "employees": [
            {
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "name": emp.name,
                "email": emp.email,
                "role": emp.role,
                "shift": emp.shift,
                "employment_type": emp.employment_type,
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

    emp.shift = shift_data.shift
    mark_assigned_if_ready(emp)
    db.commit()

    return {"message": "Shift updated successfully"}


@router.put("/employee/{id}/employment-type")
def update_employment_type(
    id: int,
    employment_data: EmploymentTypeUpdateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    emp = db.query(Employee).filter(Employee.id == id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if employment_data.employment_type not in VALID_EMPLOYMENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid employment type")

    emp.employment_type = employment_data.employment_type
    emp.intern_months = employment_data.intern_months if employment_data.employment_type == "intern" else None
    db.commit()

    return {"message": "Employment type updated successfully"}


@router.post("/employee/{id}/profile-photo")
def upload_employee_profile_photo(
    id: int,
    photo: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    emp = db.query(Employee).filter(Employee.id == id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    emp.profile_photo = save_profile_photo(photo, emp.id)
    db.commit()

    return {
        "message": "Profile photo uploaded successfully",
        "employee": employee_payload(emp),
        "profile_photo": emp.profile_photo,
    }


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
        existing_super_admin = db.query(Employee).filter(Employee.role == "super_admin").first()
        if existing_super_admin and existing_super_admin.id != id:
            raise HTTPException(status_code=400, detail="Only one super admin is allowed")

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
        **employee_leave_balance(db, id),
    }


@router.post("/announcements")
def create_announcement(
    announcement: AnnouncementCreateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    if not announcement.title.strip() or not announcement.message.strip():
        raise HTTPException(status_code=400, detail="Title and message are required")

    item = Announcement(
        title=announcement.title.strip(),
        message=announcement.message.strip(),
        created_by=current_user.id,
    )
    db.add(item)
    db.flush()

    notify_all_employees(
        db,
        item.title,
        item.message,
        "announcement",
        current_user.id,
    )
    db.commit()
    db.refresh(item)

    return {"message": "Announcement sent to all employees", "announcement": announcement_payload(item)}


@router.get("/announcements")
def list_announcements(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    rows = (
        db.query(Announcement)
        .filter(Announcement.deleted_at.is_(None))
        .order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .all()
    )
    return [announcement_payload(item) for item in rows]


@router.put("/announcements/{announcement_id}")
def update_announcement(
    announcement_id: int,
    announcement: AnnouncementUpdateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    item = db.query(Announcement).filter(
        Announcement.id == announcement_id,
        Announcement.deleted_at.is_(None),
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if not announcement.title.strip() or not announcement.message.strip():
        raise HTTPException(status_code=400, detail="Title and message are required")

    item.title = announcement.title.strip()
    item.message = announcement.message.strip()
    item.updated_at = datetime.utcnow()
    notify_all_employees(
        db,
        f"Updated: {item.title}",
        item.message,
        "announcement",
        current_user.id,
    )
    db.commit()
    db.refresh(item)

    return {"message": "Announcement updated", "announcement": announcement_payload(item)}


@router.delete("/announcements/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    item = db.query(Announcement).filter(
        Announcement.id == announcement_id,
        Announcement.deleted_at.is_(None),
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Announcement not found")

    item.deleted_at = datetime.utcnow()
    db.commit()

    return {"message": "Announcement deleted"}


@router.get("/employee-growth")
def employee_growth(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    today = date.today()
    non_super_admin = (Employee.role.is_(None)) | (Employee.role != "super_admin")
    joined_employees = (
        db.query(Employee)
        .filter(non_super_admin)
        .order_by(Employee.joined_at.asc(), Employee.id.asc())
        .all()
    )
    type_rows = (
        db.query(Employee.employment_type, func.count(Employee.id))
        .filter(non_super_admin)
        .group_by(Employee.employment_type)
        .all()
    )
    monthly_growth = {}
    for employee in joined_employees:
        joined_at = employee.joined_at or date(2026, 1, 1)
        key = joined_at.strftime("%Y-%m")
        monthly_growth.setdefault(key, []).append({
            "id": employee.id,
            "employee_code": employee.employee_code,
            "name": employee.name,
            "email": employee.email,
            "role": employee.role,
            "shift": normalized_shift(employee.shift),
            "employment_type": employee.employment_type or "full_time",
            "joined_at": joined_at,
        })

    return {
        "total_employees": len(joined_employees),
        "joined_this_month": db.query(Employee).filter(
            non_super_admin,
            extract("month", Employee.joined_at) == today.month,
            extract("year", Employee.joined_at) == today.year,
        ).count(),
        "by_employment_type": {
            (employment_type or "full_time"): count
            for employment_type, count in type_rows
        },
        "monthly": [
            {
                "month": month,
                "count": len(employees),
                "employees": employees,
            }
            for month, employees in monthly_growth.items()
        ],
    }


@router.get("/dashboard")
def admin_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    if auto_close_stale_active_attendance(db):
        db.commit()

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
    employee_id: int | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    employees_query = db.query(Employee).filter(Employee.role != "super_admin")
    if employee_id:
        employees_query = employees_query.filter(Employee.id == employee_id)

    employees = [
        emp for emp in employees_query.order_by(Employee.id.asc()).all()
        if include_employee_in_running_month(emp, month, year)
    ]
    report = []

    for emp in employees:
        summary = employee_monthly_summary(db, emp.id, month, year)
        report.append({
            "employee_id": emp.id,
            "employee_code": emp.employee_code,
            "name": emp.name,
            "employment_type": emp.employment_type,
            "joined_at": emp.joined_at,
            "present_days": summary["present_days"],
            "approved_leave_days": summary["approved_leave_days"],
            "absent_days": summary["absent_days"],
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


@router.get("/intern-attendance-report")
def intern_attendance_report(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    interns = (
        db.query(Employee)
        .filter(Employee.role != "super_admin", Employee.employment_type == "intern")
        .order_by(Employee.joined_at.asc(), Employee.id.asc())
        .all()
    )
    report = []

    for emp in interns:
        start_date, end_date = intern_period_dates(emp)
        summary = employee_period_attendance_summary(db, emp, start_date, end_date)
        report.append({
            "employee_id": emp.id,
            "employee_code": emp.employee_code,
            "name": emp.name,
            "email": emp.email,
            "shift": emp.shift,
            "joined_at": emp.joined_at,
            "intern_months": emp.intern_months,
            "intern_start": start_date,
            "intern_end": end_date,
            **summary,
        })

    return {"total_interns": len(report), "report": report}


@router.get("/intern-attendance-report/excel")
def intern_attendance_report_excel(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = intern_attendance_report(current_user, db)
    headers = [
        "Employee Code",
        "Name",
        "Email",
        "Shift",
        "Joined",
        "Intern Months",
        "Intern Start",
        "Intern End",
        "Working Days",
        "Present Days",
        "Approved Leave Days",
        "Absent Days",
        "Total Hours",
        "Attendance Percentage",
    ]
    rows = [
        [
            row["employee_code"],
            row["name"],
            row["email"],
            row["shift"],
            row["joined_at"],
            row["intern_months"],
            row["intern_start"],
            row["intern_end"],
            row["working_days"],
            row["present_days"],
            row["approved_leave_days"],
            row["absent_days"],
            row["total_hours"],
            row["attendance_percentage"],
        ]
        for row in data["report"]
    ]
    return excel_response(
        headers,
        rows,
        "intern-attendance-report.xls",
        "Intern Attendance Report",
        "Complete internship attendance summary",
    )


@router.get("/monthly-attendance-report/excel")
def monthly_attendance_report_excel(
    month: int,
    year: int,
    employee_id: int | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    data = monthly_attendance_report(month, year, employee_id, current_user, db)
    headers = [
        "Employee Code",
        "Name",
        "Employment Type",
        "Joined",
        "Present Days",
        "Approved Leave Days",
        "Absent Days",
        "Effective Working Days",
        "Extra Work Days",
        "Extra Work Hours",
        "Attendance Percentage",
    ]

    rows = []
    for row in data["report"]:
        rows.append([
            row["employee_code"],
            row["name"],
            row["employment_type"],
            row["joined_at"],
            row["present_days"],
            row["approved_leave_days"],
            row["absent_days"],
            row["effective_working_days"],
            row["extra_work_days"],
            row["extra_work_hours"],
            row["attendance_percentage"],
        ])

    employee_name = data["report"][0]["name"] if employee_id and data["report"] else None
    filename = (
        f"employee-attendance-report-{employee_id}-{year}-{month:02d}.xls"
        if employee_id
        else f"attendance-report-{year}-{month:02d}.xls"
    )
    return excel_response(
        headers,
        rows,
        filename,
        "Employee Monthly Attendance Report" if employee_id else "Monthly Attendance Report",
        f"Employee: {employee_name or employee_id} | Payroll Month: {month:02d}-{year}" if employee_id else f"Payroll Month: {month:02d}-{year}",
    )


@router.get("/attendance-report/excel")
def attendance_report_excel(
    period: str,
    selected_date: date | None = None,
    week: str | None = None,
    month: int | None = None,
    year: int | None = None,
    employee_id: int | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    employees_query = db.query(Employee).filter(Employee.role != "super_admin")
    if employee_id:
        employees_query = employees_query.filter(Employee.id == employee_id)

    employees = employees_query.order_by(Employee.id.asc()).all()

    if employee_id and not employees:
        raise HTTPException(status_code=404, detail="Employee not found")

    if period == "daily":
        report_date = selected_date or date.today()
        headers = [
            "Employee Code",
            "Name",
            "Email",
            "Role",
            "Shift",
            "Employment Type",
            "Date",
            "Status",
            "Login Time",
            "Logout Time",
            "Total Hours",
            "Late",
            "Late Minutes",
            "Left Early",
        ]
        rows = []

        for emp in employees:
            record = attendance_record_for_date(db, emp.id, report_date)
            status = employee_shift_date_status(db, emp, report_date)
            is_leave = status == "On Leave"
            rows.append([
                emp.employee_code,
                emp.name,
                emp.email,
                emp.role,
                emp.shift,
                emp.employment_type,
                report_date,
                "Leave" if is_leave else status,
                "Leave" if is_leave else (record.login_time if record else ""),
                "Leave" if is_leave else (record.logout_time if record else ""),
                "Leave" if is_leave else (str(attendance_total_hours(db, record)) if record else ""),
                "Leave" if is_leave else ("Yes" if record and record.is_late else "No"),
                "Leave" if is_leave else (late_minutes(record, emp.shift) if record else 0),
                "Leave" if is_leave else ("Yes" if record and record.left_early else "No"),
            ])

        return excel_response(
            headers,
            rows,
            f"employee-daily-attendance-report-{employee_id}-{report_date}.xls" if employee_id else f"daily-attendance-report-{report_date}.xls",
            "Employee Daily Attendance Report" if employee_id else "Daily Attendance Report",
            f"Employee: {employees[0].name} | Report Date: {report_date}" if employee_id else f"Report Date: {report_date}",
        )

    if period == "weekly":
        if not week:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            week = f"{week_start.isocalendar().year}-W{week_start.isocalendar().week:02d}"
        else:
            week_start, week_end = parse_week_input(week)

        headers = [
            "Employee Code",
            "Name",
            "Email",
            "Role",
            "Shift",
            "Employment Type",
            "Week Start",
            "Week End",
            "Working Days",
            "Present Days",
            "Approved Leave Days",
            "Absent Days",
            "Extra Work Days",
            "Extra Work Hours",
            "Total Hours",
            "Late Count",
            "Left Early Count",
            "Attendance Percentage",
        ]
        rows = []

        for emp in employees:
            summary = employee_period_attendance_summary(db, emp, week_start, week_end)
            rows.append([
                emp.employee_code,
                emp.name,
                emp.email,
                emp.role,
                emp.shift,
                emp.employment_type,
                week_start,
                week_end,
                summary["working_days"],
                summary["present_days"],
                summary["approved_leave_days"],
                summary["absent_days"],
                summary["extra_work_days"],
                summary["extra_work_hours"],
                summary["total_hours"],
                summary["late_count"],
                summary["early_count"],
                summary["attendance_percentage"],
            ])

        return excel_response(
            headers,
            rows,
            f"employee-weekly-attendance-report-{employee_id}-{week}.xls" if employee_id else f"weekly-attendance-report-{week}.xls",
            "Employee Weekly Attendance Report" if employee_id else "Weekly Attendance Report",
            f"Employee: {employees[0].name} | Week: {week} | Period: {week_start} to {week_end}" if employee_id else f"Week: {week} | Period: {week_start} to {week_end}",
        )

    if period == "monthly":
        today = date.today()
        month = month or today.month
        year = year or today.year
        return monthly_attendance_report_excel(month, year, employee_id, current_user, db)

    raise HTTPException(status_code=400, detail="Period must be daily, weekly, or monthly")


@router.get("/daily-attendance-trend")
def daily_attendance_trend(
    month: int,
    year: int,
    shift: str = "all",
    role: str = "all",
    employee_id: int | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    today = date.today()
    if month_start > today:
        return {
            "month": month,
            "year": year,
            "total_employees": 0,
            "daily": [],
        }

    month_end = min(month_end, today)
    employees_query = db.query(Employee).filter(
        Employee.role != "super_admin",
        Employee.role.isnot(None),
        Employee.shift.isnot(None),
    )

    if shift != "all":
        if shift == "morning":
            employees_query = employees_query.filter(Employee.shift.in_(["morning", "day"]))
        else:
            employees_query = employees_query.filter(Employee.shift == shift)
    if role != "all":
        employees_query = employees_query.filter(Employee.role == role)
    if employee_id:
        employees_query = employees_query.filter(Employee.id == employee_id)

    selected_employees = [
        emp for emp in employees_query.order_by(Employee.id.asc()).all()
        if include_employee_in_running_month(emp, month, year)
    ]
    records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id.in_([emp.id for emp in selected_employees]) if selected_employees else False,
            Attendance.date >= month_start,
            Attendance.date <= month_end,
        )
        .all()
    )
    records_by_key = {(record.employee_id, record.date): record for record in records}

    daily = []
    for day in range(1, month_end.day + 1):
        current = date(year, month, day)
        working_day = current.weekday() != 6
        item = {
            "date": current,
            "label": f"{day} Sun" if not working_day else str(day),
            "is_working_day": working_day,
            "scheduled": 0,
            "present": 0,
            "leave": 0,
            "absent": 0,
            "hours": 0,
            "late": 0,
            "early": 0,
        }

        for emp in selected_employees:
            status = employee_shift_date_status(db, emp, current)
            record = records_by_key.get((emp.id, current))

            if status in ["Pending Assignment", "Shift Not Started", "Joined Today - Work Starts Tomorrow"]:
                continue

            if working_day:
                item["scheduled"] += 1

            if working_day:
                if status in ["Present", "Working (Punched In)"]:
                    item["present"] += 1
                elif status == "On Leave":
                    item["leave"] += 1
                elif status == "Absent":
                    item["absent"] += 1

            if record:
                item["hours"] += round(attendance_total_hours(db, record).total_seconds() / 3600, 2)
                if working_day:
                    item["late"] += 1 if record.is_late else 0
                    item["early"] += 1 if record.left_early and record.logout_time else 0

        item["hours"] = round(item["hours"], 2)
        daily.append(item)

    return {
        "month": month,
        "year": year,
        "total_employees": len(selected_employees),
        "daily": daily,
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
        if not include_employee_in_running_month(emp, month, year):
            continue

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
