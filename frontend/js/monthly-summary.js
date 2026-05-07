const token = localStorage.getItem("token");

if (!token) {
    window.location.href = "login.html";
}


// ================= LOAD SUMMARY =================

async function loadSummary() {

    const month = document.getElementById("month").value;

    const year = document.getElementById("year").value;

    if (!month || !year) {
        alert("Please enter month and year");
        return;
    }

    const response = await fetch(
        `http://127.0.0.1:8000/employee/monthly-summary?month=${month}&year=${year}`,
        {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        }
    );

    const data = await response.json();

    if (!response.ok) {
        alert(data.detail);
        return;
    }

    document.getElementById("workingDays").innerText =
        data.working_days;

    document.getElementById("leaveDays").innerText =
        data.approved_leave_days;

    document.getElementById("effectiveDays").innerText =
        data.effective_working_days;

    document.getElementById("presentDays").innerText =
        data.present_days;

    document.getElementById("absentDays").innerText =
        data.absent_days;

    document.getElementById("totalHours").innerText =
        data.total_hours_worked + " hrs";

    document.getElementById("attendancePercentage").innerText =
        data.attendance_percentage + "%";
}