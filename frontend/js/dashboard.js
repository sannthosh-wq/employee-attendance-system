const token = localStorage.getItem("token");
const API_BASE = "http://127.0.0.1:8000";

if (!token) {
    window.location.href = "login.html";
}

const currentDate = new Date();

document.addEventListener("DOMContentLoaded", () => {
    setDefaultMonthYear();

    if (document.getElementById("name") || document.getElementById("todayStatus")) {
        loadDashboard();
    }

    if (document.getElementById("attendanceTable")) {
        loadAttendance();
    }

    if (document.getElementById("workingDays")) {
        loadSummary();
    }
});

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
            ...(options.headers || {})
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.detail || "Something went wrong");
    }

    return data;
}

async function loadDashboard() {
    try {
        const data = await apiRequest("/employee/dashboard");

        setText("name", data.name);
        setText("email", data.email);
        setText("employeeId", "Employee ID: " + data.employee_id);
        setText("role", "Role: " + (data.is_assigned ? formatLabel(data.role) : "Pending Assignment"));
        setText("shift", "Shift: " + (data.is_assigned ? formatLabel(data.shift) : "Pending Assignment"));
        setText("totalAttendanceDays", data.total_attendance_days);
        setText("totalLeaveDays", data.total_approved_leave_days);
        setStatusBadge("todayStatus", data.today_status);
        setVisible("punch", data.is_assigned);
        setVisible("apply-leave", data.is_assigned);
    } catch (error) {
        alert(error.message);
    }
}

async function punchIn() {
    try {
        const data = await apiRequest("/attendance/punch-in", { method: "POST" });

        alert(data.message);
        refreshEmployeeViews();
    } catch (error) {
        alert(error.message);
    }
}

async function punchOut() {
    try {
        const data = await apiRequest("/attendance/punch-out", { method: "POST" });

        alert(data.message);
        refreshEmployeeViews();
    } catch (error) {
        alert(error.message);
    }
}

async function loadAttendance() {
    try {
        const data = await apiRequest("/attendance/my-attendance");
        const table = document.getElementById("attendanceTable");

        if (!table) return;

        table.innerHTML = "";

        const rows = document.getElementById("name") ? data.slice(0, 8) : data;

        rows.forEach(record => {
            const active = !record.logout_time;

            table.innerHTML += `
                <tr>
                    <td>${record.date}</td>
                    <td>${formatDateTime(record.login_time)}</td>
                    <td>${active ? badge("In progress", "warning") : formatDateTime(record.logout_time)}</td>
                    <td>${formatDuration(record.total_hours)}</td>
                    <td>${yesNo(record.is_late)}</td>
                    <td>${active ? "-" : yesNo(record.left_early)}</td>
                </tr>
            `;
        });

        emptyTable(table, 6);
    } catch (error) {
        alert(error.message);
    }
}

async function applyLeave() {
    const start_date = getValue("startDate");
    const end_date = getValue("endDate");
    const reason = getValue("reason");

    if (!start_date || !end_date || !reason) {
        alert("Please fill all leave fields");
        return;
    }

    try {
        const data = await apiRequest("/leave/apply", {
            method: "POST",
            body: JSON.stringify({ start_date, end_date, reason })
        });

        alert(`${data.message}. Total days: ${data.total_days}`);
        setValue("startDate", "");
        setValue("endDate", "");
        setValue("reason", "");
        loadDashboard();
    } catch (error) {
        alert(error.message);
    }
}

async function loadSummary() {
    const month = getValue("month");
    const year = getValue("year");

    if (!month || !year) {
        return;
    }

    try {
        const data = await apiRequest(`/employee/monthly-summary?month=${month}&year=${year}`);
        applySummaryData(data);
    } catch (error) {
        alert(error.message);
    }
}

function applySummaryData(data) {
    if (data.has_data === false) {
        setText("workingDays", "No data");
        setText("leaveDays", "No data");
        setText("effectiveDays", "No data");
        setText("presentDays", "No data");
        setText("absentDays", "No data");
        setText("totalHours", "No data");
        setText("attendancePercentage", "No data");
        return;
    }

    setText("workingDays", data.working_days);
    setText("leaveDays", data.approved_leave_days);
    setText("effectiveDays", data.effective_working_days);
    setText("presentDays", data.present_days);
    setText("absentDays", data.absent_days);
    setText("totalHours", data.total_hours_worked + " hrs");
    setText("attendancePercentage", data.attendance_percentage + "%");
}

function refreshEmployeeViews() {
    loadDashboard();
    loadAttendance();
    loadSummary();
}

function setDefaultMonthYear() {
    if (document.getElementById("month")) {
        document.getElementById("month").value = currentDate.getMonth() + 1;
    }

    if (document.getElementById("year")) {
        document.getElementById("year").value = currentDate.getFullYear();
    }
}

function formatDateTime(value) {
    return value ? new Date(value).toLocaleString() : "-";
}

function formatDuration(value) {
    if (!value) return "-";
    return value.split(".")[0];
}

function statusClass(status) {
    if (status === "Present" || status === "Working (Punched In)") return "success";
    if (status === "On Leave" || status === "Not Marked") return "warning";
    if (status === "Pending Assignment" || status === "Shift Not Started") return "neutral";
    return "danger";
}

function setStatusBadge(id, status) {
    const element = document.getElementById(id);
    if (!element) return;

    element.innerText = status;
    element.className = `badge ${statusClass(status)}`;
}

function badge(text, type) {
    return `<span class="badge ${type}">${text}</span>`;
}

function yesNo(value) {
    return value ? badge("Yes", "warning") : badge("No", "success");
}

function emptyTable(table, columns) {
    if (!table.innerHTML) {
        table.innerHTML = `<tr><td colspan="${columns}" class="muted">No records found</td></tr>`;
    }
}

function formatLabel(value) {
    if (!value) return "-";
    return value
        .split("_")
        .map(part => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
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
    if (element) {
        element.innerText = value;
    }
}

function setVisible(id, visible) {
    const element = document.getElementById(id);
    if (element) {
        element.style.display = visible ? "" : "none";
    }
}
