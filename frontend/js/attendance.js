const token = localStorage.getItem("token");
const API_BASE = "http://127.0.0.1:8000";
let activeEmployeeAttendanceFilter = "date";

if (!token) {
    window.location.href = "login.html";
}

document.addEventListener("DOMContentLoaded", async () => {
    await applyAttendancePageContext();
    setupAttendanceFilters();
    loadAttendance();
});

async function apiRequest(path) {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.detail || "Something went wrong");
    }

    return data;
}

async function applyAttendancePageContext() {
    try {
        const data = await apiRequest("/employee/dashboard");
        if (data.employment_type !== "intern") return;

        document.title = "Intern Attendance History";
        document.querySelectorAll(".employee-dashboard-label").forEach(element => {
            element.innerText = "Intern Dashboard";
        });
        document.querySelectorAll(".employee-attendance-label").forEach(element => {
            element.innerText = "Intern Attendance History";
        });
        document.querySelectorAll(".employee-leave-label").forEach(element => {
            element.innerText = "Intern Apply Leave";
        });
        setText("attendancePageTitle", "Intern Attendance History");
        setText("attendancePageSubtitle", "Your internship punch in and punch out records.");
    } catch (error) {
        alert(error.message);
    }
}

async function loadAttendance() {
    try {
        const query = employeeAttendanceQuery();
        const data = await apiRequest(`/attendance/my-attendance${query}`);
        const table = document.getElementById("attendanceTable");

        if (!table) return;

        table.innerHTML = "";

        data.forEach(record => {
            const active = Boolean(record.login_time && !record.logout_time);
            const holiday = record.status === "Holiday";

            table.innerHTML += `
                <tr>
                    <td>${record.date}</td>
                    <td>${attendanceStatusBadge(record)}</td>
                    <td>${formatDateTime(record.login_time)}</td>
                    <td>${active ? badge("In progress", "warning") : formatDateTime(record.logout_time)}</td>
                    <td>${formatDuration(record.total_hours)}</td>
                    <td>${holiday ? "-" : record.is_late ? badge(`${record.late_minutes || 0} min`, "warning") : badge("No", "success")}</td>
                    <td>${holiday || active ? "-" : yesNo(record.left_early)}</td>
                </tr>
            `;
        });

        setText("employeeAttendanceRecordCount", `${data.length} ${data.length === 1 ? "Record" : "Records"}`);
        emptyAttendanceTable(table);
    } catch (error) {
        alert(error.message);
    }
}

function setupAttendanceFilters() {
    if (!document.getElementById("employeeAttendanceDate")) return;

    const now = new Date();
    setValue("employeeAttendanceDate", formatInputDate(now));
    setValue("employeeAttendanceMonth", `${now.getFullYear()}-${pad2(now.getMonth() + 1)}`);
    setValue("employeeAttendanceYear", now.getFullYear());
    updateAttendanceFilterControls();
}

function filterEmployeeAttendance(mode) {
    activeEmployeeAttendanceFilter = mode;
    updateAttendanceFilterControls();
    loadAttendance();
}

function updateAttendanceFilterControls() {
    const labels = {
        date: "Date",
        month: "Month",
        year: "Year"
    };

    setText("employeeAttendanceFilterLabel", labels[activeEmployeeAttendanceFilter]);

    setButtonActive("employeeAttendanceDateBtn", activeEmployeeAttendanceFilter === "date");
    setButtonActive("employeeAttendanceMonthBtn", activeEmployeeAttendanceFilter === "month");
    setButtonActive("employeeAttendanceYearBtn", activeEmployeeAttendanceFilter === "year");

    setVisible("employeeAttendanceDateField", activeEmployeeAttendanceFilter === "date");
    setVisible("employeeAttendanceMonthField", activeEmployeeAttendanceFilter === "month");
    setVisible("employeeAttendanceYearField", activeEmployeeAttendanceFilter === "year");
}

function employeeAttendanceQuery() {
    const range = selectedAttendanceRange();

    if (!range.startDate || !range.endDate) {
        return "";
    }

    return `?${new URLSearchParams({
        start_date: range.startDate,
        end_date: range.endDate
    }).toString()}`;
}

function selectedAttendanceRange() {
    if (activeEmployeeAttendanceFilter === "date") {
        const selectedDate = getValue("employeeAttendanceDate");
        return { startDate: selectedDate, endDate: selectedDate };
    }

    if (activeEmployeeAttendanceFilter === "month") {
        const selectedMonth = getValue("employeeAttendanceMonth");
        if (!selectedMonth) return {};

        const [year, month] = selectedMonth.split("-").map(Number);
        const lastDay = new Date(year, month, 0).getDate();

        return {
            startDate: `${year}-${pad2(month)}-01`,
            endDate: `${year}-${pad2(month)}-${pad2(lastDay)}`
        };
    }

    const selectedYear = Number(getValue("employeeAttendanceYear"));
    if (!selectedYear) return {};

    return {
        startDate: `${selectedYear}-01-01`,
        endDate: `${selectedYear}-12-31`
    };
}

function formatDateTime(value) {
    return value ? new Date(value).toLocaleString() : "-";
}

function formatDuration(value) {
    if (!value) return "-";
    return value.split(".")[0];
}

function badge(text, type) {
    return `<span class="badge ${type}">${text}</span>`;
}

function yesNo(value) {
    return value ? badge("Yes", "warning") : badge("No", "success");
}

function attendanceStatusBadge(record) {
    const status = record.status || (record.login_time ? "Present" : "-");
    return status === "-" ? "-" : badge(status, statusClass(status));
}

function statusClass(status) {
    if (status === "Present" || status === "Working (Punched In)") return "success";
    if (status === "On Leave" || status === "Leave") return "warning";
    if (status === "Pending Assignment" || status === "Shift Not Started" || status === "No Attendance" || status === "Holiday" || status === "Extra Work") return "neutral";
    return "danger";
}

function getValue(id) {
    const element = document.getElementById(id);
    return element ? element.value.trim() : "";
}

function setValue(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.value = value;
    }
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

function setButtonActive(id, active) {
    const element = document.getElementById(id);
    if (element) {
        element.classList.toggle("active", active);
    }
}

function emptyAttendanceTable(table) {
    if (!table.innerHTML) {
        table.innerHTML = `<tr><td colspan="7" class="muted">No attendance records found</td></tr>`;
    }
}

function formatInputDate(value) {
    return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}`;
}

function pad2(value) {
    return String(value).padStart(2, "0");
}
