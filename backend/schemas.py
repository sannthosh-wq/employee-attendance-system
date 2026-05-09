from pydantic import BaseModel
from datetime import datetime, date

class RegisterSchema(BaseModel):
    name: str
    email: str
    password: str

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
    login_time: datetime
    logout_time: datetime | None
    total_hours: str | None

    is_late: bool
    left_early: bool

    class Config:
        from_attributes = True
        
class ShiftUpdateSchema(BaseModel):
    shift: str

class RoleUpdateSchema(BaseModel):
    role: str
    
class LeaveCreateSchema(BaseModel):
    start_date: date
    end_date: date
    reason: str

class LeaveStatusUpdateSchema(BaseModel):
    status: str

class LeaveResponse(BaseModel):
    id: int
    start_date: date
    end_date: date
    reason: str
    status: str

    class Config:
        from_attributes = True
