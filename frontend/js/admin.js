const token = localStorage.getItem("token");

if (!token) {
    window.location.href = "login.html";
}

loadDashboard();
loadEmployees();


// ================= DASHBOARD =================

async function loadDashboard() {

    const response = await fetch("http://127.0.0.1:8000/admin/dashboard", {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json();

    document.getElementById("totalEmployees").innerText = data.total_employees;

    document.getElementById("presentToday").innerText = data.present_today;

    document.getElementById("onLeaveToday").innerText = data.on_leave_today;

    document.getElementById("absentToday").innerText = data.absent_today;

    document.getElementById("pendingLeaves").innerText = data.pending_leave_requests;
}



// ================= EMPLOYEES =================

async function loadEmployees() {

    const response = await fetch("http://127.0.0.1:8000/admin/employees", {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    const employees = await response.json();

    const table = document.getElementById("employeeTable");

    table.innerHTML = "";

    employees.forEach(emp => {

        table.innerHTML += `
        
        <tr>

            <td>${emp.id}</td>

            <td>${emp.name}</td>

            <td>${emp.email}</td>

            <td>${emp.role}</td>

            <td>${emp.shift}</td>

            <td>

                <button onclick="changeShift(${emp.id})">
                    Change Shift
                </button>

                <br><br>

                <button onclick="deleteEmployee(${emp.id})">
                    Delete
                </button>

            </td>

        </tr>
        
        `;
    });

}



// ================= CHANGE SHIFT =================

async function changeShift(id) {

    const shift = prompt("Enter shift: morning or night");

    if (!shift) return;

    const response = await fetch(`http://127.0.0.1:8000/admin/employee/${id}/shift`, {

        method: "PUT",

        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
        },

        body: JSON.stringify({
            shift: shift
        })
    });

    const data = await response.json();

    alert(data.message);

    loadEmployees();
}



// ================= DELETE EMPLOYEE =================

async function deleteEmployee(id) {

    const confirmDelete = confirm("Delete employee?");

    if (!confirmDelete) return;

    const response = await fetch(`http://127.0.0.1:8000/admin/employee/${id}`, {

        method: "DELETE",

        headers: {
            "Authorization": `Bearer ${token}`
        }

    });

    const data = await response.json();

    alert(data.message);

    loadEmployees();
}

async function updateRole() {

    const id = document.getElementById("employeeId").value;

    const role = document.getElementById("role").value;

    if (!id || !role) {
        alert("Enter employee ID and role");
        return;
    }

    const response = await fetch(
        `http://127.0.0.1:8000/admin/employee/${id}/role`,
        {
            method: "PUT",

            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },

            body: JSON.stringify({
                role: role
            })
        }
    );

    const data = await response.json();

    alert(data.message);

    loadEmployees();
}

async function updateShift() {

    const id = document.getElementById("employeeId").value;

    const shift = document.getElementById("shift").value;

    if (!id || !shift) {
        alert("Enter employee ID and shift");
        return;
    }

    const response = await fetch(
        `http://127.0.0.1:8000/admin/employee/${id}/shift`,
        {
            method: "PUT",

            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },

            body: JSON.stringify({
                shift: shift
            })
        }
    );

    const data = await response.json();

    alert(data.message);

    loadEmployees();
}

async function loadChart() {

    const response = await fetch("http://127.0.0.1:8000/admin/dashboard", {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json();

    const ctx = document.getElementById("attendanceChart");

    new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["Present", "On Leave", "Absent"],
            datasets: [{
                data: [
                    data.present_today,
                    data.on_leave_today,
                    data.absent_today
                ],
                backgroundColor: [
                    "#22c55e",
                    "#f59e0b",
                    "#ef4444"
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: "bottom"
                }
            }
        }
    });
}

loadChart();

async function loadLeaves() {

    const response = await fetch("http://127.0.0.1:8000/leave/all", {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json();

    const table = document.getElementById("leaveTable");

    table.innerHTML = "";

    data.forEach(leave => {

        table.innerHTML += `
        <tr>
            <td>${leave.id}</td>
            <td>${leave.employee_id}</td>
            <td>${leave.start_date}</td>
            <td>${leave.end_date}</td>
            <td>${leave.reason}</td>
            <td>${formatStatus(leave.status)}</td>

            <td>
                <button onclick="updateLeave(${leave.id}, 'approved')">Approve</button>
                <button onclick="updateLeave(${leave.id}, 'rejected')">Reject</button>
            </td>
        </tr>
        `;
    });
}

async function updateLeave(id, status) {

    const response = await fetch(`http://127.0.0.1:8000/leave/${id}`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
            status: status
        })
    });

    const data = await response.json();

    alert(data.message);

    loadLeaves();
}

function formatStatus(status) {

    if (status === "approved") {
        return `<span style="color:green;font-weight:bold;">Approved</span>`;
    }

    if (status === "rejected") {
        return `<span style="color:red;font-weight:bold;">Rejected</span>`;
    }

    return `<span style="color:orange;font-weight:bold;">Pending</span>`;
}

loadLeaves();