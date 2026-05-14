from pydantic import BaseModel
from datetime import datetime, date
from decimal import Decimal

class RegisterSchema(BaseModel):
    name: str
    email: str
    password: str
    employment_type: str = "full_time"

class LoginSchema(BaseModel):
    email: str
    password: str

class ForgotPasswordSchema(BaseModel):
    email: str

class ResetPasswordSchema(BaseModel):
    email: str
    token: str
    new_password: str

class AttendanceResponse(BaseModel):
    date: date
    login_time: datetime | None
    logout_time: datetime | None
    total_hours: str | None
    status: str | None = None

    is_late: bool
    late_minutes: int
    left_early: bool

    class Config:
        from_attributes = True
        
class ShiftUpdateSchema(BaseModel):
    shift: str

class RoleUpdateSchema(BaseModel):
    role: str

class EmploymentTypeUpdateSchema(BaseModel):
    employment_type: str
    intern_months: int | None = None
    
class LeaveCreateSchema(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    from_date: date | None = None
    to_date: date | None = None
    leave_type: str | None = None
    reason: str
    custom_reason: str | None = None
    additional_comments: str | None = None

class LeaveStatusUpdateSchema(BaseModel):
    status: str

class AnnouncementCreateSchema(BaseModel):
    title: str
    message: str

class AnnouncementUpdateSchema(BaseModel):
    title: str
    message: str

class LeaveResponse(BaseModel):
    id: int
    start_date: date
    end_date: date
    from_date: date | None = None
    to_date: date | None = None
    reason: str
    leave_type: str | None = None
    custom_reason: str | None = None
    additional_comments: str | None = None
    status: str
    applied_at: datetime | None = None

    class Config:
        from_attributes = True


class SalaryStructureCreateSchema(BaseModel):
    employee_id: int
    basic_salary: Decimal
    hra: Decimal = Decimal("0")
    travel_allowance: Decimal = Decimal("0")
    medical_allowance: Decimal = Decimal("0")
    special_allowance: Decimal = Decimal("0")
    effective_from: date


class SalaryStructureUpdateSchema(BaseModel):
    basic_salary: Decimal
    hra: Decimal = Decimal("0")
    travel_allowance: Decimal = Decimal("0")
    medical_allowance: Decimal = Decimal("0")
    special_allowance: Decimal = Decimal("0")
    effective_from: date


class SalaryStructureResponse(BaseModel):
    id: int
    employee_id: int
    basic_salary: Decimal
    hra: Decimal
    travel_allowance: Decimal
    medical_allowance: Decimal
    special_allowance: Decimal
    total_salary: Decimal
    effective_from: date
    is_active: bool

    class Config:
        from_attributes = True


class PayrollProcessSchema(BaseModel):
    month: int
    year: int
    tax_percentage: Decimal = Decimal("0")
    employee_id: int | None = None


class PayrollResponse(BaseModel):
    id: int
    employee_id: int
    salary_structure_id: int
    month: int
    year: int
    total_days: int
    working_days: Decimal
    present_days: Decimal
    leave_days: Decimal
    absent_days: Decimal
    overtime_hours: Decimal
    basic_salary: Decimal
    hra: Decimal
    travel_allowance: Decimal
    medical_allowance: Decimal
    special_allowance: Decimal
    gross_salary: Decimal
    overtime_pay: Decimal
    pf: Decimal
    tax_percentage: Decimal
    tax: Decimal
    loss_of_pay: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    payslip_path: str | None
    processed_at: datetime | None

    class Config:
        from_attributes = True
