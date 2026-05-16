const token = localStorage.getItem("token");
const API_BASE = "https://employee-attendance-system-7.onrender.com";

if (!token) {
    window.location.href = "login.html";
}

const currentDate = new Date();

document.addEventListener("DOMContentLoaded", () => {
    setValue("month", currentDate.getMonth() + 1);
    setValue("year", currentDate.getFullYear());
    loadSummary();
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

async function loadSummary() {
    const month = getValue("month");
    const year = getValue("year");

    if (!month || !year) {
        alert("Please enter month and year");
        return;
    }

    try {
        const data = await apiRequest(`/employee/monthly-summary?month=${month}&year=${year}`);
        setText("monthlySummaryPeriod", formatMonthYear(month, year));
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

function formatDayCount(value) {
    const number = Number(value || 0);
    return Number.isInteger(number) ? String(number) : number.toFixed(1);
}

function formatMonthYear(month, year) {
    const date = new Date(Number(year), Number(month) - 1, 1);
    return date.toLocaleDateString(undefined, {
        month: "long",
        year: "numeric"
    });
}
