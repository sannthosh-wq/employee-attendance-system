const employees = [
    { id: 1, name: "Aarav Menon", role: "admin", basic: 52000, hra: 16000, travel: 4500, medical: 3000, special: 6500, present: 24, absent: 1, leave: 1 },
    { id: 2, name: "Priya Shah", role: "admin", basic: 48000, hra: 14500, travel: 4200, medical: 3000, special: 5800, present: 23, absent: 2, leave: 1 },
    { id: 3, name: "Nithin Rao", role: "employee", basic: 34000, hra: 8500, travel: 2500, medical: 1800, special: 3000, present: 25, absent: 0, leave: 1 },
    { id: 4, name: "Amirtha Kumar", role: "employee", basic: 31500, hra: 8200, travel: 2200, medical: 1800, special: 2500, present: 21, absent: 3, leave: 2 },
    { id: 5, name: "Kanimozhi Devi", role: "employee", basic: 30000, hra: 7800, travel: 2200, medical: 1600, special: 2600, present: 18, absent: 5, leave: 3 },
    { id: 6, name: "Sasmitha Iyer", role: "employee", basic: 42000, hra: 12000, travel: 3000, medical: 2400, special: 4200, present: 24, absent: 1, leave: 1 }
];

let salaryHistory = [
    ...employees.map(item => ({ ...item, effectiveFrom: "2026-01-01", active: false })),
    ...employees.map(item => ({ ...item, effectiveFrom: "2026-05-01", active: true }))
];

const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
let currentRole = "super_admin";
let salarySort = { key: "effectiveFrom", dir: "desc" };
let payrollSort = { key: "name", dir: "asc" };

document.addEventListener("DOMContentLoaded", () => {
    setupNavigation();
    setupRoleRendering();
    setupSalaryForm();
    setupPayroll();
    setupTables();
    renderAll();
});

function setupNavigation() {
    const sidebar = document.getElementById("sidebar");
    const shell = document.querySelector(".app-shell");
    document.getElementById("sidebarToggle").addEventListener("click", () => {
        sidebar.classList.toggle("collapsed");
        shell.classList.toggle("sidebar-collapsed");
    });

    document.querySelectorAll(".nav-item").forEach(button => {
        button.addEventListener("click", () => {
            document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
            button.classList.add("active");
            document.getElementById(button.dataset.section)?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
    });

    document.querySelectorAll(".primary-button").forEach(button => {
        button.addEventListener("click", event => {
            const rect = button.getBoundingClientRect();
            button.style.setProperty("--ripple-x", `${event.clientX - rect.left}px`);
            button.style.setProperty("--ripple-y", `${event.clientY - rect.top}px`);
            button.classList.remove("ripple");
            void button.offsetWidth;
            button.classList.add("ripple");
        });
    });
}

function setupRoleRendering() {
    const select = document.getElementById("roleSelect");
    select.addEventListener("change", () => {
        currentRole = select.value;
        renderRoleState();
        renderAll();
        showToast(`Role switched to ${roleLabel(currentRole)}`);
    });
}

function setupSalaryForm() {
    const userSelect = document.getElementById("salaryUser");
    employees.forEach(employee => {
        const option = document.createElement("option");
        option.value = employee.id;
        option.textContent = `${employee.name} - ${roleLabel(employee.role)}`;
        userSelect.appendChild(option);
    });

    document.getElementById("effectiveFrom").value = "2026-06-01";
    document.getElementById("salaryUser").addEventListener("change", () => {
        setSalaryInputs(selectedSalaryUser());
        renderSalaryPreview();
    });

    ["basicSalary", "hra", "travel", "medical", "special"].forEach(id => {
        document.getElementById(id).addEventListener("input", renderSalaryPreview);
    });

    document.getElementById("salaryForm").addEventListener("submit", event => {
        event.preventDefault();
        if (!isSalaryFormValid()) return;

        const selected = selectedSalaryUser();
        const revision = {
            ...selected,
            basic: numberValue("basicSalary"),
            hra: numberValue("hra"),
            travel: numberValue("travel"),
            medical: numberValue("medical"),
            special: numberValue("special"),
            effectiveFrom: document.getElementById("effectiveFrom").value,
            active: true
        };

        salaryHistory = salaryHistory.map(row => row.id === selected.id ? { ...row, active: false } : row);
        salaryHistory.unshift(revision);
        renderSalaryHistory();
        renderPayrollTable();
        renderMetrics();
        showToast("Salary revision added to history");
    });

    const first = employees[0];
    setSalaryInputs(first);
}

function setupPayroll() {
    const monthSelect = document.getElementById("payrollMonth");
    monthNames.forEach((month, index) => {
        const option = document.createElement("option");
        option.value = index + 1;
        option.textContent = month;
        monthSelect.appendChild(option);
    });
    monthSelect.value = "5";
    document.getElementById("payrollYear").value = "2026";

    document.getElementById("processPayrollBtn").addEventListener("click", simulatePayrollProcessing);
    document.getElementById("processQuickBtn").addEventListener("click", simulatePayrollProcessing);
}

function setupTables() {
    document.getElementById("salarySearch").addEventListener("input", renderSalaryHistory);
    document.getElementById("salaryFilter").addEventListener("change", renderSalaryHistory);
    document.getElementById("payrollSearch").addEventListener("input", renderPayrollTable);

    document.querySelectorAll("[data-sort]").forEach(th => {
        th.addEventListener("click", () => {
            salarySort = nextSort(salarySort, th.dataset.sort);
            renderSalaryHistory();
        });
    });

    document.querySelectorAll("[data-payroll-sort]").forEach(th => {
        th.addEventListener("click", () => {
            payrollSort = nextSort(payrollSort, th.dataset.payrollSort);
            renderPayrollTable();
        });
    });
}

function renderAll() {
    renderRoleState();
    renderSalaryPreview();
    renderSalaryHistory();
    renderPayrollTable();
    renderAttendance();
    renderMetrics();
    renderSelfService();
}

function renderRoleState() {
    document.querySelectorAll("[data-super-admin-only]").forEach(element => {
        element.classList.toggle("hidden-by-role", currentRole !== "super_admin");
    });
    document.querySelectorAll("[data-employee-only]").forEach(element => {
        element.classList.toggle("hidden-by-role", currentRole !== "employee");
    });

    const adminReadOnly = currentRole === "admin";
    document.getElementById("processPayrollBtn").disabled = currentRole !== "super_admin";
    document.getElementById("processQuickBtn").disabled = currentRole !== "super_admin";
    document.querySelector(".salary-assignment")?.classList.toggle("hidden-by-role", adminReadOnly || currentRole === "employee");
}

function renderSalaryPreview() {
    const selected = selectedSalaryUser();
    const values = {
        basic: numberValue("basicSalary"),
        hra: numberValue("hra"),
        travel: numberValue("travel"),
        medical: numberValue("medical"),
        special: numberValue("special")
    };
    const total = Object.values(values).reduce((sum, value) => sum + value, 0);

    document.getElementById("previewRole").textContent = roleLabel(selected.role);
    document.getElementById("salaryTotal").textContent = money(total);
    document.getElementById("componentList").innerHTML = [
        ["Basic", values.basic],
        ["HRA", values.hra],
        ["Travel", values.travel],
        ["Medical", values.medical],
        ["Special", values.special]
    ].map(([label, value]) => `<div class="component-row"><span>${label}</span><strong>${money(value)}</strong></div>`).join("");

    validateSalaryForm(selected, values.basic);
}

function validateSalaryForm(selected, basic) {
    const error = document.getElementById("salaryError");
    const button = document.getElementById("assignSalaryBtn");
    const status = document.getElementById("formStatus");
    let message = "";

    if (selected.role === "employee" && basic <= 25000) {
        message = "Employee basic salary must be greater than INR 25,000";
    }
    if (selected.role === "admin" && basic <= 35000) {
        message = "Admin basic salary must be greater than INR 35,000";
    }

    error.textContent = message;
    error.classList.toggle("show", Boolean(message));
    button.disabled = Boolean(message) || currentRole !== "super_admin";
    status.textContent = message ? "Needs attention" : "Valid";
    status.className = `status-pill ${message ? "danger" : "success"}`;
    return !message;
}

function isSalaryFormValid() {
    return validateSalaryForm(selectedSalaryUser(), numberValue("basicSalary"));
}

function renderSalaryHistory() {
    const search = document.getElementById("salarySearch").value.toLowerCase();
    const filter = document.getElementById("salaryFilter").value;
    const body = document.getElementById("salaryHistoryBody");

    const visibleRows = salaryHistory
        .filter(row => currentRole !== "employee" || row.id === 3)
        .filter(row => filter === "all" || row.role === filter)
        .filter(row => `${row.name} ${row.role} ${row.effectiveFrom}`.toLowerCase().includes(search))
        .sort((a, b) => compareSalaryValues(a, b, salarySort));

    body.innerHTML = visibleRows.map(row => `
        <tr>
            <td>${row.name}</td>
            <td>${roleLabel(row.role)}</td>
            <td>${row.effectiveFrom}</td>
            <td>${money(row.basic)}</td>
            <td>${money(totalSalary(row))}</td>
            <td>${row.active ? '<span class="status-pill success">Active</span>' : '<span class="status-pill">Old</span>'}</td>
        </tr>
    `).join("");
}

function renderPayrollTable() {
    const body = document.getElementById("payrollBody");
    const search = document.getElementById("payrollSearch").value.toLowerCase();
    const rows = activeSalaryRows()
        .filter(row => currentRole !== "employee" || row.id === 3)
        .map(row => payrollRow(row))
        .filter(row => `${row.name} ${row.role}`.toLowerCase().includes(search))
        .sort((a, b) => compareValues(a, b, payrollSort));

    body.innerHTML = rows.map(row => `
        <tr>
            <td>${row.name}</td>
            <td>${money(row.basic)}</td>
            <td>${row.present}</td>
            <td>${row.absent}</td>
            <td>${row.leave}</td>
            <td>${money(row.gross)}</td>
            <td>${money(row.deductions)}</td>
            <td><strong>${money(row.net)}</strong></td>
        </tr>
    `).join("");
}

function renderAttendance() {
    const rows = activeSalaryRows().filter(row => currentRole !== "employee" || row.id === 3);
    const present = rows.reduce((sum, row) => sum + row.present, 0);
    const absent = rows.reduce((sum, row) => sum + row.absent, 0);
    const leave = rows.reduce((sum, row) => sum + row.leave, 0);
    const total = present + absent + leave;
    const percentage = total ? Math.round((present / total) * 100) : 0;

    animateCounter(document.querySelector('[data-counter="present"]'), present);
    animateCounter(document.querySelector('[data-counter="absent"]'), absent);
    animateCounter(document.querySelector('[data-counter="leave"]'), leave);
    animateCounter(document.querySelector('[data-counter="percentage"]'), percentage, "%");

    const progress = document.getElementById("attendanceProgress");
    progress.style.width = `${percentage}%`;
    progress.style.background = percentage >= 85 ? "var(--green)" : percentage >= 70 ? "var(--yellow)" : "var(--red)";

    const quality = document.getElementById("attendanceQuality");
    quality.textContent = percentage >= 85 ? "Good" : percentage >= 70 ? "Average" : "Poor";
    quality.className = `status-pill ${percentage >= 85 ? "success" : percentage >= 70 ? "warning" : "danger"}`;
}

function renderMetrics() {
    const rows = activeSalaryRows().filter(row => currentRole !== "employee" || row.id === 3).map(payrollRow);
    const payout = rows.reduce((sum, row) => sum + row.net, 0);
    const attendance = rows.length
        ? Math.round(rows.reduce((sum, row) => sum + (row.present / (row.present + row.absent + row.leave)) * 100, 0) / rows.length)
        : 0;

    document.getElementById("metricPayroll").textContent = money(payout);
    document.getElementById("metricEmployees").textContent = rows.length;
    document.getElementById("metricAttendance").textContent = `${attendance}%`;
    document.getElementById("metricRevisions").textContent = salaryHistory.length;
}

function renderSelfService() {
    const row = payrollRow(activeSalaryRows().find(item => item.id === 3));
    document.getElementById("selfServiceCard").innerHTML = [
        ["Basic Salary", money(row.basic)],
        ["Gross Salary", money(row.gross)],
        ["Deductions", money(row.deductions)],
        ["Net Salary", money(row.net)]
    ].map(([label, value]) => `<div><span>${label}</span><h2>${value}</h2></div>`).join("");
}

function simulatePayrollProcessing() {
    if (currentRole !== "super_admin") {
        showToast(`${roleLabel(currentRole)} can view payroll data only`);
        return;
    }

    const state = document.getElementById("processingState");
    const body = document.getElementById("payrollBody");
    state.classList.add("show");
    body.innerHTML = Array.from({ length: 5 }, () => `
        <tr class="skeleton">
            <td>Loading</td><td>Loading</td><td>Loading</td><td>Loading</td>
            <td>Loading</td><td>Loading</td><td>Loading</td><td>Loading</td>
        </tr>
    `).join("");

    window.setTimeout(() => {
        state.classList.remove("show");
        renderPayrollTable();
        showToast("Payroll processed successfully");
    }, 1100);
}

function activeSalaryRows() {
    const latest = {};
    salaryHistory
        .slice()
        .sort((a, b) => b.effectiveFrom.localeCompare(a.effectiveFrom))
        .forEach(row => {
            if (!latest[row.id]) latest[row.id] = row;
        });
    return Object.values(latest);
}

function payrollRow(row) {
    const gross = totalSalary(row);
    const lossOfPay = Math.round((row.basic / 30) * row.absent);
    const pf = Math.round(row.basic * 0.12);
    const deductions = lossOfPay + pf;
    return {
        ...row,
        gross,
        deductions,
        net: gross - deductions
    };
}

function selectedSalaryUser() {
    return employees.find(employee => String(employee.id) === document.getElementById("salaryUser").value) || employees[0];
}

function setSalaryInputs(employee) {
    document.getElementById("salaryUser").value = employee.id;
    document.getElementById("basicSalary").value = employee.basic;
    document.getElementById("hra").value = employee.hra;
    document.getElementById("travel").value = employee.travel;
    document.getElementById("medical").value = employee.medical;
    document.getElementById("special").value = employee.special;
}

function nextSort(sort, key) {
    return { key, dir: sort.key === key && sort.dir === "asc" ? "desc" : "asc" };
}

function compareValues(a, b, sort) {
    const av = a[sort.key];
    const bv = b[sort.key];
    const result = typeof av === "number" ? av - bv : String(av).localeCompare(String(bv));
    return sort.dir === "asc" ? result : -result;
}

function compareSalaryValues(a, b, sort) {
    if (sort.key === "total") {
        const result = totalSalary(a) - totalSalary(b);
        return sort.dir === "asc" ? result : -result;
    }
    return compareValues(a, b, sort);
}

function totalSalary(row) {
    return row.basic + row.hra + row.travel + row.medical + row.special;
}

function numberValue(id) {
    return Number(document.getElementById(id).value || 0);
}

function money(value) {
    return `INR ${Number(value || 0).toLocaleString("en-IN")}`;
}

function roleLabel(role) {
    return role === "super_admin" ? "Super Admin" : role.charAt(0).toUpperCase() + role.slice(1);
}

function animateCounter(element, target, suffix = "") {
    const start = Number(String(element.textContent).replace(/\D/g, "")) || 0;
    const duration = 650;
    const began = performance.now();

    function tick(now) {
        const progress = Math.min((now - began) / duration, 1);
        const value = Math.round(start + (target - start) * progress);
        element.textContent = `${value}${suffix}`;
        if (progress < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
}

function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
}
