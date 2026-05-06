from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Employee
from schemas import RegisterSchema, LoginSchema
from utils import hash_password, verify_password
from jwt_handler import create_access_token

router = APIRouter(prefix="/auth")

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

    new_user = Employee(
        name=user.name,
        email=user.email,
        password=hash_password(user.password),
        role="employee",
        shift="morning"
    )

    db.add(new_user)
    db.commit()

    return {"message": "User registered"}

@router.post("/login")
def login(user: LoginSchema, db: Session = Depends(get_db)):
    db_user = db.query(Employee).filter(Employee.email == user.email).first()

    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "user_id": db_user.id,
        "role": db_user.role
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }