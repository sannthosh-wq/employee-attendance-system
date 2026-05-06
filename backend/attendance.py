from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Attendance
from datetime import datetime, date
from deps import get_current_user

router = APIRouter(prefix="/attendance")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/punch-in")
def punch_in(current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()

    existing = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today
    ).first()

    if existing and existing.logout_time is None:
        raise HTTPException(status_code=400, detail="Already punched in. Please punch out first.")

    record = Attendance(
        employee_id=current_user.id,
        date=today,
        login_time=datetime.now()
    )

    db.add(record)
    db.commit()

    return {"message": "Punch in successful"}

@router.post("/punch-out")
def punch_out(current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()

    record = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.logout_time == None
    ).first()

    if not record or record.logout_time:
        raise HTTPException(status_code=400, detail="No active session")

    now = datetime.now()
    record.logout_time = now
    record.total_hours = now - record.login_time

    db.commit()

    return {"message": "Punch out successful"}

@router.get("/my-attendance")
def my_attendance(current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Attendance).filter(
        Attendance.employee_id == current_user.id
    ).all()