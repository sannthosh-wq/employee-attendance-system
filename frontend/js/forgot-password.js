const API_BASE = "http://127.0.0.1:8000";

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.detail || "Something went wrong");
    }

    return data;
}

async function requestReset() {
    const email = getValue("email");

    if (!email) {
        alert("Enter your email");
        return;
    }

    try {
        const data = await apiRequest("/auth/forgot-password", {
            method: "POST",
            body: JSON.stringify({ email })
        });

        setValue("resetToken", data.reset_token);
        setVisible("resetPanel", true);
        alert(`${data.message}. Code expires in ${data.expires_in_minutes} minutes.`);
    } catch (error) {
        alert(error.message);
    }
}

async function resetPassword() {
    const email = getValue("email");
    const token = getValue("resetToken");
    const new_password = getValue("newPassword");

    if (!email || !token || !new_password) {
        alert("Enter email, reset code, and new password");
        return;
    }

    try {
        const data = await apiRequest("/auth/reset-password", {
            method: "POST",
            body: JSON.stringify({ email, token, new_password })
        });

        alert(data.message);
        window.location.href = "login.html";
    } catch (error) {
        alert(error.message);
    }
}

function getValue(id) {
    const element = document.getElementById(id);
    return element ? element.value.trim() : "";
}

function setValue(id, value) {
    const element = document.getElementById(id);
    if (element) element.value = value;
}

function setVisible(id, visible) {
    const element = document.getElementById(id);
    if (element) {
        element.style.display = visible ? "" : "none";
    }
}
