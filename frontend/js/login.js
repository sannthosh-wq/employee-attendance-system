let loginType = "employee";   // default

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

    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;

    const response = await fetch("http://127.0.0.1:8000/auth/login", {
        method: "POST",
        headers:{
            "Content-Type":"application/json"
        },
        body: JSON.stringify({
            email,
            password
        })
    });

    const data = await response.json();

    if(response.ok){

        const payload = JSON.parse(atob(data.access_token.split(".")[1]));

        // 🔥 role validation
        if (loginType === "admin" && payload.role !== "admin") {
            alert("This is not an admin account");
            return;
        }

        if (loginType === "employee" && payload.role === "admin") {
            alert("Please use Admin Login");
            return;
        }

        localStorage.setItem("token", data.access_token);

        alert("Login Successful");

        if(payload.role === "admin"){
            window.location.href = "admin.html";
        }
        else{
            window.location.href = "dashboard.html";
        }

    }
    else{
        alert(data.detail);
    }
}