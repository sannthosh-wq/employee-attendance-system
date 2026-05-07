const token = localStorage.getItem("token");

if (!token) {
    window.location.href = "login.html";
}

loadAttendance();


// ================= LOAD ATTENDANCE =================

async function loadAttendance() {

    const response = await fetch(
        "http://127.0.0.1:8000/attendance/my-attendance",
        {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        }
    );

    const data = await response.json();

    const table = document.getElementById("attendanceTable");

    table.innerHTML = "";

    data.forEach(record => {

        const loginTime = record.login_time
            ? new Date(record.login_time).toLocaleString()
            : "-";

        const logoutTime = record.logout_time
            ? new Date(record.logout_time).toLocaleString()
            : "-";

        let totalHours = "-";

        if (record.total_hours) {

            totalHours = formatDuration(record.total_hours);
        }

        table.innerHTML += `

        <tr>

            <td>${record.date}</td>

            <td>${loginTime}</td>

            <td>${logoutTime}</td>

            <td>${totalHours}</td>

            <td>${record.is_late ? "Yes" : "No"}</td>

            <td>${record.left_early ? "Yes" : "No"}</td>

        </tr>

        `;
    });
}



// ================= FORMAT DURATION =================

function formatDuration(duration) {

    /*
        Example backend format:
        "08:30:25"
    */

    return duration;
}