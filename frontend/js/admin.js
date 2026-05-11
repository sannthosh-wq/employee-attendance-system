const token = localStorage.getItem("token");
const API_BASE = "http://127.0.0.1:8000";

if (!token) {
    window.location.href = "login.html";
}

let employees = [];
let todayStatuses = {};
let allAttendanceRecords = [];
let attendanceChart = null;
let monthlyAttendanceChart = null;
let attendanceTrendChart = null;
let hoursTrendChart = null;
let lateEarlyChart = null;
let shiftSplitChart = null;
let employeeHoursChart = null;
let currentAdmin = null;
let activeStatusFilter = "all";
let activeEmployeeShiftFilter = "all";
let activeSummaryShift = "morning";
let activeAttendanceFilter = "day";
const LOW_ATTENDANCE_THRESHOLD = 70;

document.addEventListener("DOMContentLoaded", async () => {
    await loadCurrentAdminContext();
    applyRoleBasedUi();

    const isAttendanceAnalyticsPage = Boolean(document.getElementById("analyticsMonth"));

    activeSummaryShift = getCurrentSummaryShift();
    setupAttendanceHistoryFilters();
    setupAdminMonthlySummary();

    if (document.getElementById("adminName") || document.getElementById("adminTodayStatus")) {
        loadAdminProfile();
    }

    if (!isAttendanceAnalyticsPage && ((document.getElementById("totalEmployees") && !document.getElementById("todayShiftFilter")) || document.getElementById("attendanceChart"))) {
        loadDashboard();
    }

    if (document.getElementById("morningTotal")) {
        loadShiftSummary();
    }

    setupAttendanceAnalytics();

    if (document.getElementById("employeeTable") || document.getElementById("presentList")) {
        loadEmployees();
    }

    if (document.getElementById("allAttendanceTable")) {
        loadAllAttendance();
    }

    if (document.getElementById("adminOwnAttendanceTable")) {
        loadAdminAttendanceHistory();
    }

    if (document.getElementById("leaveTable")) {
        loadLeaves();
    }
});

async function loadCurrentAdminContext() {
    try {
        currentAdmin = await apiRequest("/employee/dashboard");
    } catch (error) {
        alert(error.message);
    }
}

function applyRoleBasedUi() {
    if (!currentAdmin) return;

    if (currentAdmin.role === "super_admin") {
        document.querySelectorAll('a[href="admin-punch.html"], a[href="admin-leave.html"]').forEach(link => {
            link.style.display = "none";
        });

        if (["/admin-punch.html", "/admin-leave.html"].some(path => window.location.pathname.endsWith(path))) {
            window.location.href = "admin.html";
            return;
        }

        setVisible("admin-punch", false);
        setVisible("adminRole", false);
        setVisible("adminShift", false);
        setVisible("adminMonthlySummarySection", false);
        setVisible("adminOwnAttendanceSection", false);
        setVisible("superAdminOwnAttendanceNote", true);
    }
}

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

async function loadAdminProfile() {
    try {
        const data = currentAdmin || await apiRequest("/employee/dashboard");

        setText("adminName", data.name);
        setText("adminEmail", data.email);
        setText("adminId", "Admin ID: " + data.employee_id);
        if (data.role !== "super_admin") {
            setText("adminRole", "Role: " + formatLabel(data.role));
            setText("adminShift", "Shift: " + formatLabel(data.shift));
        }
        setText("adminTotalAttendanceDays", data.total_attendance_days);
        setText("adminApprovedLeaveDays", data.total_approved_leave_days);
        setStatusBadge("adminTodayStatus", data.today_status);
    } catch (error) {
        alert(error.message);
    }
}

async function loadDashboard() {
    try {
        const data = await apiRequest("/admin/dashboard");

        setText("totalEmployees", data.total_employees);
        setText("presentToday", data.present_today);
        setText("onLeaveToday", data.on_leave_today);
        setText("absentToday", data.absent_today);
        setText("pendingLeaves", data.pending_leave_requests);
        setText("pendingAssignments", `${data.pending_assignment_requests || 0} Pending`);
        setText("monthlyAttendanceRecords", data.monthly_attendance_records);
        setText("monthlyWorkingHours", data.monthly_total_working_hours + " hrs");

        if (document.getElementById("attendanceChart") && !document.getElementById("todayShiftFilter")) {
            renderChart(data);
        }

        loadOnboardingNotifications();
    } catch (error) {
        alert(error.message);
    }
}

async function loadOnboardingNotifications() {
    const list = document.getElementById("onboardingNotificationList");
    if (!list) return;

    try {
        const data = await apiRequest("/admin/onboarding-notifications");
        setText("pendingAssignments", `${data.total} Pending`);
        list.innerHTML = "";

        data.notifications.forEach(item => {
            list.innerHTML += `
                <li>
                    ${item.message}
                    <span>${item.email} - Joined ${formatDate(item.joined_at)}</span>
                </li>
            `;
        });

        emptyList(list);
    } catch (error) {
        alert(error.message);
    }
}

async function loadShiftSummary() {
    try {
        const data = await apiRequest("/admin/shift-summary");
        const morning = data.shifts.morning;
        const night = data.shifts.night;

        setText("morningTotal", morning.total);
        setText("morningPresent", morning.present_today);
        setText("morningAbsent", morning.absent_today);
        setText("morningLeave", morning.on_leave_today);

        setText("nightTotal", night.total);
        setText("nightPresent", night.present_today);
        setText("nightAbsent", night.absent_today);
        setText("nightLeave", night.on_leave_today);

        updateFilteredTodaySummary(data.shifts);
    } catch (error) {
        alert(error.message);
    }
}

async function punchIn() {
    try {
        const data = await apiRequest("/attendance/punch-in", { method: "POST" });

        alert(data.message);
        refreshAdminDashboard();
    } catch (error) {
        alert(error.message);
    }
}

async function punchOut() {
    try {
        const data = await apiRequest("/attendance/punch-out", { method: "POST" });

        alert(data.message);
        refreshAdminDashboard();
    } catch (error) {
        alert(error.message);
    }
}

async function loadEmployees() {
    try {
        const [employeeData, statusData] = await Promise.all([
            apiRequest("/admin/employees"),
            apiRequest("/admin/today-status")
        ]);

        employees = employeeData;
        todayStatuses = {};

        statusData.employees.forEach(item => {
            todayStatuses[item.employee_id] = item;
        });

        renderEmployees();
        renderTodayLists(statusData.employees);
    } catch (error) {
        alert(error.message);
    }
}

function renderEmployees() {
    const table = document.getElementById("employeeTable");
    const searchInput = document.getElementById("employeeSearch");
    const search = searchInput ? searchInput.value.toLowerCase() : "";

    if (!table) return;

    table.innerHTML = "";

    employees
        .filter(emp => matchesSearch(emp, search))
        .filter(emp => matchesStatus(emp))
        .filter(emp => matchesEmployeeShift(emp))
        .forEach(emp => {
            const status = employeeStatus(emp);
            const managementActions = document.getElementById("employeeId")
                ? `<button onclick="fillEmployee(${emp.id})">Edit</button>`
                : "";
            const deleteAction = canDeleteEmployee(emp)
                ? `<button class="danger" onclick="deleteEmployee(${emp.id})">Delete</button>`
                : `<span class="muted">Protected</span>`;

            table.innerHTML += `
                <tr>
                    <td>${emp.id}</td>
                    <td>${emp.name}</td>
                    <td>${emp.email}</td>
                    <td>${formatLabel(emp.role)}</td>
                    <td>${formatLabel(emp.shift)}</td>
                    <td>${formatDate(emp.joined_at)}</td>
                    <td>${badge(status, statusClass(status))}</td>
                    <td>
                        ${managementActions}
                        ${deleteAction}
                    </td>
                </tr>
            `;
        });

    emptyTable(table, 8);
}

async function loadAdminAttendanceHistory() {
    const table = document.getElementById("adminOwnAttendanceTable");
    if (!table) return;

    try {
        const data = await apiRequest("/attendance/my-attendance");

        table.innerHTML = "";

        data.forEach(record => {
            const active = !record.logout_time;

            table.innerHTML += `
                <tr>
                    <td>${record.date}</td>
                    <td>${formatDateTime(record.login_time)}</td>
                    <td>${active ? badge("In progress", "warning") : formatDateTime(record.logout_time)}</td>
                    <td>${formatDuration(record.total_hours)}</td>
                    <td>${yesNo(record.is_late)}</td>
                    <td>${active ? "-" : yesNo(record.left_early)}</td>
                </tr>
            `;
        });

        setText("adminAttendanceCount", `${data.length} Records`);
        emptyTable(table, 6);
    } catch (error) {
        alert(error.message);
    }
}

function setupAttendanceAnalytics() {
    if (!document.getElementById("analyticsMonth")) return;

    const now = new Date();
    setValue("analyticsDate", formatInputDate(now));
    setValue("analyticsMonth", now.getMonth() + 1);
    setValue("analyticsYear", now.getFullYear());
    loadAttendanceAnalytics();
}

async function loadAttendanceAnalytics() {
    if (!document.getElementById("analyticsMonth")) return;

    const month = getValue("analyticsMonth");
    const year = getValue("analyticsYear");
    const selectedDate = getValue("analyticsDate") || formatInputDate(new Date());

    if (!month || !year || !selectedDate) return;

    try {
        const [dailySummary, employeeData, attendanceRecords, monthlyReport, warnings] = await Promise.all([
            loadDailyAnalyticsSummary(selectedDate),
            apiRequest("/admin/employees"),
            apiRequest("/admin/attendance"),
            apiRequest(`/admin/monthly-attendance-report?month=${month}&year=${year}`),
            loadLowAttendanceWarnings(month, year)
        ]);

        employees = employeeData;
        allAttendanceRecords = attendanceRecords;
        populateAnalyticsEmployeeFilter();
        renderAnalyticsDashboard(dailySummary, monthlyReport, warnings, attendanceRecords);
    } catch (error) {
        alert(error.message);
    }
}

async function loadDailyAnalyticsSummary(selectedDate) {
    try {
        return await apiRequest(`/admin/daily-attendance-summary?selected_date=${selectedDate}`);
    } catch (error) {
        const today = formatInputDate(new Date());
        if (selectedDate !== today) {
            throw error;
        }

        const [dashboard, shiftData] = await Promise.all([
            apiRequest("/admin/dashboard"),
            apiRequest("/admin/shift-summary")
        ]);

        return {
            date: dashboard.date,
            total_employees: dashboard.total_employees,
            present_today: dashboard.present_today,
            absent_today: dashboard.absent_today,
            on_leave_today: dashboard.on_leave_today,
            shifts: shiftData.shifts
        };
    }
}

async function loadLowAttendanceWarnings(month, year) {
    try {
        return await apiRequest(`/admin/low-attendance-warning?month=${month}&year=${year}&threshold=${LOW_ATTENDANCE_THRESHOLD}`);
    } catch (error) {
        return {
            month,
            year,
            threshold: LOW_ATTENDANCE_THRESHOLD,
            total_warnings: 0,
            employees: []
        };
    }
}

function renderAnalyticsDashboard(dailySummary, monthlyReport, warnings, attendanceRecords) {
    setText("analyticsDateLabel", dailySummary.date || "Selected Day");
    setText("analyticsTotalLabel", `${dailySummary.total_employees} Employees`);
    setText("analyticsMonthLabel", `${pad2(monthlyReport.month)}-${monthlyReport.year}`);

    const model = buildAnalyticsModel(monthlyReport.report, attendanceRecords, monthlyReport.month, monthlyReport.year);

    setText("totalEmployees", dailySummary.total_employees);
    setText("presentToday", dailySummary.present_today);
    setText("absentToday", dailySummary.absent_today);
    setText("onLeaveToday", dailySummary.on_leave_today);
    setText("monthlyAttendanceRecords", model.records.length);
    setText("monthlyWorkingHours", formatHours(model.records.reduce((sum, record) => sum + durationToHours(record.total_hours), 0)));

    const morning = dailySummary.shifts.morning;
    const night = dailySummary.shifts.night;

    setText("analyticsMorningPresent", morning.present_today);
    setText("analyticsMorningTotal", `${morning.total} employees`);
    setText("analyticsNightPresent", night.present_today);
    setText("analyticsNightTotal", `${night.total} employees`);

    renderChart(dailySummary);
    renderAnalyticsScorecards(model);
    renderMonthlyAttendanceChart(model.report);
    renderBestAttendance(model.report);
    renderLowAttendanceWarnings(filterWarningData(warnings));
    renderAttendanceTrendChart(model.daily);
    renderHoursTrendChart(model.daily);
    renderLateEarlyChart(model);
    renderShiftSplitChart(model.report);
    renderEmployeeAnalytics(model);
    renderAnalyticsDetailTable(model.report, model.employeeStats);
}

function changeAnalyticsDate() {
    const selectedDate = parseRecordDate(getValue("analyticsDate"));
    if (selectedDate) {
        setValue("analyticsMonth", selectedDate.getMonth() + 1);
        setValue("analyticsYear", selectedDate.getFullYear());
    }

    loadAttendanceAnalytics();
}

function changeAnalyticsMonthYear() {
    const month = Number(getValue("analyticsMonth"));
    const year = Number(getValue("analyticsYear"));
    const selectedDate = parseRecordDate(getValue("analyticsDate")) || new Date();

    if (month >= 1 && month <= 12 && year) {
        const daysInMonth = new Date(year, month, 0).getDate();
        const day = Math.min(selectedDate.getDate(), daysInMonth);
        setValue("analyticsDate", `${year}-${pad2(month)}-${pad2(day)}`);
    }

    loadAttendanceAnalytics();
}

function buildAnalyticsModel(report, attendanceRecords, month, year) {
    const selectedShift = getValue("analyticsShift") || "all";
    const selectedRole = getValue("analyticsRole") || "all";
    const selectedEmployee = getValue("analyticsEmployee") || "all";
    const employeeMap = {};

    employees.forEach(emp => {
        employeeMap[emp.id] = emp;
    });

    const filteredEmployeeIds = new Set(
        employees
            .filter(emp => selectedShift === "all" || emp.shift === selectedShift)
            .filter(emp => selectedRole === "all" || emp.role === selectedRole)
            .filter(emp => selectedEmployee === "all" || String(emp.id) === selectedEmployee)
            .map(emp => emp.id)
    );

    const filteredReport = report.filter(item => filteredEmployeeIds.has(item.employee_id));
    const filteredRecords = attendanceRecords.filter(record => {
        const recordDate = parseRecordDate(record.date);
        if (!recordDate) return false;

        return filteredEmployeeIds.has(record.employee_id)
            && recordDate.getMonth() + 1 === Number(month)
            && recordDate.getFullYear() === Number(year);
    });

    const employeeStats = {};
    filteredReport.forEach(item => {
        employeeStats[item.employee_id] = {
            hours: 0,
            late: 0,
            early: 0,
            records: 0
        };
    });

    filteredRecords.forEach(record => {
        if (!employeeStats[record.employee_id]) {
            employeeStats[record.employee_id] = {
                hours: 0,
                late: 0,
                early: 0,
                records: 0
            };
        }

        employeeStats[record.employee_id].hours += durationToHours(record.total_hours);
        employeeStats[record.employee_id].late += record.is_late ? 1 : 0;
        employeeStats[record.employee_id].early += record.left_early && record.logout_time ? 1 : 0;
        employeeStats[record.employee_id].records += 1;
    });

    return {
        report: filteredReport,
        records: filteredRecords,
        employeeStats,
        daily: buildDailyAnalytics(filteredRecords, month, year),
        employeeMap
    };
}

function populateAnalyticsEmployeeFilter() {
    const select = document.getElementById("analyticsEmployee");
    if (!select) return;

    const selected = select.value || "all";
    const selectedShift = getValue("analyticsShift") || "all";
    const selectedRole = getValue("analyticsRole") || "all";

    const options = employees
        .filter(emp => selectedShift === "all" || emp.shift === selectedShift)
        .filter(emp => selectedRole === "all" || emp.role === selectedRole)
        .map(emp => `<option value="${emp.id}">${emp.name} - ${formatLabel(emp.shift)}</option>`)
        .join("");

    select.innerHTML = `<option value="all">All Employees</option>${options}`;

    const exists = [...select.options].some(option => option.value === selected);
    select.value = exists ? selected : "all";
}

function buildDailyAnalytics(records, month, year) {
    const daysInMonth = new Date(Number(year), Number(month), 0).getDate();
    const daily = [];

    for (let day = 1; day <= daysInMonth; day += 1) {
        const current = new Date(Number(year), Number(month) - 1, day);
        const id = `${year}-${pad2(month)}-${pad2(day)}`;
        daily.push({
            id,
            label: isSunday(current) ? `${day} Sun` : String(day),
            present: 0,
            hours: 0,
            late: 0,
            early: 0
        });
    }

    const dailyMap = {};
    daily.forEach(item => {
        dailyMap[item.id] = item;
    });

    records.forEach(record => {
        const item = dailyMap[record.date];
        if (!item) return;

        if (!isSunday(parseRecordDate(record.date))) {
            item.present += 1;
        }

        item.hours += durationToHours(record.total_hours);
        item.late += record.is_late ? 1 : 0;
        item.early += record.left_early && record.logout_time ? 1 : 0;
    });

    return daily;
}

function filterWarningData(data) {
    const selectedShift = getValue("analyticsShift") || "all";
    const selectedRole = getValue("analyticsRole") || "all";

    const employeesById = {};
    employees.forEach(emp => {
        employeesById[emp.id] = emp;
    });

    const filtered = data.employees.filter(item => {
        const employee = employeesById[item.employee_id];
        if (!employee) return false;

        return (selectedShift === "all" || employee.shift === selectedShift)
            && (selectedRole === "all" || employee.role === selectedRole);
    });

    return {
        ...data,
        total_warnings: filtered.length,
        employees: filtered
    };
}

function renderAnalyticsScorecards(model) {
    const totalHours = model.records.reduce((sum, record) => sum + durationToHours(record.total_hours), 0);
    const late = model.records.filter(record => record.is_late).length;
    const early = model.records.filter(record => record.left_early && record.logout_time).length;
    const averageAttendance = model.report.length
        ? model.report.reduce((sum, item) => sum + item.attendance_percentage, 0) / model.report.length
        : 0;

    setText("analyticsFilteredEmployees", model.report.length);
    setText("analyticsAverageAttendance", `${averageAttendance.toFixed(1)}%`);
    setText("analyticsFilteredHours", formatHours(totalHours));
    setText("analyticsLateEarly", `${late} / ${early}`);
}

function renderTodayLists(items) {
    const presentList = document.getElementById("presentList");
    const absentList = document.getElementById("absentList");
    const leaveList = document.getElementById("leaveList");

    if (!presentList || !absentList || !leaveList) return;

    presentList.innerHTML = "";
    absentList.innerHTML = "";
    leaveList.innerHTML = "";

    items.forEach(item => {
        const line = `<li>${item.name} <span>${formatLabel(item.role)} - ${formatLabel(item.shift)} - Joined ${formatDate(item.joined_at)}</span></li>`;

        if (item.status === "Present" || item.status === "Working (Punched In)") {
            presentList.innerHTML += line;
        } else if (item.status === "On Leave") {
            leaveList.innerHTML += line;
        } else if (item.status === "Absent") {
            absentList.innerHTML += line;
        }
    });

    emptyList(presentList);
    emptyList(absentList);
    emptyList(leaveList);
}

async function loadAllAttendance() {
    try {
        allAttendanceRecords = await apiRequest("/admin/attendance");
        renderAllAttendance();
    } catch (error) {
        alert(error.message);
    }
}

function renderAllAttendance() {
    const table = document.getElementById("allAttendanceTable");

    if (!table) return;

    const records = getFilteredAttendanceRecords();
    const limit = attendanceRecordLimit();
    const visibleRecords = records.slice(0, limit);
    table.innerHTML = "";

    visibleRecords.forEach(record => {
        const active = !record.logout_time;

        table.innerHTML += `
            <tr>
                <td>${record.employee_name}</td>
                <td>${formatLabel(record.role)}</td>
                <td>${formatLabel(record.shift)}</td>
                <td>${formatDate(record.joined_at)}</td>
                <td>${record.date}</td>
                <td>${formatDateTime(record.login_time)}</td>
                <td>${active ? badge("In progress", "warning") : formatDateTime(record.logout_time)}</td>
                <td>${formatDuration(record.total_hours)}</td>
                <td>${yesNo(record.is_late)}</td>
                <td>${active ? "-" : yesNo(record.left_early)}</td>
            </tr>
        `;
    });

    setText("attendanceRecordCount", attendanceRecordCountText(visibleRecords.length, records.length));
    renderAttendanceSummary(records);
    emptyTable(table, 10);
}

function attendanceRecordLimit() {
    const limit = Number(getValue("attendanceRecordLimit"));
    return [10, 25, 50, 75, 100].includes(limit) ? limit : allAttendanceRecords.length;
}

function attendanceRecordCountText(visible, total) {
    if (!document.getElementById("attendanceRecordLimit")) {
        return `${total} Records`;
    }

    return `${visible} of ${total} Records`;
}

async function loadLeaves() {
    try {
        const data = await apiRequest("/leave/all");
        const table = document.getElementById("leaveTable");

        if (!table) return;

        table.innerHTML = "";

        data.forEach(leave => {
            const pending = leave.status === "pending";
            const actions = pending
                ? `
                    <button class="approve" onclick="updateLeave(${leave.id}, 'approved')">Approve</button>
                    <button class="reject" onclick="updateLeave(${leave.id}, 'rejected')">Reject</button>
                `
                : `<span class="muted">Completed</span>`;

            table.innerHTML += `
                <tr>
                    <td>${leave.id}</td>
                    <td>${leave.employee_id}</td>
                    <td>${leave.employee_name || "-"}</td>
                    <td>${formatLabel(leave.employee_role)}</td>
                    <td>${leave.start_date}</td>
                    <td>${leave.end_date}</td>
                    <td>${leave.reason}</td>
                    <td>${formatStatus(leave.status)}</td>
                    <td>${actions}</td>
                </tr>
            `;
        });

        emptyTable(table, 9);
    } catch (error) {
        alert(error.message);
    }
}

async function updateLeave(id, status) {
    try {
        const data = await apiRequest(`/leave/${id}`, {
            method: "PUT",
            body: JSON.stringify({ status })
        });

        alert(data.message);
        refreshAdminDashboard();
    } catch (error) {
        alert(error.message);
    }
}

async function updateRole() {
    const id = getValue("employeeId");
    const role = getValue("role");

    if (!id || !role) {
        alert("Enter employee ID and role");
        return;
    }

    const employee = employees.find(emp => String(emp.id) === String(id));
    if (employee?.role === "super_admin") {
        alert("Super admin role cannot be changed");
        return;
    }

    if (role === "super_admin" && employees.some(emp => emp.role === "super_admin" && String(emp.id) !== String(id))) {
        alert("Only one super admin is allowed");
        return;
    }

    try {
        const data = await apiRequest(`/admin/employee/${id}/role`, {
            method: "PUT",
            body: JSON.stringify({ role })
        });

        alert(data.message);
        refreshAdminDashboard();
    } catch (error) {
        alert(error.message);
    }
}

async function updateShift() {
    const id = getValue("employeeId");
    const shift = getValue("shift");

    if (!id || !shift) {
        alert("Enter employee ID and shift");
        return;
    }

    const employee = employees.find(emp => String(emp.id) === String(id));
    if (employee?.role === "super_admin") {
        alert("Super admin does not have a shift");
        return;
    }

    try {
        const data = await apiRequest(`/admin/employee/${id}/shift`, {
            method: "PUT",
            body: JSON.stringify({ shift })
        });

        alert(data.message);
        refreshAdminDashboard();
    } catch (error) {
        alert(error.message);
    }
}

async function deleteEmployee(id) {
    if (!confirm("Delete employee and all related attendance/leave records?")) {
        return;
    }

    try {
        const data = await apiRequest(`/admin/employee/${id}`, { method: "DELETE" });

        alert(data.message);
        refreshAdminDashboard();
    } catch (error) {
        alert(error.message);
    }
}

function fillEmployee(id) {
    const employee = employees.find(emp => emp.id === id);

    if (!employee) return;

    setValue("employeeId", employee.id);
    setValue("role", employee.role === "super_admin" ? "" : employee.role);
    setValue("shift", employee.role === "super_admin" ? "" : employee.shift);
}

function canDeleteEmployee(employee) {
    if (!currentAdmin || employee.role === "super_admin" || employee.id === currentAdmin.employee_id) {
        return false;
    }

    if (employee.role === "admin") {
        return currentAdmin.role === "super_admin";
    }

    return true;
}

function employeeStatus(employee) {
    if (employee.role === "super_admin") {
        return "No Attendance";
    }

    if (employee.assignment_pending || !employee.role || !employee.shift) {
        return "Pending Assignment";
    }

    return todayStatuses[employee.id]?.status || "Absent";
}

function filterTodayStatus(status) {
    activeStatusFilter = status;
    updateEmployeeStatusButtons();
    renderEmployees();
}

function filterEmployeeShift(shift) {
    activeEmployeeShiftFilter = shift;
    updateEmployeeShiftButtons();
    renderEmployees();
}

function filterTodaySummaryShift(shift) {
    activeSummaryShift = shift;
    loadShiftSummary();
}

function filterAttendanceHistory(mode) {
    activeAttendanceFilter = mode;
    updateAttendanceFilterControls();
    renderAllAttendance();
}

function setupAttendanceHistoryFilters() {
    if (!document.getElementById("attendanceDate")) return;

    const now = new Date();
    setValue("attendanceDate", formatInputDate(now));
    setValue("attendanceWeek", getWeekInputValue(now));
    setValue("attendanceMonth", `${now.getFullYear()}-${pad2(now.getMonth() + 1)}`);
    setValue("attendanceYear", now.getFullYear());
    updateAttendanceFilterControls();
}

function setupAdminMonthlySummary() {
    if (!document.getElementById("adminSummaryMonth")) return;

    const now = new Date();
    setValue("adminSummaryMonth", now.getMonth() + 1);
    setValue("adminSummaryYear", now.getFullYear());
    loadAdminMonthlySummary();
}

async function loadAdminMonthlySummary() {
    const month = getValue("adminSummaryMonth");
    const year = getValue("adminSummaryYear");

    if (!month || !year) return;

    try {
        const data = await apiRequest(`/employee/monthly-summary?month=${month}&year=${year}`);

        setText("adminMonthlySummaryLabel", `${pad2(month)}-${year}`);
        setText("adminMonthPresentDays", data.has_data === false ? "No data" : formatDayCount(data.present_days));
        setText("adminMonthExtraWork", data.has_data === false ? "No data" : `Extra: ${data.extra_work_days || 0} days / ${data.extra_work_hours || 0} hrs`);
        setText("adminAttendancePercentage", data.has_data === false ? "No data" : `${data.attendance_percentage}%`);
    } catch (error) {
        alert(error.message);
    }
}

function updateAttendanceFilterControls() {
    const labels = {
        day: "Day",
        week: "Week",
        month: "Month",
        year: "Year"
    };

    setText("attendanceFilterLabel", labels[activeAttendanceFilter]);

    setButtonActive("attendanceDayBtn", activeAttendanceFilter === "day");
    setButtonActive("attendanceWeekBtn", activeAttendanceFilter === "week");
    setButtonActive("attendanceMonthBtn", activeAttendanceFilter === "month");
    setButtonActive("attendanceYearBtn", activeAttendanceFilter === "year");

    setVisible("attendanceDayField", activeAttendanceFilter === "day");
    setVisible("attendanceWeekField", activeAttendanceFilter === "week");
    setVisible("attendanceMonthField", activeAttendanceFilter === "month");
    setVisible("attendanceYearField", activeAttendanceFilter === "year");
}

function updateEmployeeShiftButtons() {
    setButtonActive("shiftAllBtn", activeEmployeeShiftFilter === "all");
    setButtonActive("shiftMorningBtn", activeEmployeeShiftFilter === "morning");
    setButtonActive("shiftNightBtn", activeEmployeeShiftFilter === "night");
}

function updateEmployeeStatusButtons() {
    setButtonActive("statusAllBtn", activeStatusFilter === "all");
    setButtonActive("statusPresentBtn", activeStatusFilter === "present");
    setButtonActive("statusAbsentBtn", activeStatusFilter === "absent");
    setButtonActive("statusLeaveBtn", activeStatusFilter === "leave");
}

function getFilteredAttendanceRecords() {
    if (!document.getElementById("attendanceDate")) {
        return allAttendanceRecords;
    }

    const employeeSearch = getValue("attendanceEmployeeSearch").toLowerCase();

    return allAttendanceRecords.filter(record => {
        const recordDate = parseRecordDate(record.date);

        if (!recordDate) return false;
        if (!matchesAttendanceEmployee(record, employeeSearch)) return false;

        if (activeAttendanceFilter === "day") {
            const selectedDate = getValue("attendanceDate");
            return selectedDate ? record.date === selectedDate : true;
        }

        if (activeAttendanceFilter === "week") {
            return getWeekInputValue(recordDate) === getValue("attendanceWeek");
        }

        if (activeAttendanceFilter === "month") {
            return record.date.slice(0, 7) === getValue("attendanceMonth");
        }

        return String(recordDate.getFullYear()) === getValue("attendanceYear");
    });
}

function renderAttendanceSummary(records) {
    if (!document.getElementById("attendanceSummaryCard")) return;

    const totalHours = records.reduce((sum, record) => sum + durationToHours(record.total_hours), 0);
    const employeeCount = new Set(records.map(record => record.employee_id)).size;
    const lateCount = records.filter(record => record.is_late).length;
    const earlyCount = records.filter(record => record.left_early && record.logout_time).length;

    setText("attendanceEmployeeCount", employeeCount);
    setText("attendanceTotalHours", formatHours(totalHours));
    setText("attendanceLateCount", lateCount);
    setText("attendanceEarlyCount", earlyCount);
    setText("attendanceSummaryLabel", formatHours(totalHours));
    setText("attendancePeriodLabel", attendancePeriodText());

    renderAttendanceBreakdown(records);
}

function renderAttendanceBreakdown(records) {
    const table = document.getElementById("attendanceBreakdownTable");
    if (!table) return;

    table.innerHTML = "";

    const groups = buildAttendanceBreakdown(records);
    groups.forEach(group => {
        table.innerHTML += `
            <tr>
                <td>${group.label}</td>
                <td>${group.records.length}</td>
                <td>${formatHours(group.hours)}</td>
                <td>${group.late}</td>
                <td>${group.early}</td>
            </tr>
        `;
    });

    emptyTable(table, 5);
}

function buildAttendanceBreakdown(records) {
    if (activeAttendanceFilter === "day") {
        return [summarizeAttendanceGroup(attendancePeriodText(), records)];
    }

    const groups = {};

    records.forEach(record => {
        const recordDate = parseRecordDate(record.date);
        if (!recordDate) return;

        const key = attendanceBreakdownKey(recordDate);
        if (!groups[key.id]) {
            groups[key.id] = { label: key.label, records: [] };
        }
        groups[key.id].records.push(record);
    });

    return Object.keys(groups)
        .sort()
        .map(key => summarizeAttendanceGroup(groups[key].label, groups[key].records));
}

function summarizeAttendanceGroup(label, records) {
    return {
        label,
        records,
        hours: records.reduce((sum, record) => sum + durationToHours(record.total_hours), 0),
        late: records.filter(record => record.is_late).length,
        early: records.filter(record => record.left_early && record.logout_time).length
    };
}

function attendanceBreakdownKey(date) {
    if (activeAttendanceFilter === "week") {
        const id = formatInputDate(date);
        return { id, label: id };
    }

    if (activeAttendanceFilter === "month") {
        const weekNumber = Math.min(4, Math.ceil(date.getDate() / 7));
        const id = `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(weekNumber)}`;
        return { id, label: `Week ${weekNumber}` };
    }

    const id = `${date.getFullYear()}-${pad2(date.getMonth() + 1)}`;
    return { id, label: date.toLocaleString(undefined, { month: "long", year: "numeric" }) };
}

function attendancePeriodText() {
    if (activeAttendanceFilter === "day") {
        return getValue("attendanceDate") || "Selected day";
    }

    if (activeAttendanceFilter === "week") {
        return getValue("attendanceWeek") || "Selected week";
    }

    if (activeAttendanceFilter === "month") {
        return getValue("attendanceMonth") || "Selected month";
    }

    return getValue("attendanceYear") || "Selected year";
}

function matchesAttendanceEmployee(record, search) {
    if (!search) return true;

    return [
        record.employee_id,
        record.employee_name,
        record.email,
        record.role,
        record.shift,
        record.joined_at
    ]
        .join(" ")
        .toLowerCase()
        .includes(search);
}

function updateFilteredTodaySummary(shifts) {
    if (!document.getElementById("todayShiftFilter")) return;

    const selected = shifts[activeSummaryShift] || shifts.morning;
    const label = activeSummaryShift === "night" ? "Night Shift" : "Morning Shift";
    const hasAttendanceState = selected.present_today + selected.absent_today + selected.on_leave_today > 0;
    const displayLabel = selected.total > 0 && !hasAttendanceState ? `${label} Not Started` : label;

    setText("totalEmployees", selected.total);
    setText("presentToday", selected.present_today);
    setText("absentToday", selected.absent_today);
    setText("onLeaveToday", selected.on_leave_today);
    setText("summaryShiftLabel", displayLabel);

    const labelElement = document.getElementById("summaryShiftLabel");
    if (labelElement) {
        labelElement.className = `badge ${activeSummaryShift === "night" ? "warning" : "success"}`;
    }

    setButtonActive("summaryMorningBtn", activeSummaryShift === "morning");
    setButtonActive("summaryNightBtn", activeSummaryShift === "night");
    setVisible("morningShiftCard", activeSummaryShift === "morning");
    setVisible("nightShiftCard", activeSummaryShift === "night");
    renderTodayChart(selected);
}

function getCurrentSummaryShift() {
    const hour = new Date().getHours();
    return hour >= 21 || hour < 12 ? "night" : "morning";
}

function matchesSearch(emp, search) {
    if (!search) return true;

    return [emp.name, emp.email, emp.role, emp.shift, emp.joined_at]
        .join(" ")
        .toLowerCase()
        .includes(search);
}

function matchesStatus(emp) {
    if (activeStatusFilter === "all") return true;

    const status = employeeStatus(emp);

    if (activeStatusFilter === "present") {
        return status === "Present" || status === "Working (Punched In)";
    }

    if (activeStatusFilter === "leave") {
        return status === "On Leave";
    }

    return status === "Absent";
}

function matchesEmployeeShift(emp) {
    return activeEmployeeShiftFilter === "all" || emp.shift === activeEmployeeShiftFilter;
}

function renderChart(data) {
    const ctx = document.getElementById("attendanceChart");

    if (!ctx) return;

    if (attendanceChart) {
        attendanceChart.destroy();
    }

    const present = Number(data.present_today || 0);
    const leave = Number(data.on_leave_today || 0);
    const absent = Number(data.absent_today || 0);
    const total = Number(data.total_employees || data.total || 0);
    const hasAttendanceState = present + leave + absent > 0;
    const chartLabels = hasAttendanceState
        ? ["Present", "On Leave", "Absent"]
        : [total > 0 ? "Shift Not Started" : "No Employees"];
    const chartData = hasAttendanceState ? [present, leave, absent] : [1];
    const chartColors = hasAttendanceState ? ["#15803d", "#d97706", "#be123c"] : ["#94a3b8"];

    attendanceChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: chartLabels,
            datasets: [{
                data: chartData,
                backgroundColor: chartColors
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "bottom"
                }
            }
        }
    });
}

function renderTodayChart(summary) {
    if (!document.getElementById("attendanceChart") || !document.getElementById("todayShiftFilter")) return;

    renderChart({
        total: summary.total,
        present_today: summary.present_today,
        on_leave_today: summary.on_leave_today,
        absent_today: summary.absent_today
    });
}

function renderMonthlyAttendanceChart(report) {
    const ctx = document.getElementById("monthlyAttendanceChart");
    if (!ctx) return;

    const rows = [...report]
        .sort((a, b) => b.attendance_percentage - a.attendance_percentage);

    const chartCard = ctx.closest(".analytics-chart-card") || ctx.parentElement;
    if (chartCard) {
        chartCard.style.height = `${Math.max(420, rows.length * 34 + 130)}px`;
    }

    if (monthlyAttendanceChart) {
        monthlyAttendanceChart.destroy();
    }

    monthlyAttendanceChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: rows.map(item => `${item.name} (${Number(item.attendance_percentage || 0).toFixed(1)}%)`),
            datasets: [{
                label: "Attendance %",
                data: rows.map(item => Number(item.attendance_percentage || 0)),
                backgroundColor: "#0e7c73",
                borderRadius: 7,
                barThickness: 14,
                categoryPercentage: 0.78
            }]
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: value => `${value}%`
                    }
                },
                y: {
                    ticks: {
                        autoSkip: false,
                        padding: 8
                    },
                    grid: {
                        display: false
                    }
                }
            },
            layout: {
                padding: {
                    top: 8,
                    right: 16,
                    bottom: 4,
                    left: 4
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: context => `Attendance: ${context.parsed.x}%`
                    }
                }
            }
        }
    });
}

function renderAttendanceTrendChart(daily) {
    const ctx = document.getElementById("attendanceTrendChart");
    if (!ctx) return;

    if (attendanceTrendChart) {
        attendanceTrendChart.destroy();
    }

    attendanceTrendChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: daily.map(item => item.label),
            datasets: [{
                label: "Present",
                data: daily.map(item => item.present),
                borderColor: "#0e7c73",
                backgroundColor: "rgba(14, 124, 115, 0.14)",
                fill: true,
                tension: 0.35,
                pointRadius: 3
            }]
        },
        options: analyticsAxisOptions()
    });
}

function renderHoursTrendChart(daily) {
    const ctx = document.getElementById("hoursTrendChart");
    if (!ctx) return;

    if (hoursTrendChart) {
        hoursTrendChart.destroy();
    }

    hoursTrendChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: daily.map(item => item.label),
            datasets: [{
                label: "Hours",
                data: daily.map(item => Number(item.hours.toFixed(2))),
                backgroundColor: "#3346d3",
                borderRadius: 6,
                maxBarThickness: 28
            }]
        },
        options: analyticsAxisOptions()
    });
}

function renderLateEarlyChart(model) {
    const ctx = document.getElementById("lateEarlyChart");
    if (!ctx) return;

    if (lateEarlyChart) {
        lateEarlyChart.destroy();
    }

    lateEarlyChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: model.daily.map(item => item.label),
            datasets: [
                {
                    label: "Late",
                    data: model.daily.map(item => item.late),
                    backgroundColor: "#c47a00",
                    borderRadius: 6,
                    maxBarThickness: 24
                },
                {
                    label: "Left Early",
                    data: model.daily.map(item => item.early),
                    backgroundColor: "#c02648",
                    borderRadius: 6,
                    maxBarThickness: 24
                }
            ]
        },
        options: analyticsAxisOptions()
    });
}

function renderShiftSplitChart(report) {
    const ctx = document.getElementById("shiftSplitChart");
    if (!ctx) return;

    const totals = { morning: 0, night: 0 };
    report.forEach(item => {
        const employee = employees.find(emp => emp.id === item.employee_id);
        if (employee?.shift in totals) {
            totals[employee.shift] += item.present_days;
        }
    });

    if (shiftSplitChart) {
        shiftSplitChart.destroy();
    }

    shiftSplitChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["Morning Present Days", "Night Present Days"],
            datasets: [{
                data: [totals.morning, totals.night],
                backgroundColor: ["#0e7c73", "#3346d3"]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "bottom"
                }
            }
        }
    });
}

function renderEmployeeAnalytics(model) {
    const selectedEmployee = getValue("analyticsEmployee") || "all";
    const employee = selectedEmployee === "all"
        ? null
        : employees.find(emp => String(emp.id) === selectedEmployee);

    const selectedReport = selectedEmployee === "all"
        ? model.report
        : model.report.filter(item => String(item.employee_id) === selectedEmployee);
    const selectedRecords = selectedEmployee === "all"
        ? model.records
        : model.records.filter(record => String(record.employee_id) === selectedEmployee);

    const totalHours = selectedRecords.reduce((sum, record) => sum + durationToHours(record.total_hours), 0);
    const late = selectedRecords.filter(record => record.is_late).length;
    const early = selectedRecords.filter(record => record.left_early && record.logout_time).length;
    const present = selectedReport.reduce((sum, item) => sum + item.present_days, 0);
    const leave = selectedReport.reduce((sum, item) => sum + item.approved_leave_days, 0);
    const extra = selectedReport.reduce((sum, item) => sum + (item.extra_work_days || 0), 0);
    const attendance = selectedReport.length
        ? selectedReport.reduce((sum, item) => sum + item.attendance_percentage, 0) / selectedReport.length
        : 0;

    setText("employeeAnalyticsName", employee ? `${employee.name} - ${formatLabel(employee.role)}` : "All Employees");
    setText("employeeAttendancePercent", `${attendance.toFixed(1)}%`);
    setText("employeePresentLeave", `${present} / ${leave} / ${extra}`);
    setText("employeeTotalHours", formatHours(totalHours));
    setText("employeeLateEarly", `${late} / ${early}`);

    renderEmployeeHoursChart(model.daily, selectedRecords);
    renderEmployeeAnalyticsTable(selectedRecords);
}

function renderEmployeeHoursChart(daily, records) {
    const ctx = document.getElementById("employeeHoursChart");
    if (!ctx) return;

    const hoursByDate = {};
    daily.forEach(item => {
        hoursByDate[item.id] = 0;
    });

    records.forEach(record => {
        if (record.date in hoursByDate) {
            hoursByDate[record.date] += durationToHours(record.total_hours);
        }
    });

    if (employeeHoursChart) {
        employeeHoursChart.destroy();
    }

    employeeHoursChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: daily.map(item => item.label),
            datasets: [{
                label: "Hours",
                data: daily.map(item => Number((hoursByDate[item.id] || 0).toFixed(2))),
                backgroundColor: "#0e7c73",
                borderRadius: 6,
                maxBarThickness: 28
            }]
        },
        options: analyticsAxisOptions()
    });
}

function renderEmployeeAnalyticsTable(records) {
    const table = document.getElementById("employeeAnalyticsTable");
    if (!table) return;

    table.innerHTML = "";

    records
        .slice()
        .sort((a, b) => parseRecordDate(b.date) - parseRecordDate(a.date))
        .forEach(record => {
            const active = !record.logout_time;
            table.innerHTML += `
                <tr>
                    <td>${record.date}</td>
                    <td>${formatDateTime(record.login_time)}</td>
                    <td>${active ? badge("In progress", "warning") : formatDateTime(record.logout_time)}</td>
                    <td>${formatDuration(record.total_hours)}</td>
                    <td>${yesNo(record.is_late)}</td>
                    <td>${active ? "-" : yesNo(record.left_early)}</td>
                </tr>
            `;
        });

    setText("employeeRecordCount", `${records.length} Records`);
    emptyTable(table, 6);
}

function renderBestAttendance(report) {
    const table = document.getElementById("bestAttendanceTable");
    if (!table) return;

    const rows = [...report]
        .sort((a, b) => {
            if (b.attendance_percentage !== a.attendance_percentage) {
                return b.attendance_percentage - a.attendance_percentage;
            }
            return Number(b.present_days || 0) - Number(a.present_days || 0);
        })
        .slice(0, 5);

    table.innerHTML = "";

    rows.forEach(item => {
        const employee = employees.find(emp => emp.id === item.employee_id);
        table.innerHTML += `
            <tr>
                <td>${item.name}</td>
                <td>${formatLabel(employee?.shift)}</td>
                <td>${formatDate(employee?.joined_at || item.joined_at)}</td>
                <td>${formatDayCount(item.present_days)}</td>
                <td>${item.approved_leave_days}</td>
                <td>${formatExtraWork(item)}</td>
                <td>${badge(`${item.attendance_percentage}%`, attendanceScoreClass(item.attendance_percentage))}</td>
            </tr>
        `;
    });

    setText("bestAttendanceCount", `${rows.length} Employees`);
    emptyTable(table, 7);
}

function renderLowAttendanceWarnings(data) {
    const table = document.getElementById("lowAttendanceTable");
    if (!table) return;

    table.innerHTML = "";

    data.employees.forEach(item => {
        table.innerHTML += `
            <tr>
                <td>${item.name}</td>
                <td>${formatDayCount(item.present_days)}</td>
                <td>${formatExtraWork(item)}</td>
                <td>${item.effective_working_days}</td>
                <td>${badge(`${item.attendance_percentage}%`, attendanceScoreClass(item.attendance_percentage))}</td>
                <td>${badge(item.status, "warning")}</td>
            </tr>
        `;
    });

    setText("lowAttendanceCount", `${data.total_warnings} Warnings`);
    emptyTable(table, 6);
}

function renderAnalyticsDetailTable(report, employeeStats) {
    const table = document.getElementById("analyticsDetailTable");
    if (!table) return;

    const rows = [...report].sort((a, b) => a.attendance_percentage - b.attendance_percentage);

    table.innerHTML = "";

    rows.forEach(item => {
        const employee = employees.find(emp => emp.id === item.employee_id);
        const stats = employeeStats[item.employee_id] || { hours: 0, late: 0, early: 0 };

        table.innerHTML += `
            <tr>
                <td>${item.name}</td>
                <td>${formatLabel(employee?.role)}</td>
                <td>${formatLabel(employee?.shift)}</td>
                <td>${formatDate(employee?.joined_at || item.joined_at)}</td>
                <td>${formatDayCount(item.present_days)}</td>
                <td>${item.approved_leave_days}</td>
                <td>${formatExtraWork(item)}</td>
                <td>${item.effective_working_days}</td>
                <td>${badge(`${item.attendance_percentage}%`, attendanceScoreClass(item.attendance_percentage))}</td>
                <td>${formatHours(stats.hours)}</td>
                <td>${stats.late}</td>
                <td>${stats.early}</td>
            </tr>
        `;
    });

    setText("analyticsDetailCount", `${rows.length} Rows`);
    emptyTable(table, 12);
}

function analyticsAxisOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: "bottom"
            }
        },
        scales: {
            x: {
                grid: {
                    display: false
                }
            },
            y: {
                beginAtZero: true,
                ticks: {
                    precision: 0
                }
            }
        }
    };
}

function refreshAdminDashboard() {
    loadAdminProfile();
    loadDashboard();
    loadShiftSummary();
    loadEmployees();
    loadAllAttendance();
    loadAdminAttendanceHistory();
    loadAdminMonthlySummary();
    loadLeaves();
}

function formatStatus(status) {
    if (status === "approved") return badge("Approved", "success");
    if (status === "rejected") return badge("Rejected", "danger");
    return badge("Pending", "warning");
}

function statusClass(status) {
    if (status === "Present" || status === "Working (Punched In)") return "success";
    if (status === "On Leave") return "warning";
    if (status === "Pending Assignment" || status === "No Attendance" || status === "Shift Not Started" || status === "Extra Work") return "neutral";
    return "danger";
}

function attendanceScoreClass(score) {
    if (score >= 90) return "success";
    if (score >= LOW_ATTENDANCE_THRESHOLD) return "warning";
    return "danger";
}

function setStatusBadge(id, status) {
    const element = document.getElementById(id);
    if (!element) return;

    element.innerText = status;
    element.className = `badge ${statusClass(status)}`;
}

function formatDateTime(value) {
    return value ? new Date(value).toLocaleString() : "-";
}

function formatDate(value) {
    return value ? new Date(value).toLocaleDateString() : "-";
}

function parseRecordDate(value) {
    if (!value) return null;
    const parts = value.split("-").map(Number);

    if (parts.length !== 3) return null;

    return new Date(parts[0], parts[1] - 1, parts[2]);
}

function formatInputDate(value) {
    return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}`;
}

function getWeekInputValue(value) {
    const date = new Date(Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()));
    const dayNumber = date.getUTCDay() || 7;

    date.setUTCDate(date.getUTCDate() + 4 - dayNumber);

    const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
    const weekNumber = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);

    return `${date.getUTCFullYear()}-W${pad2(weekNumber)}`;
}

function pad2(value) {
    return String(value).padStart(2, "0");
}

function isSunday(value) {
    return value.getDay() === 0;
}

function durationToHours(value) {
    if (!value) return 0;

    const duration = String(value).split(".")[0];
    const dayMatch = duration.match(/(\d+)\s+day[s]?,\s*(\d+):(\d+):(\d+)/);

    if (dayMatch) {
        const days = Number(dayMatch[1]);
        const hours = Number(dayMatch[2]);
        const minutes = Number(dayMatch[3]);
        const seconds = Number(dayMatch[4]);
        return (days * 24) + hours + (minutes / 60) + (seconds / 3600);
    }

    const parts = duration.split(":").map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return 0;

    return parts[0] + (parts[1] / 60) + (parts[2] / 3600);
}

function formatHours(value) {
    const totalMinutes = Math.round(value * 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;

    return `${hours}h ${pad2(minutes)}m`;
}

function formatExtraWork(item) {
    return `${item.extra_work_days || 0}d / ${item.extra_work_hours || 0}h`;
}

function formatDayCount(value) {
    const number = Number(value || 0);
    return Number.isInteger(number) ? String(number) : number.toFixed(1);
}

function formatDuration(value) {
    if (!value) return "-";
    return value.split(".")[0];
}

function formatLabel(value) {
    if (!value) return "-";
    return value
        .split("_")
        .map(part => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
}

function badge(text, type) {
    return `<span class="badge ${type}">${text}</span>`;
}

function yesNo(value) {
    return value ? badge("Yes", "warning") : badge("No", "success");
}

function emptyList(list) {
    if (!list.innerHTML) {
        list.innerHTML = `<li class="muted">No records</li>`;
    }
}

function emptyTable(table, columns) {
    if (!table.innerHTML) {
        table.innerHTML = `<tr><td colspan="${columns}" class="muted">No records found</td></tr>`;
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

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.innerText = value;
    }
}

function setButtonActive(id, active) {
    const element = document.getElementById(id);
    if (!element) return;

    element.classList.toggle("active", active);
}

function setVisible(id, visible) {
    const element = document.getElementById(id);
    if (element) {
        element.style.display = visible ? "" : "none";
    }
}
