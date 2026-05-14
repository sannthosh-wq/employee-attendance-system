const token = localStorage.getItem("token");
const API_BASE = "http://127.0.0.1:8000";

if (!token) {
    window.location.href = "login.html";
}

document.addEventListener("DOMContentLoaded", async () => {
    if (await redirectSuperAdminLeavePage()) return;
    setupLeaveForm();
    restoreLeaveMessage();
    loadLeaveBalance();
    loadNotifications();
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

function setupLeaveForm() {
    const form = document.getElementById("leaveForm");
    const reason = document.getElementById("leaveReason");
    const customReason = document.getElementById("customReason");
    const customReasonGroup = document.getElementById("customReasonGroup");
    const fromDate = document.getElementById("fromDate");
    const toDate = document.getElementById("toDate");

    if (!form) return;

    const today = getTodayDateString();
    if (fromDate) fromDate.min = today;
    if (toDate) toDate.min = today;

    reason?.addEventListener("change", () => {
        const isOther = reason.value === "Other";
        customReasonGroup?.classList.toggle("hidden", !isOther);
        if (customReason) {
            customReason.required = isOther;
            if (!isOther) customReason.value = "";
        }
    });

    fromDate?.addEventListener("change", () => {
        if (toDate && fromDate.value) {
            toDate.min = fromDate.value;
        }
        validateDateRange(false);
    });

    toDate?.addEventListener("change", () => validateDateRange(false));
    reason?.addEventListener("pointerdown", positionReasonDropdown);
    reason?.addEventListener("focus", positionReasonDropdown);
    form.addEventListener("submit", applyLeave);
}

function positionReasonDropdown() {
    const reason = document.getElementById("leaveReason");
    if (!reason) return;

    const top = reason.getBoundingClientRect().top + window.scrollY - 160;
    window.scrollTo({
        top: Math.max(top, 0),
        behavior: "smooth"
    });
}

function restoreLeaveMessage() {
    const message = sessionStorage.getItem("leaveSuccessMessage");
    if (!message) return;

    showLeaveMessage(message, "success");
    sessionStorage.removeItem("leaveSuccessMessage");
}

async function applyLeave(event) {
    event?.preventDefault();

    const leave_type = getValue("leaveType");
    const from_date = getValue("fromDate");
    const to_date = getValue("toDate");
    const reason = getValue("leaveReason");
    const custom_reason = getValue("customReason");
    const additional_comments = getValue("additionalComments");

    if (!leave_type || !from_date || !to_date || !reason) {
        showLeaveMessage("Please complete all required leave fields.", "error");
        return;
    }

    if (reason === "Other" && !custom_reason) {
        showLeaveMessage("Please enter a custom reason for Other.", "error");
        return;
    }

    if (!validateDateRange(true)) return;

    try {
        setSubmitting(true);
        const data = await apiRequest("/apply-leave", {
            method: "POST",
            body: JSON.stringify({
                leave_type,
                from_date,
                to_date,
                reason,
                custom_reason: reason === "Other" ? custom_reason : null,
                additional_comments: additional_comments || null
            })
        });

        const warning = data.balance_warning ? `\n\nBalance warning: ${data.balance_warning}` : "";
        const successMessage = `${data.message}. Total days: ${data.total_days}${warning}`;
        showLeaveMessage(successMessage, "success");
        document.getElementById("leaveForm")?.reset();
        document.getElementById("customReasonGroup")?.classList.add("hidden");
        const customReason = document.getElementById("customReason");
        if (customReason) customReason.required = false;
        loadLeaveBalance();
        loadNotifications();
        loadLeaves();
        sessionStorage.setItem("leaveSuccessMessage", successMessage);
        window.location.href = "leave.html#leave-history";
    } catch (error) {
        showLeaveMessage(error.message, "error");
    } finally {
        setSubmitting(false);
    }
}

function validateDateRange(showMessage) {
    const fromDate = getValue("fromDate");
    const toDate = getValue("toDate");
    const today = getTodayDateString();

    if (!fromDate || !toDate) return true;

    if (fromDate < today || toDate < today) {
        if (showMessage) showLeaveMessage("Leave cannot be applied for past dates.", "error");
        return false;
    }

    if (fromDate > toDate) {
        if (showMessage) showLeaveMessage("From Date cannot be greater than To Date.", "error");
        return false;
    }

    return true;
}

async function loadLeaveBalance() {
    const remaining = document.getElementById("leaveBalance");
    if (!remaining) return;

    try {
        const data = await apiRequest("/leave/my-leave-count");
        remaining.innerText = data.remaining_days;
        setText("leaveAllowance", data.allowance);
        setText("leaveUsed", data.approved_days);
        setText("leavePending", data.pending_days);
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
                    <td>${leave.leave_type || "-"}</td>
                    <td>${leave.start_date}</td>
                    <td>${leave.end_date}</td>
                    <td>${formatLeaveReason(leave)}</td>
                    <td>${formatStatus(leave.status)}</td>
                </tr>
            `;
        });

        if (!table.innerHTML) {
            table.innerHTML = `<tr><td colspan="6" class="muted">No leave requests found</td></tr>`;
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

function formatLeaveReason(leave) {
    const reason = escapeHtml(leave.reason || "-");
    if (leave.custom_reason) {
        return `${reason}: ${escapeHtml(leave.custom_reason)}`;
    }
    return reason;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showLeaveMessage(message, type) {
    const element = document.getElementById("leaveMessage");
    if (!element) {
        alert(message);
        return;
    }

    element.textContent = message;
    element.className = `form-message ${type}`;
}

function setSubmitting(isSubmitting) {
    const button = document.getElementById("submitLeaveButton");
    if (!button) return;

    button.disabled = isSubmitting;
    button.textContent = isSubmitting ? "Submitting..." : "Submit Leave Request";
}

function getTodayDateString() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
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
