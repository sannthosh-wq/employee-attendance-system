import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from database import engine, Base

import auth
import attendance
import admin
import leave
import employee
import notifications
import payroll

Base.metadata.create_all(bind=engine)


def upgrade_existing_schema():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS joined_at DATE"))
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP"))
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS employee_code VARCHAR"))
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS employment_type VARCHAR DEFAULT 'full_time'"))
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS intern_months INTEGER"))
        connection.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS profile_photo VARCHAR"))
        connection.execute(text("""
            UPDATE employees
            SET employment_type = 'full_time'
            WHERE employment_type IS NULL
        """))
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
            SET employee_code = 'EMS-' || EXTRACT(YEAR FROM joined_at)::INT || '-' || LPAD(id::TEXT, 4, '0')
            WHERE employee_code IS NULL
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
        connection.execute(text("""
            UPDATE employees
            SET role = 'admin',
                shift = 'night',
                assigned_at = COALESCE(assigned_at, CURRENT_TIMESTAMP)
            WHERE LOWER(name) = 'namit'
              AND role != 'super_admin'
        """))
        connection.execute(text("""
            DELETE FROM attendance_punches
            WHERE attendance_id IN (
                SELECT attendance.id
                FROM attendance
                JOIN employees ON employees.id = attendance.employee_id
                WHERE employees.employment_type = 'intern'
                  AND employees.joined_at >= DATE '2026-05-12'
                  AND attendance.date = employees.joined_at
            )
        """))
        connection.execute(text("""
            DELETE FROM attendance
            USING employees
            WHERE employees.id = attendance.employee_id
              AND employees.employment_type = 'intern'
              AND employees.joined_at >= DATE '2026-05-12'
              AND attendance.date = employees.joined_at
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS salary_structure (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER NOT NULL REFERENCES employees(id),
                basic_salary NUMERIC(12, 2) NOT NULL,
                hra NUMERIC(12, 2) NOT NULL DEFAULT 0,
                travel_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                medical_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                special_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                effective_from DATE NOT NULL,
                created_by INTEGER REFERENCES employees(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS basic_salary NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS hra NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS travel_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS medical_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS special_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS effective_from DATE NOT NULL DEFAULT CURRENT_DATE"))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES employees(id)"))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        connection.execute(text("ALTER TABLE salary_structure ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_salary_structure_employee_effective
            ON salary_structure(employee_id, effective_from DESC)
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS payroll (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER NOT NULL REFERENCES employees(id),
                salary_structure_id INTEGER NOT NULL REFERENCES salary_structure(id),
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                total_days INTEGER NOT NULL DEFAULT 0,
                working_days NUMERIC(8, 2) NOT NULL DEFAULT 0,
                present_days NUMERIC(8, 2) NOT NULL DEFAULT 0,
                leave_days NUMERIC(8, 2) NOT NULL DEFAULT 0,
                absent_days NUMERIC(8, 2) NOT NULL DEFAULT 0,
                overtime_hours NUMERIC(10, 2) NOT NULL DEFAULT 0,
                basic_salary NUMERIC(12, 2) NOT NULL DEFAULT 0,
                hra NUMERIC(12, 2) NOT NULL DEFAULT 0,
                travel_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                medical_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                special_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                gross_salary NUMERIC(12, 2) NOT NULL DEFAULT 0,
                overtime_pay NUMERIC(12, 2) NOT NULL DEFAULT 0,
                pf NUMERIC(12, 2) NOT NULL DEFAULT 0,
                tax_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0,
                tax NUMERIC(12, 2) NOT NULL DEFAULT 0,
                loss_of_pay NUMERIC(12, 2) NOT NULL DEFAULT 0,
                total_deductions NUMERIC(12, 2) NOT NULL DEFAULT 0,
                net_salary NUMERIC(12, 2) NOT NULL DEFAULT 0,
                payslip_path VARCHAR,
                processed_by INTEGER REFERENCES employees(id),
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_payroll_employee_month_year UNIQUE(employee_id, month, year)
            )
        """))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS salary_structure_id INTEGER REFERENCES salary_structure(id)"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS total_days INTEGER NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS working_days NUMERIC(8, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS present_days NUMERIC(8, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS leave_days NUMERIC(8, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS absent_days NUMERIC(8, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS overtime_hours NUMERIC(10, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS basic_salary NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS hra NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS travel_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS medical_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS special_allowance NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS gross_salary NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS overtime_pay NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS pf NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS tax_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS tax NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS loss_of_pay NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS total_deductions NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS net_salary NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS payslip_path VARCHAR"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS processed_by INTEGER REFERENCES employees(id)"))
        connection.execute(text("ALTER TABLE payroll ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_payroll_month_year
            ON payroll(year, month)
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS allowances (
                id SERIAL PRIMARY KEY,
                payroll_id INTEGER NOT NULL REFERENCES payroll(id),
                name VARCHAR NOT NULL,
                amount NUMERIC(12, 2) NOT NULL DEFAULT 0
            )
        """))
        connection.execute(text("ALTER TABLE allowances ADD COLUMN IF NOT EXISTS payroll_id INTEGER REFERENCES payroll(id)"))
        connection.execute(text("ALTER TABLE allowances ADD COLUMN IF NOT EXISTS name VARCHAR NOT NULL DEFAULT ''"))
        connection.execute(text("ALTER TABLE allowances ADD COLUMN IF NOT EXISTS amount NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_allowances_payroll_id
            ON allowances(payroll_id)
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS deductions (
                id SERIAL PRIMARY KEY,
                payroll_id INTEGER NOT NULL REFERENCES payroll(id),
                name VARCHAR NOT NULL,
                amount NUMERIC(12, 2) NOT NULL DEFAULT 0
            )
        """))
        connection.execute(text("ALTER TABLE deductions ADD COLUMN IF NOT EXISTS payroll_id INTEGER REFERENCES payroll(id)"))
        connection.execute(text("ALTER TABLE deductions ADD COLUMN IF NOT EXISTS name VARCHAR NOT NULL DEFAULT ''"))
        connection.execute(text("ALTER TABLE deductions ADD COLUMN IF NOT EXISTS amount NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_deductions_payroll_id
            ON deductions(payroll_id)
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY,
                title VARCHAR NOT NULL,
                message TEXT NOT NULL,
                created_by INTEGER REFERENCES employees(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                deleted_at TIMESTAMP
            )
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
app.include_router(notifications.router)
app.include_router(payroll.router)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/")
def home():
    return {"message": "Attendance System API Running"}
