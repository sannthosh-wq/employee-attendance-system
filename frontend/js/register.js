async function register() {

    const name = document.getElementById("name").value;
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;
    const employment_type = document.getElementById("employmentType").value;

    const response = await fetch("https://employee-attendance-system-7.onrender.com/auth/register", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            name,
            email,
            password,
            employment_type
        })
    });

    const data = await response.json();

    if(response.ok){
        alert(`Registration Successful. Employee ID: ${data.employee_code}`);
        window.location.href = "login.html";
    }
    else{
        alert(data.detail);
    }
}
