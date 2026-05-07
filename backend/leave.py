from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Leave
from deps import get_current_user
from schemas import LeaveCreateSchema, LeaveStatusUpdateSchema
from datetime import datetime, date
from schemas import LeaveResponse

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
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


def require_employee(user):
    if user.role != "employee":
        raise HTTPException(status_code=403, detail="Employee access only")


# ---------------- APPLY LEAVE (EMPLOYEE ONLY) ----------------
@router.post("/apply")
def apply_leave(
    leave_data: LeaveCreateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_employee(current_user)

    if leave_data.start_date < date.today():
        raise HTTPException(status_code=400, detail="Cannot apply leave for past dates")

    if leave_data.end_date < leave_data.start_date:
        raise HTTPException(status_code=400, detail="End date cannot be before start date")

    total_days = (leave_data.end_date - leave_data.start_date).days + 1

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


# ---------------- EMPLOYEE: MY LEAVES ----------------
@router.get("/my-leaves", response_model=list[LeaveResponse])
def my_leaves(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_employee(current_user)

    return db.query(Leave).filter(
        Leave.employee_id == current_user.id
    ).all()


# ---------------- EMPLOYEE: MY LEAVE COUNT ----------------
@router.get("/my-leave-count")
def my_leave_count(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    require_employee(current_user)

    approved_leaves = db.query(Leave).filter(
        Leave.employee_id == current_user.id,
        Leave.status == "approved"
    ).all()

    total_days = sum(
        (leave.end_date - leave.start_date).days + 1
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

    return db.query(Leave).all()


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

    if status_data.status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    leave.status = status_data.status

    if status_data.status == "rejected":
        leave.cancelled_at = datetime.utcnow()

    db.commit()

    return {
        "message": f"Leave {status_data.status} successfully"
    }