const token = localStorage.getItem("token");

async function loadDashboard(){

    const response = await fetch("http://127.0.0.1:8000/employee/dashboard",{
        headers:{
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json();

    document.getElementById("name").innerText = data.name;
    document.getElementById("email").innerText = data.email;
    document.getElementById("role").innerText = "Role: " + data.role;
    document.getElementById("shift").innerText = "Shift: " + data.shift;
}

async function punchIn(){

    const response = await fetch("http://127.0.0.1:8000/attendance/punch-in",{
        method:"POST",
        headers:{
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json();

    alert(data.message);
}

async function punchOut(){

    const response = await fetch("http://127.0.0.1:8000/attendance/punch-out",{
        method:"POST",
        headers:{
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json();

    alert(data.message);
}

loadDashboard();