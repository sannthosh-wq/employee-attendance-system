import os
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session

from attendance_logic import employee_monthly_summary
from models import Employee, Payroll, PayrollAllowance, PayrollDeduction, SalaryStructure


COMPANY_NAME = "Employee Attendance System"
PF_PERCENTAGE = Decimal("12")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_salary_amounts(*amounts):
    if any(money(amount) < 0 for amount in amounts):
        raise HTTPException(status_code=400, detail="Salary amounts cannot be negative")


def create_salary_revision(db: Session, salary_data, created_by: int):
    employee = db.query(Employee).filter(Employee.id == salary_data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    validate_salary_amounts(
        salary_data.basic_salary,
        salary_data.hra,
        salary_data.travel_allowance,
        salary_data.medical_allowance,
    )

    db.query(SalaryStructure).filter(
        SalaryStructure.employee_id == salary_data.employee_id,
        SalaryStructure.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)

    salary = SalaryStructure(
        employee_id=salary_data.employee_id,
        basic_salary=money(salary_data.basic_salary),
        hra=money(salary_data.hra),
        travel_allowance=money(salary_data.travel_allowance),
        medical_allowance=money(salary_data.medical_allowance),
        special_allowance=money(getattr(salary_data, "special_allowance", 0)),
        effective_from=salary_data.effective_from,
        created_by=created_by,
        is_active=True,
    )
    db.add(salary)
    db.commit()
    db.refresh(salary)
    return salary


def revise_salary_structure(db: Session, salary_id: int, salary_data, created_by: int):
    current = db.query(SalaryStructure).filter(SalaryStructure.id == salary_id).first()
    if not current:
        raise HTTPException(status_code=404, detail="Salary structure not found")

    revision = SimpleNamespace(
        employee_id=current.employee_id,
        basic_salary=salary_data.basic_salary,
        hra=salary_data.hra,
        travel_allowance=salary_data.travel_allowance,
        medical_allowance=salary_data.medical_allowance,
        special_allowance=getattr(salary_data, "special_allowance", 0),
        effective_from=salary_data.effective_from,
    )
    return create_salary_revision(db, revision, created_by)


def active_salary_for_month(db: Session, employee_id: int, month: int, year: int):
    month_end = date(year, month, 28)
    while True:
        try:
            month_end = month_end.replace(day=month_end.day + 1)
        except ValueError:
            break

    salary = (
        db.query(SalaryStructure)
        .filter(
            SalaryStructure.employee_id == employee_id,
            SalaryStructure.effective_from <= month_end,
        )
        .order_by(SalaryStructure.effective_from.desc(), SalaryStructure.id.desc())
        .first()
    )
    if not salary:
        raise HTTPException(status_code=400, detail=f"Salary structure not assigned for employee {employee_id}")
    return salary


def payroll_components(salary: SalaryStructure, summary: dict, tax_percentage: Decimal):
    basic = money(salary.basic_salary)
    hra = money(salary.hra)
    travel = money(salary.travel_allowance)
    medical = money(salary.medical_allowance)
    absent_days = money(summary.get("absent_days", 0))

    gross = money(basic + hra + travel + medical)
    loss_of_pay = money((basic / Decimal("30")) * absent_days)
    pf = money(basic * PF_PERCENTAGE / Decimal("100"))
    tax = money(gross * money(tax_percentage) / Decimal("100"))
    deductions = money(pf + tax + loss_of_pay)
    net = money(gross - deductions)

    return {
        "basic_salary": basic,
        "hra": hra,
        "travel_allowance": travel,
        "medical_allowance": medical,
        "special_allowance": Decimal("0.00"),
        "gross_salary": gross,
        "overtime_hours": Decimal("0.00"),
        "overtime_pay": Decimal("0.00"),
        "absent_days": absent_days,
        "pf": pf,
        "tax_percentage": money(tax_percentage),
        "tax": tax,
        "loss_of_pay": loss_of_pay,
        "total_deductions": deductions,
        "net_salary": net,
    }


def process_employee_payroll(db: Session, employee: Employee, month: int, year: int, tax_percentage: Decimal, processed_by: int):
    salary = active_salary_for_month(db, employee.id, month, year)
    summary = employee_monthly_summary(db, employee.id, month, year)
    components = payroll_components(salary, summary, tax_percentage)

    payroll = (
        db.query(Payroll)
        .filter(Payroll.employee_id == employee.id, Payroll.month == month, Payroll.year == year)
        .first()
    )
    if not payroll:
        payroll = Payroll(employee_id=employee.id, month=month, year=year)
        db.add(payroll)

    payroll.salary_structure_id = salary.id
    payroll.total_days = monthrange(year, month)[1]
    payroll.working_days = money(summary.get("working_days", 0))
    payroll.present_days = money(summary.get("present_days", 0))
    payroll.leave_days = money(summary.get("approved_leave_days", 0))
    payroll.absent_days = components["absent_days"]
    payroll.overtime_hours = components["overtime_hours"]
    payroll.basic_salary = components["basic_salary"]
    payroll.hra = components["hra"]
    payroll.travel_allowance = components["travel_allowance"]
    payroll.medical_allowance = components["medical_allowance"]
    payroll.special_allowance = components["special_allowance"]
    payroll.gross_salary = components["gross_salary"]
    payroll.overtime_pay = components["overtime_pay"]
    payroll.pf = components["pf"]
    payroll.tax_percentage = components["tax_percentage"]
    payroll.tax = components["tax"]
    payroll.loss_of_pay = components["loss_of_pay"]
    payroll.total_deductions = components["total_deductions"]
    payroll.net_salary = components["net_salary"]
    payroll.processed_by = processed_by
    payroll.processed_at = datetime.utcnow()

    db.query(PayrollAllowance).filter(PayrollAllowance.payroll_id == payroll.id).delete()
    db.query(PayrollDeduction).filter(PayrollDeduction.payroll_id == payroll.id).delete()
    db.flush()

    for name, amount in [
        ("Basic Salary", payroll.basic_salary),
        ("HRA", payroll.hra),
        ("Travel Allowance", payroll.travel_allowance),
        ("Medical Allowance", payroll.medical_allowance),
    ]:
        db.add(PayrollAllowance(payroll_id=payroll.id, name=name, amount=amount))

    for name, amount in [
        ("PF", payroll.pf),
        ("Tax", payroll.tax),
        ("Loss of Pay", payroll.loss_of_pay),
    ]:
        db.add(PayrollDeduction(payroll_id=payroll.id, name=name, amount=amount))

    db.flush()
    payroll.payslip_path = generate_payslip_pdf(employee, payroll)
    return payroll


def process_monthly_payroll(db: Session, month: int, year: int, tax_percentage: Decimal, processed_by: int, employee_id: int | None = None):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")

    query = db.query(Employee).filter(Employee.role != "super_admin")
    if employee_id:
        query = query.filter(Employee.id == employee_id)

    employees = query.order_by(Employee.id.asc()).all()
    if not employees:
        raise HTTPException(status_code=404, detail="No employees found")

    payrolls = [
        process_employee_payroll(db, employee, month, year, tax_percentage, processed_by)
        for employee in employees
    ]
    db.commit()
    for payroll in payrolls:
        db.refresh(payroll)
    return payrolls


def pdf_escape(value) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def generate_simple_pdf(lines: list[str], path: str):
    content = ["BT", "/F1 11 Tf", "50 780 Td"]
    for index, line in enumerate(lines):
        if index:
            content.append("0 -18 Td")
        content.append(f"({pdf_escape(line)}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as output:
        output.write(pdf)


def generate_payslip_pdf(employee: Employee, payroll: Payroll):
    directory = os.path.join("payslips", str(payroll.year), f"{payroll.month:02d}")
    filename = f"payslip-{employee.id}-{payroll.year}-{payroll.month:02d}.pdf"
    path = os.path.join(directory, filename)
    lines = [
        COMPANY_NAME,
        f"Payslip for {payroll.month:02d}-{payroll.year}",
        "",
        f"Employee: {employee.name}",
        f"Employee Code: {employee.employee_code or employee.id}",
        f"Email: {employee.email}",
        f"Role: {employee.role or '-'}",
        "",
        "Earnings",
        f"Basic Salary: {money(payroll.basic_salary)}",
        f"HRA: {money(payroll.hra)}",
        f"Travel Allowance: {money(payroll.travel_allowance)}",
        f"Medical Allowance: {money(payroll.medical_allowance)}",
        f"Gross Salary: {money(payroll.gross_salary)}",
        "",
        "Deductions",
        f"PF: {money(payroll.pf)}",
        f"Tax ({money(payroll.tax_percentage)}%): {money(payroll.tax)}",
        f"Loss of Pay: {money(payroll.loss_of_pay)}",
        f"Total Deductions: {money(payroll.total_deductions)}",
        "",
        f"Net Salary: {money(payroll.net_salary)}",
    ]
    generate_simple_pdf(lines, path)
    return f"/{path.replace(os.sep, '/')}"
