from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Attendance, Employee, Leave
from deps import get_current_user
from schemas import LeaveCreateSchema, LeaveStatusUpdateSchema
from datetime import datetime, date
from schemas import LeaveResponse
from attendance_logic import has_leave_overlap, require_assignment_complete, working_leave_days

router = APIRouter(
    prefix="/leave",
    tags=["Leave"]
)

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


def can_update_leave(current_user, leave_owner, db: Session):
    if leave_owner.role == "super_admin":
        raise HTTPException(status_code=403, detail="Super admin leave cannot be updated")

    if current_user.role == "admin":
        if leave_owner.role == "admin":
            raise HTTPException(status_code=403, detail="Admin leave requires super admin approval")
        return

    if current_user.role == "super_admin":
        if leave_owner.role == "admin":
            return
        if admin_on_leave_today(db):
            return
        raise HTTPException(
            status_code=403,
            detail="Super admin can approve employee leave only when an admin is on leave",
        )


# ---------------- APPLY LEAVE (NON-ADMIN ONLY) ----------------
@router.post("/apply")
def apply_leave(
    leave_data: LeaveCreateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_leave_applicant(current_user)

    if leave_data.start_date < date.today():
        raise HTTPException(status_code=400, detail="Cannot apply leave for past dates")

    if leave_data.end_date < leave_data.start_date:
        raise HTTPException(status_code=400, detail="End date cannot be before start date")

    if has_leave_overlap(db, current_user.id, leave_data.start_date, leave_data.end_date):
        raise HTTPException(status_code=400, detail="Leave request overlaps an existing leave")

    total_days = working_leave_days(leave_data.start_date, leave_data.end_date)

    new_leave = Leave(
        employee_id=current_user.id,
        start_date=leave_data.start_date,
        end_date=leave_data.end_date,
        reason=leave_data.reason,
        status="pending"
    )

    db.add(new_leave)
    db.commit()

    return {
        "message": "Leave applied successfully",
        "total_days": total_days
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
        "total_approved_leave_days": total_days
    }


# ---------------- ADMIN: VIEW ALL LEAVES ----------------
@router.get("/all")
def all_leaves(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_admin(current_user)

    query = db.query(Leave, Employee).join(Employee, Leave.employee_id == Employee.id)

    if current_user.role == "admin":
        query = query.filter(Employee.role != "admin", Employee.role != "super_admin")
    elif current_user.role == "super_admin":
        if admin_on_leave_today(db):
            query = query.filter(Employee.role != "super_admin")
        else:
            query = query.filter(Employee.role == "admin")

    return [
        {
            "id": leave.id,
            "employee_id": leave.employee_id,
            "employee_name": employee.name,
            "employee_role": employee.role,
            "start_date": leave.start_date,
            "end_date": leave.end_date,
            "reason": leave.reason,
            "status": leave.status,
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

    db.commit()

    return {
        "message": f"Leave {status_data.status} successfully"
    }
