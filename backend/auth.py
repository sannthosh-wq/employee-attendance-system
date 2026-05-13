import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Employee, PasswordReset
from schemas import ForgotPasswordSchema, LoginSchema, RegisterSchema, ResetPasswordSchema
from utils import hash_password, verify_password
from jwt_handler import create_access_token
from attendance_logic import is_internship_over

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

VALID_EMPLOYMENT_TYPES = {"full_time", "intern", "contract"}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/register")
def register(user: RegisterSchema, db: Session = Depends(get_db)):
    existing = db.query(Employee).filter(Employee.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    if user.employment_type not in VALID_EMPLOYMENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid employment type")

    new_user = Employee(
        name=user.name,
        email=user.email,
        password=hash_password(user.password),
        role=None,
        shift=None,
        employment_type=user.employment_type,
        joined_at=date.today(),
        assigned_at=None,
    )

    db.add(new_user)
    db.flush()
    new_user.employee_code = f"EMS-{new_user.joined_at.year}-{new_user.id:04d}"
    db.commit()

    return {"message": "User registered", "employee_code": new_user.employee_code}

@router.post("/login")
def login(user: LoginSchema, db: Session = Depends(get_db)):
    db_user = db.query(Employee).filter(Employee.email == user.email).first()

    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if is_internship_over(db_user):
        raise HTTPException(status_code=403, detail="Your internship period is over so you cannot login")

    token = create_access_token({
        "user_id": db_user.id,
        "role": db_user.role
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordSchema, db: Session = Depends(get_db)):
    user = db.query(Employee).filter(Employee.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email")

    db.query(PasswordReset).filter(
        PasswordReset.employee_id == user.id,
        PasswordReset.used_at.is_(None),
    ).update({"used_at": datetime.utcnow()})

    token = secrets.token_urlsafe(24)
    reset = PasswordReset(
        employee_id=user.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )

    db.add(reset)
    db.commit()

    return {
        "message": "Password reset code generated",
        "reset_token": token,
        "expires_in_minutes": 15,
    }


@router.post("/reset-password")
def reset_password(data: ResetPasswordSchema, db: Session = Depends(get_db)):
    user = db.query(Employee).filter(Employee.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email")

    reset = db.query(PasswordReset).filter(
        PasswordReset.employee_id == user.id,
        PasswordReset.token == data.token,
        PasswordReset.used_at.is_(None),
    ).first()

    if not reset:
        raise HTTPException(status_code=400, detail="Invalid or used reset code")

    if reset.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset code expired")

    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user.password = hash_password(data.new_password)
    reset.used_at = datetime.utcnow()
    db.commit()

    return {"message": "Password reset successfully"}
