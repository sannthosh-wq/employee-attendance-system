import os
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .attendance_logic import employee_monthly_summary
from .models import Employee, Payroll, PayrollAllowance, PayrollDeduction, SalaryStructure


COMPANY_NAME = "Employee Attendance System"
PF_PERCENTAGE = Decimal("12")
EMPLOYEE_MIN_BASIC_SALARY = Decimal("25000")
ADMIN_MIN_BASIC_SALARY = Decimal("35000")
ADMIN_ROLES = {"admin"}
PROTECTED_ROLES = {"admin", "super_admin"}
ROLE_SALARY_COMPONENTS = {
    "admin": {
        "basic_salary": Decimal("50000"),
        "hra": Decimal("15000"),
        "travel_allowance": Decimal("4000"),
        "medical_allowance": Decimal("3000"),
        "special_allowance": Decimal("8000"),
    },
    "software_engineer": {
        "basic_salary": Decimal("42000"),
        "hra": Decimal("12000"),
        "travel_allowance": Decimal("3500"),
        "medical_allowance": Decimal("2500"),
        "special_allowance": Decimal("6000"),
    },
    "backend_developer": {
        "basic_salary": Decimal("40000"),
        "hra": Decimal("11000"),
        "travel_allowance": Decimal("3200"),
        "medical_allowance": Decimal("2400"),
        "special_allowance": Decimal("5400"),
    },
    "frontend_developer": {
        "basic_salary": Decimal("38000"),
        "hra": Decimal("10500"),
        "travel_allowance": Decimal("3000"),
        "medical_allowance": Decimal("2200"),
        "special_allowance": Decimal("5000"),
    },
    "ml_developer": {
        "basic_salary": Decimal("43000"),
        "hra": Decimal("12500"),
        "travel_allowance": Decimal("3500"),
        "medical_allowance": Decimal("2600"),
        "special_allowance": Decimal("6500"),
    },
    "data_scientist": {
        "basic_salary": Decimal("45000"),
        "hra": Decimal("13000"),
        "travel_allowance": Decimal("3500"),
        "medical_allowance": Decimal("2700"),
        "special_allowance": Decimal("7000"),
    },
    "data_analyst": {
        "basic_salary": Decimal("36000"),
        "hra": Decimal("9500"),
        "travel_allowance": Decimal("2800"),
        "medical_allowance": Decimal("2000"),
        "special_allowance": Decimal("4200"),
    },
    "developer": {
        "basic_salary": Decimal("35000"),
        "hra": Decimal("9500"),
        "travel_allowance": Decimal("2800"),
        "medical_allowance": Decimal("2000"),
        "special_allowance": Decimal("4200"),
    },
}
DEFAULT_EMPLOYEE_SALARY_COMPONENTS = {
    "basic_salary": Decimal("30000"),
    "hra": Decimal("8000"),
    "travel_allowance": Decimal("2000"),
    "medical_allowance": Decimal("1500"),
    "special_allowance": Decimal("3000"),
}


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def salary_components_for_role(role: str | None) -> dict[str, Decimal]:
    return ROLE_SALARY_COMPONENTS.get(role or "", DEFAULT_EMPLOYEE_SALARY_COMPONENTS)


def validate_salary_amounts(*amounts):
    if any(money(amount) < 0 for amount in amounts):
        raise HTTPException(status_code=400, detail="Salary amounts cannot be negative")


def salary_total(salary_data) -> Decimal:
    return money(
        money(salary_data.basic_salary)
        + money(salary_data.hra)
        + money(salary_data.travel_allowance)
        + money(salary_data.medical_allowance)
        + money(getattr(salary_data, "special_allowance", 0))
    )


def validate_salary_assignment_permissions(assigner: Employee, target: Employee, basic_salary: Decimal):
    target_role = target.role

    if target.employment_type == "intern" and (target.intern_months or 0) < 3:
        raise HTTPException(status_code=400, detail="Salary cannot be assigned to interns below 3 months")

    if assigner.role == "admin":
        if target_role in PROTECTED_ROLES:
            raise HTTPException(status_code=403, detail="Admin can assign salary only to employees")
        if money(basic_salary) <= EMPLOYEE_MIN_BASIC_SALARY:
            raise HTTPException(status_code=400, detail="Employee basic salary must be greater than 25000")
        return

    if assigner.role == "super_admin":
        if target_role not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Super admin can assign salary only to admins")
        if money(basic_salary) <= ADMIN_MIN_BASIC_SALARY:
            raise HTTPException(status_code=400, detail="Admin basic salary must be greater than 35000")
        return

    raise HTTPException(status_code=403, detail="Only admin or super admin can assign salary")


def create_salary_revision(db: Session, salary_data, created_by: int, current_user: Employee | None = None):
    employee = db.query(Employee).filter(Employee.id == salary_data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    assigner = current_user or db.query(Employee).filter(Employee.id == created_by).first()
    if not assigner:
        raise HTTPException(status_code=403, detail="Authenticated user not found")

    validate_salary_amounts(
        salary_data.basic_salary,
        salary_data.hra,
        salary_data.travel_allowance,
        salary_data.medical_allowance,
        getattr(salary_data, "special_allowance", 0),
    )
    validate_salary_assignment_permissions(assigner, employee, salary_data.basic_salary)

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
        total_salary=salary_total(salary_data),
        effective_from=salary_data.effective_from,
        created_by=created_by,
        is_active=True,
    )
    db.add(salary)
    db.commit()
    db.refresh(salary)
    return salary


def revise_salary_structure(db: Session, salary_id: int, salary_data, created_by: int, current_user: Employee | None = None):
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
    return create_salary_revision(db, revision, created_by, current_user)


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
    special = money(getattr(salary, "special_allowance", 0))
    absent_days = money(summary.get("absent_days", 0))

    gross = money(basic + hra + travel + medical + special)
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
        "special_allowance": special,
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


def process_monthly_payroll(
    db: Session,
    month: int,
    year: int,
    tax_percentage: Decimal,
    processed_by: int,
    employee_id: int | None = None,
    processor_role: str | None = None,
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")

    query = db.query(Employee)
    if employee_id:
        query = query.filter(Employee.id == employee_id)
    elif processor_role != "super_admin":
        query = query.filter(Employee.id != processed_by)

    if processor_role != "super_admin":
        query = query.filter(Employee.role != "super_admin")

    employees = query.order_by(Employee.id.asc()).all()
    if not employees:
        raise HTTPException(status_code=404, detail="No employees found")

    if processor_role != "super_admin":
        if any(employee.id == processed_by for employee in employees):
            raise HTTPException(status_code=403, detail="Admins cannot process payroll for themselves")
        if any(employee.role == "super_admin" for employee in employees):
            raise HTTPException(status_code=403, detail="Only super admin can process super admin payroll")

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


def pdf_text(text: str, x: int, y: int, size: int = 10, font: str = "F1") -> str:
    return f"BT /{font} {size} Tf {x} {y} Td ({pdf_escape(text)}) Tj ET"


def pdf_line(x1: int, y1: int, x2: int, y2: int) -> str:
    return f"{x1} {y1} m {x2} {y2} l S"


def pdf_rect(x: int, y: int, width: int, height: int, fill: bool = False) -> str:
    return f"{x} {y} {width} {height} re {'f' if fill else 'S'}"


def generate_company_payslip_pdf(employee: Employee, payroll: Payroll, path: str):
    earnings = [
        ("Basic Salary", payroll.basic_salary),
        ("HRA", payroll.hra),
        ("Travel Allowance", payroll.travel_allowance),
        ("Medical Allowance", payroll.medical_allowance),
        ("Special Allowance", payroll.special_allowance),
    ]
    deductions = [
        ("Provident Fund", payroll.pf),
        (f"Tax ({money(payroll.tax_percentage)}%)", payroll.tax),
        ("Loss of Pay", payroll.loss_of_pay),
    ]

    payslip_id = f"PAY-{payroll.year}-{payroll.month:02d}-{payroll.employee_id}"
    processed_on = payroll.processed_at.date() if payroll.processed_at else "-"

    content = [
        "0.06 0.10 0.18 rg",
        pdf_rect(0, 744, 595, 98, True),
        "0.04 0.48 0.46 rg",
        pdf_rect(0, 744, 9, 98, True),
        "1 1 1 rg",
        pdf_text(COMPANY_NAME, 42, 808, 20, "F2"),
        pdf_text("Company Payroll Department", 42, 789, 10),
        pdf_text("Official Salary Advice and Receipt", 42, 773, 12, "F2"),
        "0.87 0.95 0.93 rg",
        pdf_rect(402, 790, 126, 28, True),
        "0 0 0 RG 0.06 0.10 0.18 rg",
        pdf_text("EMPLOYEE COPY", 422, 800, 10, "F2"),
        "0.94 0.97 1 rg",
        pdf_rect(42, 684, 511, 42, True),
        "0 0 0 RG 0 0 0 rg",
        pdf_text(f"Payslip ID: {payslip_id}", 58, 711, 9, "F2"),
        pdf_text(f"Pay Period: {payroll.month:02d}-{payroll.year}", 238, 711, 9, "F2"),
        pdf_text(f"Issue Date: {processed_on}", 402, 711, 9, "F2"),
        pdf_text("This document confirms salary processed and received from the company payroll system.", 58, 694, 8),
        pdf_text("Employee Information", 42, 656, 13, "F2"),
        pdf_rect(42, 560, 511, 78),
        pdf_text(f"Name: {employee.name}", 58, 615, 10),
        pdf_text(f"Employee Code: {employee.employee_code or employee.id}", 58, 595, 10),
        pdf_text(f"Email: {employee.email}", 58, 575, 10),
        pdf_text(f"Role: {(employee.role or '-').replace('_', ' ').title()}", 330, 615, 10),
        pdf_text(f"Working Days: {payroll.total_days}", 330, 595, 10),
        pdf_text(f"Present / Leave / Absent: {payroll.present_days} / {payroll.leave_days} / {payroll.absent_days}", 330, 575, 10),
        pdf_text("Earnings", 42, 532, 13, "F2"),
        pdf_text("Deductions", 322, 532, 13, "F2"),
        "0.98 0.99 1 rg",
        pdf_rect(42, 380, 230, 136, True),
        pdf_rect(322, 380, 230, 136, True),
        "0.76 0.82 0.90 RG 0 0 0 rg",
        pdf_rect(42, 380, 230, 136),
        pdf_rect(322, 380, 230, 136),
    ]

    y = 494
    for label, amount in earnings:
        content.append(pdf_text(label, 58, y, 9))
        content.append(pdf_text(f"INR {money(amount)}", 184, y, 9))
        y -= 22

    y = 494
    for label, amount in deductions:
        content.append(pdf_text(label, 338, y, 9))
        content.append(pdf_text(f"INR {money(amount)}", 462, y, 9))
        y -= 22

    content.extend([
        pdf_line(58, 402, 256, 402),
        pdf_line(338, 402, 536, 402),
        pdf_text("Gross Earnings", 58, 386, 10, "F2"),
        pdf_text(f"INR {money(payroll.gross_salary)}", 174, 386, 10, "F2"),
        pdf_text("Total Deductions", 338, 386, 10, "F2"),
        pdf_text(f"INR {money(payroll.total_deductions)}", 454, 386, 10, "F2"),
        "0.86 0.96 0.93 rg",
        pdf_rect(42, 292, 511, 60, True),
        "0 0 0 RG 0 0 0 rg",
        pdf_text("Net Salary Received from Company", 58, 328, 10, "F2"),
        pdf_text(f"INR {money(payroll.net_salary)}", 58, 307, 20, "F2"),
        "0.94 0.97 1 rg",
        pdf_rect(42, 210, 511, 52, True),
        "0 0 0 RG 0 0 0 rg",
        pdf_text("Payroll Acknowledgement", 58, 241, 10, "F2"),
        pdf_text("Salary has been processed through the official company payroll records for the stated pay period.", 58, 224, 8),
        pdf_text("This is a system generated payslip and does not require a physical signature.", 58, 170, 9),
        pdf_text("For payroll queries, contact HR Operations with the Payslip ID above.", 58, 154, 9),
        pdf_line(42, 118, 220, 118),
        pdf_line(375, 118, 553, 118),
        pdf_text("HR Operations", 84, 100, 9, "F2"),
        pdf_text("Employee Copy", 422, 100, 9, "F2"),
        pdf_line(42, 72, 553, 72),
        pdf_text(f"{COMPANY_NAME} | Confidential Company Payroll Document | {payslip_id}", 42, 52, 8),
    ])
    stream = "\n".join(content).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
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
    generate_company_payslip_pdf(employee, payroll, path)
    return f"/{path.replace(os.sep, '/')}"
