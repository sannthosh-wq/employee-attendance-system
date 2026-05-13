const token = localStorage.getItem("token");
const API_BASE = "http://127.0.0.1:8001";

if (!token) {
    window.location.href = "login.html";
}

let payrollEmployees = [];
let payrollCurrentUser = null;

document.addEventListener("DOMContentLoaded", async () => {
    setDefaultPayrollPeriod();

    if (document.getElementById("salaryEmployee")) {
        await loadPayrollCurrentUser();
        await loadPayrollEmployees();
        await loadSalaryHistory();
        await loadAllAssignedSalaries();
        await loadAllPayrollRecords();
        await loadPayrollHistory();
    }

    if (document.getElementById("myPayrollTable")) {
        await loadMyPayroll();
    }
});

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.detail || "Something went wrong");
    }
    return data;
}

async function loadPayrollCurrentUser() {
    try {
        payrollCurrentUser = await apiRequest("/employee/dashboard");
    } catch (error) {
        alert(error.message);
    }
}

async function loadPayrollEmployees() {
    try {
        payrollEmployees = await apiRequest("/admin/employees");
        const salarySelect = document.getElementById("salaryEmployee");
        const payrollSelect = document.getElementById("payrollEmployee");

        const canProcessAll = payrollCurrentUser?.role === "super_admin";
        const processableEmployees = payrollEmployees
            .filter(emp => canProcessAll || emp.role !== "super_admin")
            .filter(emp => canProcessAll || Number(emp.id) !== Number(payrollCurrentUser?.employee_id));
        const salaryEmployees = payrollEmployees.filter(emp => {
            if (emp.employment_type === "intern" && Number(emp.intern_months || 0) < 3) {
                return false;
            }
            if (payrollCurrentUser?.role === "super_admin") {
                return emp.role === "admin";
            }
            return emp.role !== "admin" && emp.role !== "super_admin";
        });

        const salaryOptions = salaryEmployees
            .map(emp => `<option value="${emp.id}">${emp.employee_code || emp.id} - ${emp.name}</option>`)
            .join("");
        const payrollOptions = processableEmployees
            .map(emp => `<option value="${emp.id}">${emp.employee_code || emp.id} - ${emp.name}</option>`)
            .join("");

        if (salarySelect) {
            salarySelect.innerHTML = salaryOptions || `<option value="">No employees</option>`;
        }

        if (payrollSelect) {
            payrollSelect.innerHTML = `<option value="">All Employees</option>${payrollOptions}`;
        }
    } catch (error) {
        alert(error.message);
    }
}

async function assignSalary() {
    const employee_id = Number(getValue("salaryEmployee"));
    const effective_from = getValue("salaryEffectiveFrom");

    if (!employee_id || !effective_from) {
        alert("Select employee and effective date");
        return;
    }

    const payload = {
        employee_id,
        basic_salary: numberValue("basicSalary"),
        hra: numberValue("hra"),
        travel_allowance: numberValue("travelAllowance"),
        medical_allowance: numberValue("medicalAllowance"),
        special_allowance: numberValue("specialAllowance"),
        effective_from
    };

    if (payload.basic_salary <= 0) {
        alert("Basic salary must be greater than 0");
        return;
    }

    try {
        await apiRequest("/payroll/salary", {
            method: "POST",
            body: JSON.stringify(payload)
        });
        alert("Salary assigned successfully");
        clearSalaryForm(false);
        await loadSalaryHistory();
        await loadAllAssignedSalaries();
    } catch (error) {
        alert(error.message);
    }
}

async function loadSalaryHistory() {
    const employeeId = getValue("salaryEmployee");
    const table = document.getElementById("salaryHistoryTable");
    if (!employeeId || !table) return;

    try {
        const rows = await apiRequest(`/payroll/salary/employee/${employeeId}`);
        table.innerHTML = "";

        rows.forEach(item => {
            table.innerHTML += `
                <tr>
                    <td>${item.effective_from}</td>
                    <td>${formatMoney(item.basic_salary)}</td>
                    <td>${formatMoney(item.hra)}</td>
                    <td>${formatMoney(item.travel_allowance)}</td>
                    <td>${formatMoney(item.medical_allowance)}</td>
                    <td>${formatMoney(item.special_allowance)}</td>
                    <td>${formatMoney(item.total_salary)}</td>
                    <td>${item.is_active ? badge("Active", "success") : badge("Old", "neutral")}</td>
                </tr>
            `;
        });

        setText("salaryHistoryCount", `${rows.length} Records`);
        emptyTable(table, 8);
    } catch (error) {
        alert(error.message);
    }
}

async function loadAllAssignedSalaries() {
    const table = document.getElementById("allSalaryTable");
    if (!table) return;

    try {
        const rows = await apiRequest("/payroll/salary");
        table.innerHTML = "";

        rows.forEach(item => {
            table.innerHTML += `
                <tr>
                    <td>${item.employee_name}<br><span class="muted">${item.employee_code || item.employee_id}</span></td>
                    <td>${formatLabel(item.role)}</td>
                    <td>${item.effective_from}</td>
                    <td>${formatMoney(item.basic_salary)}</td>
                    <td>${formatMoney(item.hra)}</td>
                    <td>${formatMoney(item.travel_allowance)}</td>
                    <td>${formatMoney(item.medical_allowance)}</td>
                    <td>${formatMoney(item.special_allowance)}</td>
                    <td>${formatMoney(item.total_salary)}</td>
                    <td>${item.is_active ? badge("Active", "success") : badge("Old", "neutral")}</td>
                </tr>
            `;
        });

        setText("allSalaryCount", `${rows.length} Records`);
        emptyTable(table, 10);
    } catch (error) {
        alert(error.message);
    }
}

async function processPayroll() {
    const month = Number(getValue("payrollMonth"));
    const year = Number(getValue("payrollYear"));
    const employee_id = getValue("payrollEmployee");

    if (!month || !year) {
        alert("Enter payroll month and year");
        return;
    }

    if (
        payrollCurrentUser?.role === "admin"
        && employee_id
        && Number(employee_id) === Number(payrollCurrentUser.employee_id)
    ) {
        alert("Admins cannot process payroll for themselves");
        return;
    }

    const payload = {
        month,
        year,
        tax_percentage: numberValue("taxPercentage")
    };

    if (employee_id) {
        payload.employee_id = Number(employee_id);
    }

    try {
        const rows = await apiRequest("/payroll/process", {
            method: "POST",
            body: JSON.stringify(payload)
        });
        alert(`Payroll processed for ${rows.length} employee(s)`);
        renderPayrollRows(rows, "payrollTable", "payrollCount");
        await loadPayrollHistory();
    } catch (error) {
        alert(error.message);
    }
}

async function loadPayrollMonth() {
    const month = Number(getValue("payrollMonth"));
    const year = Number(getValue("payrollYear"));
    if (!month || !year || !document.getElementById("payrollTable")) return;

    try {
        const rows = await apiRequest(`/payroll/month?month=${month}&year=${year}`);
        renderPayrollRows(rows, "payrollTable", "payrollCount");
    } catch (error) {
        alert(error.message);
    }
}

async function loadAllPayrollRecords() {
    const table = document.getElementById("payrollTable");
    if (!table) return;

    try {
        const rows = await apiRequest("/payroll/history?start_month=1&end_month=4&year=2026");
        renderPayrollRows(rows, "payrollTable", "payrollCount");
    } catch (error) {
        alert(error.message);
    }
}

async function loadPayrollHistory() {
    const table = document.getElementById("payrollHistoryTable");
    if (!table) return;

    try {
        const rows = await apiRequest("/payroll/history?start_month=1&end_month=4&year=2026");
        table.innerHTML = "";

        rows.forEach(item => {
            table.innerHTML += `
                <tr>
                    <td>${item.employee_name}<br><span class="muted">${item.employee_code || item.employee_id}</span></td>
                    <td>${formatLabel(item.role)}</td>
                    <td>${pad2(item.month)}-${item.year}</td>
                    <td>${item.total_days}</td>
                    <td>${item.present_days}</td>
                    <td>${item.leave_days}</td>
                    <td>${item.absent_days}</td>
                    <td>${formatMoney(item.gross_salary)}</td>
                    <td>${formatMoney(item.total_deductions)}</td>
                    <td>${formatMoney(item.net_salary)}</td>
                    <td>${formatDateTime(item.processed_at)}</td>
                </tr>
            `;
        });

        setText("payrollHistoryCount", `${rows.length} Records`);
        emptyTable(table, 11);
    } catch (error) {
        alert(error.message);
    }
}

function renderPayrollRows(rows, tableId, countId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    table.innerHTML = "";
    rows.forEach(item => {
        table.innerHTML += `
            <tr>
                <td>${employeeLabel(item.employee_id)}</td>
                <td>${pad2(item.month)}-${item.year}</td>
                <td>${item.total_days}</td>
                <td>${item.present_days}</td>
                <td>${item.leave_days}</td>
                <td>${item.absent_days}</td>
                <td>${formatMoney(item.gross_salary)}</td>
                <td>${formatMoney(item.total_deductions)}</td>
                <td>${formatMoney(item.net_salary)}</td>
                <td>${formatDateTime(item.processed_at)}</td>
                <td><button onclick="downloadPayslip(${item.id})">Download</button></td>
            </tr>
        `;
    });

    setText(countId, `${rows.length} Records`);
    emptyTable(table, 11);
}

async function loadMyPayroll() {
    try {
        const rows = await apiRequest("/payroll/my");
        const table = document.getElementById("myPayrollTable");
        if (!table) return;

        table.innerHTML = "";
        rows.forEach(item => {
            table.innerHTML += `
                <tr>
                    <td>${pad2(item.month)}-${item.year}</td>
                    <td>${item.total_days}</td>
                    <td>${item.present_days}</td>
                    <td>${item.leave_days}</td>
                    <td>${item.absent_days}</td>
                    <td>${formatMoney(item.gross_salary)}</td>
                    <td>${formatMoney(item.pf)}</td>
                    <td>${formatMoney(item.tax)}</td>
                    <td>${formatMoney(item.loss_of_pay)}</td>
                    <td>${formatMoney(item.net_salary)}</td>
                    <td><button onclick="downloadPayslip(${item.id})">Download</button></td>
                </tr>
            `;
        });

        const latest = rows[0];
        setText("myPayrollCount", `${rows.length} Records`);
        setText("payrollRecordTotal", rows.length);
        setText("latestNetSalary", latest ? formatMoney(latest.net_salary) : "0");
        setText("latestGrossSalary", latest ? formatMoney(latest.gross_salary) : "0");
        setText("latestDeductions", latest ? formatMoney(latest.total_deductions) : "0");
        emptyTable(table, 11);
    } catch (error) {
        alert(error.message);
    }
}

async function downloadPayslip(payrollId) {
    try {
        const response = await fetch(`${API_BASE}/payroll/${payrollId}/payslip`, {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || "Could not download payslip");
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `payslip-${payrollId}.pdf`;
        link.click();
        URL.revokeObjectURL(url);
    } catch (error) {
        alert(error.message);
    }
}

function setDefaultPayrollPeriod() {
    setValue("salaryEffectiveFrom", formatInputDate(new Date()));
    setValue("payrollMonth", 1);
    setValue("payrollYear", 2026);
}

function clearSalaryForm(clearEmployee = true) {
    if (clearEmployee) setValue("salaryEmployee", "");
    setValue("basicSalary", "");
    setValue("hra", "");
    setValue("travelAllowance", "");
    setValue("medicalAllowance", "");
    setValue("specialAllowance", "");
}

function employeeLabel(employeeId) {
    const employee = payrollEmployees.find(emp => Number(emp.id) === Number(employeeId));
    return employee ? `${employee.employee_code || employee.id} - ${employee.name}` : employeeId;
}

function formatMoney(value) {
    const number = Number(value || 0);
    return number.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatLabel(value) {
    return value ? String(value).replaceAll("_", " ") : "-";
}

function formatDateTime(value) {
    return value ? new Date(value).toLocaleString() : "-";
}

function formatInputDate(value) {
    return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}`;
}

function numberValue(id) {
    return Number(getValue(id) || 0);
}

function badge(text, type) {
    return `<span class="badge ${type}">${text}</span>`;
}

function emptyTable(table, columns) {
    if (!table.innerHTML) {
        table.innerHTML = `<tr><td colspan="${columns}" class="muted">No records found</td></tr>`;
    }
}

function pad2(value) {
    return String(value).padStart(2, "0");
}

function getValue(id) {
    const element = document.getElementById(id);
    return element ? element.value.trim() : "";
}

function setValue(id, value) {
    const element = document.getElementById(id);
    if (element) element.value = value;
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.innerText = value;
}
