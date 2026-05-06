from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Employee, Attendance
from deps import get_current_user
from schemas import ShiftUpdateSchema
from schemas import RoleUpdateSchema

router = APIRouter(prefix="/admin")

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