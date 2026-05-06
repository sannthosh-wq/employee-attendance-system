from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, Date, Interval, Boolean
from database import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String, default="employee")
    shift = Column(String, default="morning")

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
    
class Leave(Base):
    __tablename__ = "leaves"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))

    start_date = Column(Date)
    end_date = Column(Date)

    reason = Column(String)
    status = Column(String, default="pending")

    cancelled_at = Column(TIMESTAMP, nullable=True)