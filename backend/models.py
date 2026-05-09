from datetime import date

from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, Date, Interval, Boolean
from database import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String, nullable=True)
    shift = Column(String, nullable=True)
    joined_at = Column(Date, default=date.today)
    assigned_at = Column(TIMESTAMP, nullable=True)

class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(Date)
    login_time = Column(TIMESTAMP)
    logout_time = Column(TIMESTAMP)
    total_hours = Column(Interval)
    is_late = Column(Boolean, default=False)
    left_early = Column(Boolean, default=False)

class AttendancePunch(Base):
    __tablename__ = "attendance_punches"

    id = Column(Integer, primary_key=True, index=True)
    attendance_id = Column(Integer, ForeignKey("attendance.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    punch_type = Column(String)
    punch_time = Column(TIMESTAMP)
    
class Leave(Base):
    __tablename__ = "leaves"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))

    start_date = Column(Date)
    end_date = Column(Date)

    reason = Column(String)
    status = Column(String, default="pending")

    cancelled_at = Column(TIMESTAMP, nullable=True)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    token = Column(String, unique=True, index=True)
    expires_at = Column(TIMESTAMP)
    used_at = Column(TIMESTAMP, nullable=True)
