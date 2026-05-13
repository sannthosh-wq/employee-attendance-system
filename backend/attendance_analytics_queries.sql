-- Attendance analytics queries for PostgreSQL.
-- Parameters use SQLAlchemy-style names such as :report_date, :month, and :year.

-- Recommended indexes
CREATE INDEX IF NOT EXISTS ix_attendance_employee_date
ON attendance(employee_id, date);

CREATE INDEX IF NOT EXISTS ix_attendance_date_status
ON attendance(date, status);

CREATE INDEX IF NOT EXISTS ix_attendance_late_date
ON attendance(date)
WHERE is_late = TRUE;

CREATE INDEX IF NOT EXISTS ix_attendance_early_date
ON attendance(date)
WHERE left_early = TRUE;

CREATE INDEX IF NOT EXISTS ix_employees_department
ON employees(department);

CREATE INDEX IF NOT EXISTS ix_leaves_date_status
ON leaves(leave_date, status);

-- If your existing data has no duplicates, also enforce this:
-- CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_employee_date_idx
-- ON attendance(employee_id, date);


-- 1. Daily attendance report
SELECT
    e.id AS employee_id,
    e.employee_code,
    e.name AS employee_name,
    e.department,
    a.date AS attendance_date,
    a.login_time::time AS punch_in,
    a.logout_time::time AS punch_out,
    COALESCE(a.status, 'Present') AS status,
    a.is_late AS late_flag,
    COALESCE(a.late_minutes, 0) AS late_minutes,
    a.left_early AS early_exit_flag,
    COALESCE(a.early_minutes, 0) AS early_minutes,
    ROUND(COALESCE(a.working_hours, EXTRACT(EPOCH FROM a.total_hours) / 3600, 0)::numeric, 2) AS working_hours
FROM employees e
LEFT JOIN attendance a
    ON a.employee_id = e.id
   AND a.date = :report_date
WHERE e.joined_at <= :report_date
  AND COALESCE(e.role, '') <> 'super_admin'
ORDER BY e.department, e.name;


-- 2. Monthly attendance summary
SELECT
    e.id AS employee_id,
    e.employee_code,
    e.name AS employee_name,
    e.department,
    COUNT(*) FILTER (WHERE a.status = 'Present') AS present_days,
    COUNT(*) FILTER (WHERE a.status = 'Absent') AS absent_days,
    COUNT(*) FILTER (WHERE a.status = 'Leave') AS leave_days,
    COUNT(*) FILTER (WHERE a.is_late = TRUE) AS late_days,
    COUNT(*) FILTER (WHERE a.left_early = TRUE) AS early_exit_days,
    ROUND(SUM(COALESCE(a.working_hours, EXTRACT(EPOCH FROM a.total_hours) / 3600, 0))::numeric, 2) AS total_working_hours
FROM employees e
JOIN attendance a ON a.employee_id = e.id
WHERE EXTRACT(YEAR FROM a.date) = :year
  AND EXTRACT(MONTH FROM a.date) = :month
  AND COALESCE(e.role, '') <> 'super_admin'
GROUP BY e.id, e.employee_code, e.name, e.department
ORDER BY e.name;


-- 3. Weekly attendance report
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    DATE_TRUNC('week', a.date)::date AS week_start,
    (DATE_TRUNC('week', a.date)::date + INTERVAL '6 days')::date AS week_end,
    COUNT(*) FILTER (WHERE a.status = 'Present') AS present_days,
    COUNT(*) FILTER (WHERE a.status = 'Absent') AS absent_days,
    COUNT(*) FILTER (WHERE a.status = 'Leave') AS leave_days,
    COUNT(*) FILTER (WHERE a.is_late = TRUE) AS late_days,
    COUNT(*) FILTER (WHERE a.left_early = TRUE) AS early_exit_days,
    ROUND(SUM(COALESCE(a.working_hours, EXTRACT(EPOCH FROM a.total_hours) / 3600, 0))::numeric, 2) AS working_hours
FROM employees e
JOIN attendance a ON a.employee_id = e.id
WHERE a.date BETWEEN :week_start AND :week_end
  AND COALESCE(e.role, '') <> 'super_admin'
GROUP BY e.id, e.name, DATE_TRUNC('week', a.date)
ORDER BY week_start, e.name;


-- 4. Late employees for a given date
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    e.department,
    a.date AS attendance_date,
    a.login_time::time AS punch_in,
    COALESCE(a.late_minutes, 0) AS late_minutes
FROM attendance a
JOIN employees e ON e.id = a.employee_id
WHERE a.date = :report_date
  AND a.is_late = TRUE
ORDER BY a.login_time;


-- 5. Late employees for a given month
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    e.department,
    a.date AS attendance_date,
    a.login_time::time AS punch_in,
    COALESCE(a.late_minutes, 0) AS late_minutes
FROM attendance a
JOIN employees e ON e.id = a.employee_id
WHERE EXTRACT(YEAR FROM a.date) = :year
  AND EXTRACT(MONTH FROM a.date) = :month
  AND a.is_late = TRUE
ORDER BY a.date, a.login_time;


-- 6. List of early exits
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    e.department,
    a.date AS attendance_date,
    a.logout_time::time AS punch_out,
    COALESCE(a.early_minutes, 0) AS early_minutes
FROM attendance a
JOIN employees e ON e.id = a.employee_id
WHERE a.date BETWEEN :start_date AND :end_date
  AND a.left_early = TRUE
ORDER BY a.date, a.logout_time;


-- 7. Attendance percentage per employee
WITH working_days AS (
    SELECT COUNT(*) AS total_working_days
    FROM generate_series(:start_date::date, :end_date::date, INTERVAL '1 day') AS d(day)
    WHERE EXTRACT(DOW FROM day) <> 0
)
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    COUNT(*) FILTER (WHERE a.status = 'Present') AS present_days,
    wd.total_working_days,
    ROUND((COUNT(*) FILTER (WHERE a.status = 'Present') * 100.0 / NULLIF(wd.total_working_days, 0))::numeric, 2) AS attendance_percentage
FROM employees e
CROSS JOIN working_days wd
LEFT JOIN attendance a
    ON a.employee_id = e.id
   AND a.date BETWEEN :start_date AND :end_date
WHERE COALESCE(e.role, '') <> 'super_admin'
  AND e.joined_at <= :end_date
GROUP BY e.id, e.name, wd.total_working_days
ORDER BY attendance_percentage DESC, e.name;


-- 8. Total absent days per employee
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    COUNT(a.id) AS absent_days
FROM employees e
LEFT JOIN attendance a
    ON a.employee_id = e.id
   AND a.status = 'Absent'
   AND a.date BETWEEN :start_date AND :end_date
WHERE COALESCE(e.role, '') <> 'super_admin'
GROUP BY e.id, e.name
ORDER BY absent_days DESC, e.name;


-- 9. Total leave days per employee
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    COUNT(a.id) AS leave_days
FROM employees e
LEFT JOIN attendance a
    ON a.employee_id = e.id
   AND a.status = 'Leave'
   AND a.date BETWEEN :start_date AND :end_date
WHERE COALESCE(e.role, '') <> 'super_admin'
GROUP BY e.id, e.name
ORDER BY leave_days DESC, e.name;


-- Dashboard: Monthly attendance %
WITH working_days AS (
    SELECT COUNT(*) AS total_working_days
    FROM generate_series(
        MAKE_DATE(:year, :month, 1),
        (MAKE_DATE(:year, :month, 1) + INTERVAL '1 month - 1 day')::date,
        INTERVAL '1 day'
    ) AS d(day)
    WHERE EXTRACT(DOW FROM day) <> 0
),
employee_count AS (
    SELECT COUNT(*) AS total_employees
    FROM employees
    WHERE COALESCE(role, '') <> 'super_admin'
      AND joined_at <= (MAKE_DATE(:year, :month, 1) + INTERVAL '1 month - 1 day')::date
)
SELECT
    :year AS year,
    :month AS month,
    ROUND(
        COUNT(*) FILTER (WHERE a.status = 'Present') * 100.0
        / NULLIF(wd.total_working_days * ec.total_employees, 0),
        2
    ) AS monthly_attendance_percentage
FROM attendance a
CROSS JOIN working_days wd
CROSS JOIN employee_count ec
WHERE EXTRACT(YEAR FROM a.date) = :year
  AND EXTRACT(MONTH FROM a.date) = :month;


-- Dashboard: Total late count per month
SELECT
    EXTRACT(YEAR FROM date)::int AS year,
    EXTRACT(MONTH FROM date)::int AS month,
    COUNT(*) AS total_late_count
FROM attendance
WHERE is_late = TRUE
GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
ORDER BY year, month;


-- Dashboard: Total leave count per month
SELECT
    EXTRACT(YEAR FROM date)::int AS year,
    EXTRACT(MONTH FROM date)::int AS month,
    COUNT(*) AS total_leave_count
FROM attendance
WHERE status = 'Leave'
GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
ORDER BY year, month;


-- Dashboard: Top 5 most absent employees
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    e.department,
    COUNT(a.id) AS absent_days
FROM employees e
JOIN attendance a ON a.employee_id = e.id
WHERE a.status = 'Absent'
  AND a.date BETWEEN :start_date AND :end_date
GROUP BY e.id, e.name, e.department
ORDER BY absent_days DESC, e.name
LIMIT 5;


-- Dashboard: Department-wise attendance %
WITH department_working_days AS (
    SELECT COUNT(*) AS total_working_days
    FROM generate_series(:start_date::date, :end_date::date, INTERVAL '1 day') AS d(day)
    WHERE EXTRACT(DOW FROM day) <> 0
),
department_employee_count AS (
    SELECT department, COUNT(*) AS total_employees
    FROM employees
    WHERE COALESCE(role, '') <> 'super_admin'
      AND joined_at <= :end_date
    GROUP BY department
)
SELECT
    e.department,
    COUNT(*) FILTER (WHERE a.status = 'Present') AS present_days,
    dec.total_employees * dwd.total_working_days AS expected_working_days,
    ROUND(
        COUNT(*) FILTER (WHERE a.status = 'Present') * 100.0
        / NULLIF(dec.total_employees * dwd.total_working_days, 0),
        2
    ) AS department_attendance_percentage
FROM employees e
JOIN attendance a ON a.employee_id = e.id
JOIN department_employee_count dec ON dec.department IS NOT DISTINCT FROM e.department
CROSS JOIN department_working_days dwd
WHERE a.date BETWEEN :start_date AND :end_date
  AND COALESCE(e.role, '') <> 'super_admin'
GROUP BY e.department, dec.total_employees, dwd.total_working_days
ORDER BY department_attendance_percentage DESC;


-- Dashboard: Leave approval vs rejection ratio
SELECT
    EXTRACT(YEAR FROM COALESCE(leave_date, start_date))::int AS year,
    EXTRACT(MONTH FROM COALESCE(leave_date, start_date))::int AS month,
    COUNT(*) FILTER (WHERE status = 'approved') AS approved_count,
    COUNT(*) FILTER (WHERE status = 'rejected') AS rejected_count,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'approved') * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS approval_percentage,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'rejected') * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS rejection_percentage
FROM leaves
WHERE COALESCE(leave_date, start_date) BETWEEN :start_date AND :end_date
GROUP BY
    EXTRACT(YEAR FROM COALESCE(leave_date, start_date)),
    EXTRACT(MONTH FROM COALESCE(leave_date, start_date))
ORDER BY year, month;
