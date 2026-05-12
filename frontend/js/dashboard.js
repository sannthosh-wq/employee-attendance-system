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
    const isFormData = options.body instanceof FormData;
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            "Authorization": `Bearer ${token}`,
            ...(isFormData ? {} : { "Content-Type": "application/json" }),
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
        applyInternLabels(data);

        setText("name", data.name);
        setText("email", data.email);
        setText("employeeId", `${data.employment_type === "intern" ? "Intern" : "Employee"} ID: ${data.employee_code || data.employee_id}`);
        setText("role", "Role: " + (data.is_assigned ? formatLabel(data.role) : "Pending Assignment"));
        setText("shift", "Shift: " + (data.is_assigned ? formatLabel(data.shift) : "Pending Assignment"));
        setText("employmentType", "Employment Type: " + formatLabel(data.employment_type));
        setText("totalAttendanceDays", data.total_attendance_days);
        setText("totalLeaveDays", data.total_approved_leave_days);
        setText("leaveBalance", data.leave_balance?.remaining_days ?? 0);
        setText("leaveAllowance", data.leave_balance?.allowance ?? 0);
        setText("leaveUsed", data.leave_balance?.approved_days ?? 0);
        setProfilePhoto(data.profile_photo);
        setStatusBadge("todayStatus", data.today_status);
        const canStartWork = data.today_status !== "Joined Today - Work Starts Tomorrow";
        setVisible("punch", data.is_assigned && canStartWork);
        setVisible("apply-leave", data.is_assigned && canStartWork);
        loadNotifications();
    } catch (error) {
        alert(error.message);
    }
}

function applyInternLabels(data) {
    const isIntern = data.employment_type === "intern";
    if (!isIntern) return;

    document.title = document.title.replace("Employee", "Intern");
    document.querySelectorAll(".employee-dashboard-label").forEach(element => {
        element.innerText = "Intern Dashboard";
    });
    document.querySelectorAll(".employee-attendance-label").forEach(element => {
        element.innerText = "Intern Attendance History";
    });
    document.querySelectorAll(".employee-leave-label").forEach(element => {
        element.innerText = "Intern Apply Leave";
    });

    setText("dashboardTitle", "Intern Dashboard");
    setText("dashboardSubtitle", "Track your internship profile, attendance, leave, and monthly summary.");
    setText("employeeId", "Intern ID: " + (data.employee_code || data.employee_id));
    setText("attendanceHistoryTitle", "Intern Attendance History");
    setText("applyLeaveTitle", "Apply Leave");
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
                    <td>${record.is_late ? badge(`${record.late_minutes || 0} min`, "warning") : badge("No", "success")}</td>
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

async function uploadProfilePhoto() {
    const input = document.getElementById("profilePhotoInput");
    if (!input || !input.files.length) {
        alert("Choose a profile photo first");
        return;
    }

    const formData = new FormData();
    formData.append("photo", input.files[0]);

    try {
        const data = await apiRequest("/employee/profile-photo", {
            method: "POST",
            body: formData
        });

        alert(data.message);
        setProfilePhoto(data.profile_photo);
        input.value = "";
    } catch (error) {
        alert(error.message);
    }
}

async function loadNotifications() {
    const list = document.getElementById("notificationList");
    if (!list) return;

    try {
        const data = await apiRequest("/notifications/my");
        setText("notificationCount", `${data.unread_count} Unread`);
        list.innerHTML = "";

        data.notifications.forEach(item => {
            list.innerHTML += `
                <li class="${item.read_at ? "" : "unread-notification"}" onclick="openNotification(${item.id})">
                    <div>
                        ${item.title}
                        <span>${item.read_at ? item.message : "Unread - click to view"}</span>
                    </div>
                    <button class="danger compact-button" onclick="deleteNotification(event, ${item.id})">Delete</button>
                </li>
            `;
        });

        if (!list.innerHTML) {
            list.innerHTML = `<li class="muted">No notifications</li>`;
        }
    } catch (error) {
        alert(error.message);
    }
}

async function openNotification(id) {
    try {
        const item = await apiRequest(`/notifications/detail/${id}`);
        alert(`${item.title}\n\n${item.message}`);
        loadNotifications();
    } catch (error) {
        alert(error.message);
    }
}

async function deleteNotification(event, id) {
    event.stopPropagation();

    if (!confirm("Delete this notification?")) {
        return;
    }

    try {
        const data = await apiRequest(`/notifications/${id}`, { method: "DELETE" });
        alert(data.message);
        loadNotifications();
    } catch (error) {
        alert(error.message);
    }
}

function setProfilePhoto(path) {
    const image = document.getElementById("profilePhoto");
    if (!image) return;

    image.src = path ? `${API_BASE}${path}` : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'%3E%3Crect width='120' height='120' fill='%23d8f6f2'/%3E%3Ccircle cx='60' cy='44' r='24' fill='%230b7a75'/%3E%3Cpath d='M20 110c6-28 26-42 40-42s34 14 40 42' fill='%233157d5'/%3E%3C/svg%3E";
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
        setText("extraWork", "No data");
        setText("totalHours", "No data");
        setText("attendancePercentage", "No data");
        return;
    }

    setText("workingDays", data.working_days);
    setText("leaveDays", data.approved_leave_days);
    setText("effectiveDays", data.effective_working_days);
    setText("presentDays", formatDayCount(data.present_days));
    setText("absentDays", formatDayCount(data.absent_days));
    setText("extraWork", `${data.extra_work_days || 0} days / ${data.extra_work_hours || 0} hrs`);
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

function formatDayCount(value) {
    const number = Number(value || 0);
    return Number.isInteger(number) ? String(number) : number.toFixed(1);
}

function statusClass(status) {
    if (status === "Present" || status === "Working (Punched In)") return "success";
    if (status === "On Leave" || status === "Not Marked" || status === "Joined Today - Work Starts Tomorrow") return "warning";
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
