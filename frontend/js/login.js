let loginType = "employee";
const API_BASE = "http://127.0.0.1:8000";

function setLoginType(type) {
    loginType = type;

    const employeeBtn = document.getElementById("employeeBtn");
    const adminBtn = document.getElementById("adminBtn");

    if (type === "employee") {
        employeeBtn.classList.add("active");
        adminBtn.classList.remove("active");
    } else {
        adminBtn.classList.add("active");
        employeeBtn.classList.remove("active");
    }
}

async function login() {
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    if (!email || !password) {
        showLoginMessage("Please enter email and password.", "error");
        return;
    }

    setLoginLoading(true);

    try {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            showLoginMessage(data.detail || "Login failed. Please try again.", "error");
            return;
        }

        const payload = JSON.parse(atob(data.access_token.split(".")[1]));

        if (loginType === "admin" && !["admin", "super_admin"].includes(payload.role)) {
            showLoginMessage("This is not an admin account.", "error");
            return;
        }

        if (loginType === "employee" && ["admin", "super_admin"].includes(payload.role)) {
            showLoginMessage("Please use Admin Login.", "error");
            return;
        }

        localStorage.setItem("token", data.access_token);
        showLoginMessage("Login successful. Redirecting...", "success");

        window.location.href = ["admin", "super_admin"].includes(payload.role)
            ? "admin.html"
            : "dashboard.html";
    } catch (error) {
        showLoginMessage("Cannot connect to FastAPI. Please make sure http://127.0.0.1:8000 is running.", "error");
    } finally {
        setLoginLoading(false);
    }
}

function showLoginMessage(message, type) {
    const element = document.getElementById("loginMessage");
    if (!element) {
        alert(message);
        return;
    }

    element.textContent = message;
    element.className = `form-message ${type}`;
}

function setLoginLoading(isLoading) {
    const button = document.getElementById("signInButton");
    if (!button) return;

    button.disabled = isLoading;
    button.textContent = isLoading ? "Signing In..." : "Sign In";
}
