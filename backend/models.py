from datetime import date, datetime

from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, Date, Interval, Boolean, Text, Numeric, UniqueConstraint, Float, Index
from sqlalchemy.orm import relationship
from .database import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String, unique=True, index=True, nullable=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String, nullable=True)
    shift = Column(String, nullable=True)
    department = Column(String, nullable=True)
    employment_type = Column(String, default="full_time")
    intern_months = Column(Integer, nullable=True)
    profile_photo = Column(String, nullable=True)
    joined_at = Column(Date, default=date.today)
    assigned_at = Column(TIMESTAMP, nullable=True)
    attendance_records = relationship("Attendance", back_populates="employee", foreign_keys="Attendance.employee_id")
    salary_structures = relationship("SalaryStructure", back_populates="employee", foreign_keys="SalaryStructure.employee_id")
    payroll_records = relationship("Payroll", back_populates="employee", foreign_keys="Payroll.employee_id")

class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
        Index("ix_attendance_date_status", "date", "status"),
        Index("ix_attendance_employee_date", "employee_id", "date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(Date)
    login_time = Column(TIMESTAMP)
    logout_time = Column(TIMESTAMP)
    total_hours = Column(Interval)
    status = Column(String, default="Present")
    is_late = Column(Boolean, default=False)
    left_early = Column(Boolean, default=False)
    late_minutes = Column(Integer, default=0)
    early_minutes = Column(Integer, default=0)
    working_hours = Column(Float, default=0.0)
    employee = relationship("Employee", back_populates="attendance_records", foreign_keys=[employee_id])

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
    from_date = Column(Date)
    to_date = Column(Date)
    leave_date = Column(Date)

    reason = Column(String)
    leave_type = Column(String, nullable=True)
    custom_reason = Column(Text, nullable=True)
    additional_comments = Column(Text, nullable=True)
    status = Column(String, default="pending")
    applied_at = Column(TIMESTAMP, default=datetime.utcnow)

    cancelled_at = Column(TIMESTAMP, nullable=True)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    token = Column(String, unique=True, index=True)
    expires_at = Column(TIMESTAMP)
    used_at = Column(TIMESTAMP, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    recipient_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    title = Column(String)
    message = Column(Text)
    type = Column(String)
    read_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    title = Column(String)
    message = Column(Text)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=True)
    deleted_at = Column(TIMESTAMP, nullable=True)


class SalaryStructure(Base):
    __tablename__ = "salary_structure"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    basic_salary = Column(Numeric(12, 2), nullable=False)
    hra = Column(Numeric(12, 2), nullable=False, default=0)
    travel_allowance = Column(Numeric(12, 2), nullable=False, default=0)
    medical_allowance = Column(Numeric(12, 2), nullable=False, default=0)
    special_allowance = Column(Numeric(12, 2), nullable=False, default=0)
    total_salary = Column(Numeric(12, 2), nullable=False, default=0)
    effective_from = Column(Date, nullable=False)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    employee = relationship("Employee", back_populates="salary_structures", foreign_keys=[employee_id])
    payroll_records = relationship("Payroll", back_populates="salary_structure", foreign_keys="Payroll.salary_structure_id")


class Payroll(Base):
    __tablename__ = "payroll"
    __table_args__ = (
        UniqueConstraint("employee_id", "month", "year", name="uq_payroll_employee_month_year"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    salary_structure_id = Column(Integer, ForeignKey("salary_structure.id"), nullable=False)
    month = Column(Integer, index=True, nullable=False)
    year = Column(Integer, index=True, nullable=False)
    total_days = Column(Integer, nullable=False, default=0)
    working_days = Column(Numeric(8, 2), nullable=False, default=0)
    present_days = Column(Numeric(8, 2), nullable=False, default=0)
    leave_days = Column(Numeric(8, 2), nullable=False, default=0)
    absent_days = Column(Numeric(8, 2), nullable=False, default=0)
    overtime_hours = Column(Numeric(10, 2), nullable=False, default=0)
    basic_salary = Column(Numeric(12, 2), nullable=False, default=0)
    hra = Column(Numeric(12, 2), nullable=False, default=0)
    travel_allowance = Column(Numeric(12, 2), nullable=False, default=0)
    medical_allowance = Column(Numeric(12, 2), nullable=False, default=0)
    special_allowance = Column(Numeric(12, 2), nullable=False, default=0)
    gross_salary = Column(Numeric(12, 2), nullable=False, default=0)
    overtime_pay = Column(Numeric(12, 2), nullable=False, default=0)
    pf = Column(Numeric(12, 2), nullable=False, default=0)
    tax_percentage = Column(Numeric(5, 2), nullable=False, default=0)
    tax = Column(Numeric(12, 2), nullable=False, default=0)
    loss_of_pay = Column(Numeric(12, 2), nullable=False, default=0)
    total_deductions = Column(Numeric(12, 2), nullable=False, default=0)
    net_salary = Column(Numeric(12, 2), nullable=False, default=0)
    payslip_path = Column(String, nullable=True)
    processed_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    processed_at = Column(TIMESTAMP, default=datetime.utcnow)
    employee = relationship("Employee", back_populates="payroll_records", foreign_keys=[employee_id])
    salary_structure = relationship("SalaryStructure", back_populates="payroll_records", foreign_keys=[salary_structure_id])
    allowances = relationship("PayrollAllowance", back_populates="payroll", cascade="all, delete-orphan")
    deductions = relationship("PayrollDeduction", back_populates="payroll", cascade="all, delete-orphan")


class PayrollAllowance(Base):
    __tablename__ = "allowances"

    id = Column(Integer, primary_key=True)
    payroll_id = Column(Integer, ForeignKey("payroll.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False, default=0)
    payroll = relationship("Payroll", back_populates="allowances")


class PayrollDeduction(Base):
    __tablename__ = "deductions"

    id = Column(Integer, primary_key=True)
    payroll_id = Column(Integer, ForeignKey("payroll.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False, default=0)
    payroll = relationship("Payroll", back_populates="deductions")


class AttritionPrediction(Base):
    __tablename__ = "attrition_predictions"
    __table_args__ = (
        Index("ix_attrition_predictions_employee_date", "employee_id", "predicted_on"),
    )

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    risk_score = Column(Float, nullable=False, default=0.0)
    risk_level = Column(String, nullable=False)
    predicted_on = Column(TIMESTAMP, default=datetime.utcnow, index=True)
