const token = localStorage.getItem("token");

if (!token) {
    window.location.href = "login.html";
}

loadLeaves();


// ================= APPLY LEAVE =================

async function applyLeave() {

    const start_date = document.getElementById("startDate").value;

    const end_date = document.getElementById("endDate").value;

    const reason = document.getElementById("reason").value;

    if (!start_date || !end_date || !reason) {
        alert("Please fill all fields");
        return;
    }

    const response = await fetch(
        "http://127.0.0.1:8000/leave/apply",
        {
            method: "POST",

            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },

            body: JSON.stringify({
                start_date,
                end_date,
                reason
            })
        }
    );

    const data = await response.json();

    if (response.ok) {

        alert(data.message);

        document.getElementById("startDate").value = "";

        document.getElementById("endDate").value = "";

        document.getElementById("reason").value = "";

        loadLeaves();

    } else {

        alert(data.detail);
    }
}



// ================= LOAD LEAVES =================

async function loadLeaves() {

    const response = await fetch(
        "http://127.0.0.1:8000/leave/my-leaves",
        {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        }
    );

    const data = await response.json();

    const table = document.getElementById("leaveTable");

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
}



// ================= STATUS COLOR =================

function formatStatus(status) {

    if (status === "approved") {
        return `<span style="color:green;font-weight:bold;">Approved</span>`;
    }

    if (status === "rejected") {
        return `<span style="color:red;font-weight:bold;">Rejected</span>`;
    }

    return `<span style="color:orange;font-weight:bold;">Pending</span>`;
}