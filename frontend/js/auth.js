function logout(){
    localStorage.removeItem("token");
    window.location.href = "login.html";
}

function togglePassword(inputId, button) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const show = input.type === "password";
    input.type = show ? "text" : "password";
    if (button) {
        button.innerText = show ? "Hide" : "Show";
        button.setAttribute("aria-label", show ? "Hide password" : "Show password");
    }
}
