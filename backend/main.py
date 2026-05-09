from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import engine, Base

import auth
import attendance
import admin
import leave
import employee

Base.metadata.create_all(bind=engine)


def upgrade_existing_schema():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS joined_at DATE"))
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP"))
        connection.execute(text("""
            UPDATE employees
            SET joined_at = COALESCE(
                joined_at,
                (
                    SELECT MIN(attendance.date)
                    FROM attendance
                    WHERE attendance.employee_id = employees.id
                ),
                CURRENT_DATE
            )
        """))
        connection.execute(text("""
            UPDATE employees
            SET assigned_at = COALESCE(assigned_at, CURRENT_TIMESTAMP)
            WHERE role IS NOT NULL
              AND shift IS NOT NULL
              AND assigned_at IS NULL
        """))
        connection.execute(text("""
            UPDATE employees
            SET shift = NULL
            WHERE role = 'super_admin'
        """))


upgrade_existing_schema()

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(admin.router)
app.include_router(leave.router)
app.include_router(employee.router)

@app.get("/")
def home():
    return {"message": "Attendance System API Running"}
