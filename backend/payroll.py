from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database import SessionLocal
from .deps import get_current_user
from .models import Employee, Payroll, SalaryStructure
from .payroll_service import create_salary_revision, generate_payslip_pdf, process_monthly_payroll, revise_salary_structure
from .schemas import PayrollProcessSchema, PayrollResponse, SalaryStructureCreateSchema, SalaryStructureResponse, SalaryStructureUpdateSchema

router = APIRouter(prefix="/payroll", tags=["Payroll"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(user):
    if user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")


def can_view_employee_payroll(current_user, employee_id: int):
    if current_user.role in ["admin", "super_admin"]:
        return
    if current_user.id != employee_id:
        raise HTTPException(status_code=403, detail="Employees can only view their own payroll")


@router.post("/salary", response_model=SalaryStructureResponse)
def assign_salary(
    salary_data: SalaryStructureCreateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    return create_salary_revision(db, salary_data, current_user.id, current_user)


@router.get("/salary")
def all_assigned_salaries(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    rows = (
        db.query(SalaryStructure, Employee)
        .join(Employee, SalaryStructure.employee_id == Employee.id)
        .filter(Employee.role != "super_admin")
        .order_by(Employee.id.asc(), SalaryStructure.effective_from.desc(), SalaryStructure.id.desc())
        .all()
    )

    return [
        {
            "id": salary.id,
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "employee_name": employee.name,
            "email": employee.email,
            "role": employee.role,
            "basic_salary": salary.basic_salary,
            "hra": salary.hra,
            "travel_allowance": salary.travel_allowance,
            "medical_allowance": salary.medical_allowance,
            "special_allowance": salary.special_allowance,
            "total_salary": salary.total_salary,
            "effective_from": salary.effective_from,
            "is_active": salary.is_active,
        }
        for salary, employee in rows
    ]


@router.put("/salary/{salary_id}", response_model=SalaryStructureResponse)
def update_salary(
    salary_id: int,
    salary_data: SalaryStructureUpdateSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    return revise_salary_structure(db, salary_id, salary_data, current_user.id, current_user)


@router.get("/salary/employee/{employee_id}/current", response_model=SalaryStructureResponse)
def current_salary(
    employee_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    can_view_employee_payroll(current_user, employee_id)
    salary = (
        db.query(SalaryStructure)
        .filter(SalaryStructure.employee_id == employee_id, SalaryStructure.is_active == True)
        .order_by(SalaryStructure.effective_from.desc(), SalaryStructure.id.desc())
        .first()
    )
    if not salary:
        raise HTTPException(status_code=404, detail="Salary structure not found")
    return salary


@router.get("/salary/employee/{employee_id}", response_model=list[SalaryStructureResponse])
def salary_history(
    employee_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    return (
        db.query(SalaryStructure)
        .filter(SalaryStructure.employee_id == employee_id)
        .order_by(SalaryStructure.effective_from.desc(), SalaryStructure.id.desc())
        .all()
    )


@router.post("/process", response_model=list[PayrollResponse])
def process_payroll(
    payroll_data: PayrollProcessSchema,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    if current_user.role == "admin" and payroll_data.employee_id == current_user.id:
        raise HTTPException(status_code=403, detail="Admins cannot process payroll for themselves")

    try:
        return process_monthly_payroll(
            db,
            payroll_data.month,
            payroll_data.year,
            payroll_data.tax_percentage,
            current_user.id,
            payroll_data.employee_id,
            current_user.role,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Payroll processing failed: {exc}") from exc


@router.get("/employee/{employee_id}", response_model=list[PayrollResponse])
def get_payroll_by_employee(
    employee_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    can_view_employee_payroll(current_user, employee_id)
    return (
        db.query(Payroll)
        .filter(Payroll.employee_id == employee_id)
        .order_by(Payroll.year.desc(), Payroll.month.desc())
        .all()
    )


@router.get("/my", response_model=list[PayrollResponse])
def my_payroll(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_payroll_by_employee(current_user.id, current_user, db)


@router.get("/month", response_model=list[PayrollResponse])
def get_payroll_by_month(
    month: int,
    year: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    return (
        db.query(Payroll)
        .filter(Payroll.month == month, Payroll.year == year)
        .order_by(Payroll.employee_id.asc())
        .all()
    )


@router.get("/history")
def payroll_history(
    start_month: int = 1,
    end_month: int = 12,
    year: int = 2026,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    rows = (
        db.query(Payroll, Employee)
        .join(Employee, Payroll.employee_id == Employee.id)
        .filter(
            Payroll.year == year,
            Payroll.month >= start_month,
            Payroll.month <= end_month,
        )
        .order_by(Payroll.year.asc(), Payroll.month.asc(), Employee.id.asc())
        .all()
    )

    return [
        {
            "id": payroll.id,
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "employee_name": employee.name,
            "role": employee.role,
            "month": payroll.month,
            "year": payroll.year,
            "total_days": payroll.total_days,
            "present_days": payroll.present_days,
            "leave_days": payroll.leave_days,
            "absent_days": payroll.absent_days,
            "gross_salary": payroll.gross_salary,
            "total_deductions": payroll.total_deductions,
            "net_salary": payroll.net_salary,
            "processed_at": payroll.processed_at,
        }
        for payroll, employee in rows
    ]


@router.get("/{payroll_id}/payslip")
def download_payslip(
    payroll_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payroll = db.query(Payroll).filter(Payroll.id == payroll_id).first()
    if not payroll:
        raise HTTPException(status_code=404, detail="Payroll not found")

    can_view_employee_payroll(current_user, payroll.employee_id)

    employee = db.query(Employee).filter(Employee.id == payroll.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    payroll.payslip_path = generate_payslip_pdf(employee, payroll)
    db.commit()

    path = payroll.payslip_path.lstrip("/")
    return FileResponse(path, media_type="application/pdf", filename=path.split("/")[-1])
