const token = localStorage.getItem("token");
const API_BASE = "http://127.0.0.1:8000";

if (!token) {
    window.location.href = "login.html";
}

document.addEventListener("DOMContentLoaded", async () => {
    if (await redirectSuperAdminLeavePage()) return;
    loadLeaves();
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

async function redirectSuperAdminLeavePage() {
    try {
        const user = await apiRequest("/employee/dashboard");

        if (user.role === "super_admin" && window.location.pathname.endsWith("/admin-leave.html")) {
            window.location.href = "admin.html";
            return true;
        }

        const applyLeaveCard = document.getElementById("apply-leave");
        if (applyLeaveCard && (!user.role || !user.shift)) {
            applyLeaveCard.style.display = "none";
        }
    } catch (error) {
        alert(error.message);
    }

    return false;
}

async function applyLeave() {
    const start_date = getValue("startDate");
    const end_date = getValue("endDate");
    const reason = getValue("reason");

    if (!start_date || !end_date || !reason) {
        alert("Please fill all fields");
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
        loadLeaves();
    } catch (error) {
        alert(error.message);
    }
}

async function loadLeaves() {
    try {
        const data = await apiRequest("/leave/my-leaves");
        const table = document.getElementById("leaveTable");

        if (!table) return;

        table.innerHTML = "";

        data.forEach(leave => {
            table.innerHTML += `
                <tr>
                    <td>${leave.id}</td>
                    <td>${leave.start_date}</td>
                    <td>${leave.end_date}</td>
                    <td>${leave.reason}</td>
                    <td>${formatStatus(leave.status)}</td>
                </tr>
            `;
        });

        if (!table.innerHTML) {
            table.innerHTML = `<tr><td colspan="5" class="muted">No leave requests found</td></tr>`;
        }
    } catch (error) {
        alert(error.message);
    }
}

function formatStatus(status) {
    if (status === "approved") return `<span class="badge success">Approved</span>`;
    if (status === "rejected") return `<span class="badge danger">Rejected</span>`;
    return `<span class="badge warning">Pending</span>`;
}

function getValue(id) {
    const element = document.getElementById(id);
    return element ? element.value.trim() : "";
}

function setValue(id, value) {
    const element = document.getElementById(id);
    if (element) element.value = value;
}
