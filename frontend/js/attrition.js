const token = localStorage.getItem("token");
const API_BASE = "https://employee-attendance-system-7.onrender.com";

if (!token) {
    window.location.href = "login.html";
}

let attritionData = null;
let attritionPieChart = null;
let attritionBarChart = null;
let attritionTrendChart = null;

document.addEventListener("DOMContentLoaded", loadAttritionAnalytics);

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            "Authorization": `Bearer ${token}`,
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

async function loadAttritionAnalytics() {
    setLoading(true);
    try {
        attritionData = await apiRequest("/ml/attrition");
        renderAttritionSummary();
        renderAttritionTable();
        renderAttritionCharts();
        setText("attritionModelStatus", attritionData.model?.model_available ? "Model Active" : "Heuristic Fallback");
    } catch (error) {
        alert(error.message);
    } finally {
        setLoading(false);
    }
}

function setLoading(loading) {
    const element = document.getElementById("attritionLoading");
    if (element) {
        element.style.display = loading ? "inline-flex" : "none";
    }
}

function renderAttritionSummary() {
    const summary = attritionData?.summary || {};
    setText("attritionTotalEmployees", summary.total_employees || 0);
    setText("attritionHighRisk", summary.high_risk_count || 0);
    setText("attritionMediumRisk", summary.medium_risk_count || 0);
    setText("attritionOverallRisk", `${summary.overall_risk_percent || 0}%`);
}

function filteredPredictions() {
    const search = getValue("attritionSearch").toLowerCase();
    const risk = getValue("attritionRiskFilter") || "all";
    return (attritionData?.predictions || []).filter(item => {
        const haystack = `${item.name} ${item.employee_id} ${item.role_encoded}`.toLowerCase();
        const matchesSearch = !search || haystack.includes(search);
        const matchesRisk = risk === "all" || item.risk_level === risk;
        return matchesSearch && matchesRisk;
    });
}

function renderAttritionTable() {
    const table = document.getElementById("attritionTable");
    if (!table) return;

    const rows = filteredPredictions();
    table.innerHTML = rows.map(item => `
        <tr>
            <td>${item.name}<br><span class="muted">ID ${item.employee_id}</span></td>
            <td>${Number(item.attendance_percentage || 0).toFixed(1)}%</td>
            <td>${item.leave_count || 0}</td>
            <td>${item.late_count || 0}</td>
            <td>${Number(item.risk_score || 0).toFixed(1)}%</td>
            <td>${riskBadge(item.risk_level)}</td>
        </tr>
    `).join("");

    setText("attritionTableCount", `${rows.length} Rows`);
    if (!table.innerHTML) {
        table.innerHTML = `<tr><td colspan="6" class="muted">No matching predictions</td></tr>`;
    }
}

function renderAttritionCharts() {
    const predictions = attritionData?.predictions || [];
    const summary = attritionData?.summary || {};

    renderPieChart(summary);
    renderBarChart(predictions.slice(0, 5));
    renderTrendChart(attritionData?.trend || []);
}

function renderPieChart(summary) {
    const ctx = document.getElementById("attritionPieChart");
    if (!ctx || typeof Chart === "undefined") return;
    if (attritionPieChart) attritionPieChart.destroy();

    attritionPieChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["High Risk", "Medium Risk", "Low Risk"],
            datasets: [{
                data: [summary.high_risk_count || 0, summary.medium_risk_count || 0, summary.low_risk_count || 0],
                backgroundColor: ["#ef4444", "#f59e0b", "#16a34a"],
                borderWidth: 0
            }]
        },
        options: chartOptions()
    });
}

function renderBarChart(rows) {
    const ctx = document.getElementById("attritionBarChart");
    if (!ctx || typeof Chart === "undefined") return;
    if (attritionBarChart) attritionBarChart.destroy();

    attritionBarChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: rows.map(item => item.name),
            datasets: [{
                label: "Risk Score",
                data: rows.map(item => item.risk_score),
                backgroundColor: "#ef4444",
                borderRadius: 6
            }]
        },
        options: {
            ...chartOptions(),
            scales: {
                y: { beginAtZero: true, max: 100 }
            }
        }
    });
}

function renderTrendChart(rows) {
    const ctx = document.getElementById("attritionTrendChart");
    if (!ctx || typeof Chart === "undefined") return;
    if (attritionTrendChart) attritionTrendChart.destroy();

    attritionTrendChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: rows.map(item => formatMonth(item.month)),
            datasets: [{
                label: "Average Risk %",
                data: rows.map(item => item.average_risk),
                borderColor: "#3157d5",
                backgroundColor: "rgba(49, 87, 213, 0.16)",
                tension: 0.35,
                fill: true
            }]
        },
        options: {
            ...chartOptions(),
            scales: {
                y: { beginAtZero: true, max: 100 }
            }
        }
    });
}

function chartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 650, easing: "easeOutQuart" },
        plugins: {
            legend: { position: "bottom" }
        }
    };
}

function riskBadge(level) {
    if (level === "High Risk") return `<span class="badge danger">High Risk</span>`;
    if (level === "Medium Risk") return `<span class="badge warning">Medium Risk</span>`;
    return `<span class="badge success">Low Risk</span>`;
}

function formatMonth(value) {
    if (!value) return "-";
    const [year, month] = value.split("-").map(Number);
    return new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

function getValue(id) {
    const element = document.getElementById(id);
    return element ? element.value.trim() : "";
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.innerText = value;
}
