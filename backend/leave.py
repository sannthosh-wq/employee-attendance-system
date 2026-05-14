from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Attendance, Employee, Leave
from deps import get_current_user
from schemas import LeaveCreateSchema, LeaveStatusUpdateSchema
from datetime import datetime, date, timedelta
from schemas import LeaveResponse
from attendance_logic import employee_leave_balance, has_leave_overlap, require_assignment_complete, working_leave_days
from notifications import create_notification, notify_admins

router = APIRouter(
    prefix="/leave",
    tags=["Leave"]
)
public_router = APIRouter(tags=["Leave"])

VALID_LEAVE_TYPES = {"Casual", "Sick", "Earned", "Emergency"}

# ---------------- DB ----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- ROLE HELPERS ----------------
def require_admin(user):
    if user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")


def require_super_admin(user):
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")


def require_leave_applicant(user):
    if user.role == "super_admin":
        raise HTTPException(status_code=403, detail="Super admins cannot apply for leave")
    require_assignment_complete(user)


def admin_on_leave_today(db: Session):
    today = date.today()
    return (
        db.query(Leave)
        .join(Employee, Leave.employee_id == Employee.id)
        .filter(
            Employee.role == "admin",
            Leave.status == "approved",
            Leave.start_date <= today,
            Leave.end_date >= today,
        )
        .first()
        is not None
    )


def requested_leave_days_by_month(start_date: date, end_date: date):
    days_by_month = {}
    current = start_date

    while current <= end_date:
        if current.weekday() != 6:
            key = (current.year, current.month)
            days_by_month[key] = days_by_month.get(key, 0) + 1
        current += timedelta(days=1)

    return days_by_month


def validate_monthly_leave_balance(
    db: Session,
    employee_id: int,
    start_date: date,
    end_date: date,
    exclude_leave_id: int | None = None,
):
    for (year, month), requested_days in requested_leave_days_by_month(start_date, end_date).items():
        balance = employee_leave_balance(
            db,
            employee_id,
            month=month,
            year=year,
            exclude_leave_id=exclude_leave_id,
        )

        if requested_days > balance["remaining_days"]:
            month_name = date(year, month, 1).strftime("%B %Y")
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Leave request exceeds available leave balance for {month_name}. "
                    f"Available: {balance['remaining_days']} day(s), requested: {requested_days} day(s)."
                ),
            )


def leave_balance_warnings(db: Session, employee_id: int, start_date: date, end_date: date):
    warnings = []
    for (year, month), requested_days in requested_leave_days_by_month(start_date, end_date).items():
        balance = employee_leave_balance(db, employee_id, month=month, year=year)
        if requested_days > balance["remaining_days"]:
            month_name = date(year, month, 1).strftime("%B %Y")
            warnings.append(
                f"{month_name}: available {balance['remaining_days']} day(s), requested {requested_days} day(s)"
            )

    return warnings


def can_update_leave(current_user, leave_owner, db: Session):
    if leave_owner.role == "super_admin":
        raise HTTPException(status_code=403, detail="Super admin leave cannot be updated")
    return


# ---------------- APPLY LEAVE (NON-ADMIN ONLY) ----------------
@public_router.post("/apply-leave")
@router.post("/apply")
def apply_leave(
    leave_data: LeaveCreateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_leave_applicant(current_user)
    start_date = leave_data.from_date or leave_data.start_date
    end_date = leave_data.to_date or leave_data.end_date
    leave_type = (leave_data.leave_type or "Casual").strip()
    reason = leave_data.reason.strip()
    custom_reason = leave_data.custom_reason.strip() if leave_data.custom_reason else None
    additional_comments = leave_data.additional_comments.strip() if leave_data.additional_comments else None

    if not start_date or not end_date:
        raise HTTPException(status_code=400, detail="From Date and To Date are required")

    if leave_type not in VALID_LEAVE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid leave type")

    if not reason:
        raise HTTPException(status_code=400, detail="Leave reason is required")

    if reason == "Other" and not custom_reason:
        raise HTTPException(status_code=400, detail="Custom reason is required when Other is selected")

    if end_date < start_date:
        raise HTTPException(status_code=400, detail="From Date cannot be greater than To Date")

    if start_date < date.today() or end_date < date.today():
        raise HTTPException(status_code=400, detail="Leave cannot be applied for past dates")

    total_days = working_leave_days(start_date, end_date)

    warnings = leave_balance_warnings(db, current_user.id, start_date, end_date)
    if total_days <= 0:
        warnings.append("This request only includes holidays and will need admin review")

    existing_leave = (
        db.query(Leave)
        .filter(
            Leave.employee_id == current_user.id,
            Leave.start_date == start_date,
            Leave.end_date == end_date,
            Leave.status.in_(["pending", "approved"]),
        )
        .first()
    )
    if existing_leave:
        return {
            "message": f"Leave request already {existing_leave.status}",
            "leave_id": existing_leave.id,
            "total_days": total_days,
            "balance_warning": "; ".join(warnings) if warnings else None,
            "leave_balance": employee_leave_balance(db, current_user.id),
        }

    new_leave = Leave(
        employee_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        from_date=start_date,
        to_date=end_date,
        leave_date=start_date,
        leave_type=leave_type,
        reason=reason,
        custom_reason=custom_reason,
        additional_comments=additional_comments,
        status="pending"
    )

    db.add(new_leave)
    db.flush()
    notify_admins(
        db,
        "New leave request",
        f"{current_user.name} requested {total_days} {leave_type.lower()} leave day(s) from {start_date} to {end_date}.",
        "leave_request",
        current_user.id,
    )
    db.commit()
    db.refresh(new_leave)

    return {
        "message": "Leave applied successfully",
        "leave_id": new_leave.id,
        "total_days": total_days,
        "balance_warning": "; ".join(warnings) if warnings else None,
        "leave_balance": employee_leave_balance(db, current_user.id),
    }


# ---------------- NON-ADMIN: MY LEAVES ----------------
@router.get("/my-leaves", response_model=list[LeaveResponse])
def my_leaves(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_leave_applicant(current_user)

    return db.query(Leave).filter(
        Leave.employee_id == current_user.id
    ).all()


# ---------------- NON-ADMIN: MY LEAVE COUNT ----------------
@router.get("/my-leave-count")
def my_leave_count(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_leave_applicant(current_user)

    approved_leaves = db.query(Leave).filter(
        Leave.employee_id == current_user.id,
        Leave.status == "approved"
    ).all()

    total_days = sum(
        working_leave_days(leave.start_date, leave.end_date)
        for leave in approved_leaves
    )

    return {
        "employee_id": current_user.id,
        "total_approved_leave_days": total_days,
        **employee_leave_balance(db, current_user.id),
    }


# ---------------- ADMIN: VIEW ALL LEAVES ----------------
@router.get("/all")
def all_leaves(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_admin(current_user)

    query = db.query(Leave, Employee).join(Employee, Leave.employee_id == Employee.id)

    query = query.filter(Employee.role != "super_admin")

    return [
        {
            "id": leave.id,
            "employee_id": leave.employee_id,
            "employee_name": employee.name,
            "employee_role": employee.role,
            "employee_code": employee.employee_code,
            "employment_type": employee.employment_type,
            "start_date": leave.start_date,
            "end_date": leave.end_date,
            "from_date": leave.from_date,
            "to_date": leave.to_date,
            "total_days": working_leave_days(leave.start_date, leave.end_date),
            "leave_balance": employee_leave_balance(db, employee.id),
            "leave_type": leave.leave_type,
            "reason": leave.reason,
            "custom_reason": leave.custom_reason,
            "additional_comments": leave.additional_comments,
            "status": leave.status,
            "applied_at": leave.applied_at,
        }
        for leave, employee in query.order_by(Leave.id.desc()).all()
    ]


# ---------------- ADMIN: APPROVE / REJECT ----------------
@router.put("/{leave_id}")
def update_leave_status(
    leave_id: int,
    status_data: LeaveStatusUpdateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_admin(current_user)

    leave = db.query(Leave).filter(Leave.id == leave_id).first()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    leave_owner = db.query(Employee).filter(Employee.id == leave.employee_id).first()
    if not leave_owner:
        raise HTTPException(status_code=404, detail="Leave employee not found")

    can_update_leave(current_user, leave_owner, db)

    if status_data.status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    if leave.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending leave requests can be updated")

    if status_data.status == "approved":
        validate_monthly_leave_balance(
            db,
            leave.employee_id,
            leave.start_date,
            leave.end_date,
            exclude_leave_id=leave.id,
        )

        existing_attendance = db.query(Attendance).filter(
            Attendance.employee_id == leave.employee_id,
            Attendance.date >= leave.start_date,
            Attendance.date <= leave.end_date,
        ).first()
        if existing_attendance:
            raise HTTPException(status_code=400, detail="Cannot approve leave for attended dates")

        overlap = has_leave_overlap(
            db,
            leave.employee_id,
            leave.start_date,
            leave.end_date,
            statuses=("approved",),
        )
        if overlap and overlap.id != leave.id:
            raise HTTPException(status_code=400, detail="Approved leave overlaps another leave")

    leave.status = status_data.status

    if status_data.status == "rejected":
        leave.cancelled_at = datetime.utcnow()
    else:
        leave.cancelled_at = None

    total_days = working_leave_days(leave.start_date, leave.end_date)
    create_notification(
        db,
        f"Leave {status_data.status}",
        f"Your leave request from {leave.start_date} to {leave.end_date} was {status_data.status}.",
        "leave_status",
        leave.employee_id,
        current_user.id,
    )
    notify_admins(
        db,
        "Leave decision recorded",
        f"{current_user.name} {status_data.status} {leave_owner.name}'s {total_days} day leave request.",
        "leave_status",
        current_user.id,
    )

    db.commit()

    return {
        "message": f"Leave {status_data.status} successfully"
    }
