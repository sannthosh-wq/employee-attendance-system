from pydantic import BaseModel
from datetime import datetime, date

class RegisterSchema(BaseModel):
    name: str
    email: str
    password: str

class LoginSchema(BaseModel):
    email: str
    password: str

class AttendanceResponse(BaseModel):
    date: date
    login_time: datetime
    logout_time: datetime | None
    total_hours: str | None

    class Config:
        from_attributes = True
        
class ShiftUpdateSchema(BaseModel):
    shift: str

class RoleUpdateSchema(BaseModel):
    role: str