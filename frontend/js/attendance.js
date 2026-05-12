const token = localStorage.getItem("token");
const API_BASE = "http://127.0.0.1:8000";

if (!token) {
    window.location.href = "login.html";
}

document.addEventListener("DOMContentLoaded", async () => {
    await applyAttendancePageContext();
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
        const data = await apiRequest("/attendance/my-attendance");
        const table = document.getElementById("attendanceTable");

        if (!table) return;

        table.innerHTML = "";

        data.forEach(record => {
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

        if (!table.innerHTML) {
            table.innerHTML = `<tr><td colspan="6" class="muted">No attendance records found</td></tr>`;
        }
    } catch (error) {
        alert(error.message);
    }
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

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.innerText = value;
    }
}
