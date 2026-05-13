# Attendance Seed Data

This setup generates realistic attendance data from **2026-01-01** to **2026-05-12**.

## Project Structure

```text
backend/
  models.py                         # SQLAlchemy Employee, Attendance, Leave models
  main.py                           # Startup schema upgrade for analytics columns/indexes
  seed_attendance.py                # Jan-May 12, 2026 attendance and leave seeder
  seed_attendance_2026.py           # Backward-compatible wrapper
  attendance_analytics_queries.sql  # Reports, dashboard metrics, and index SQL
```

## Attendance Fields

The `attendance` table now supports the dashboard fields below while keeping the existing punch API fields:

```text
employee_id
date                 -- attendance_date
login_time           -- punch_in
logout_time          -- punch_out
status               -- Present / Absent / Leave
is_late              -- late_flag
left_early           -- early_exit_flag
late_minutes
early_minutes
working_hours        -- float hours for analytics
total_hours          -- interval used by existing app screens
```

## Run Seeder

From the backend folder:

```powershell
cd backend
python seed_attendance.py
```

The script is idempotent for the generated range. It removes existing attendance, punches, and leave requests between 2026-01-01 and 2026-05-12, then recreates them.

## Seeder Rules

- Sundays are skipped.
- The first 13 non-super-admin employees are used for the academic demo.
- All demo employees are set to `joined_at = 2026-01-01`.
- Employees without a department receive one of: Engineering, HR, Finance, Sales, Operations, Support.
- Normal shift is 09:00 to 18:00.
- Each working day targets 9-10 present employees, which is about 70-80% of 13 employees.
- Each working day has 1 or 2 late employees, with late punch-in from 09:10 to 10:00.
- Each working day has 1 early exit, with punch-out from 15:30 to 16:30.
- Every 8th working day has at least 1 absent employee.
- Most working days have 1-3 leave applications; busier days have 3-5.
- Casual leave approvals are limited to 2 per employee per month.
- Total approved leave balance is limited to 5 per employee per month.
- If more than 3 employees apply on the same day, the remaining requests are rejected.
- Approved leave creates `attendance.status = 'Leave'`.
- Rejected leave creates `attendance.status = 'Absent'`.
- Present employees receive matching `attendance_punches` rows.

## Example Script Output

```text
Seeded 1469 attendance rows for 13 employees.
Seeded 294 leave applications.
Present: 1057, Absent: 223, Leave: 189
Late entries: 151, Early exits: 113
Date range: 2026-01-01 to 2026-05-12. Sundays excluded.
```

The exact leave/status mix is controlled by the fixed random seed and may change if employee IDs or employee count change.

## Example Report Row

```text
employee_id | employee_name | attendance_date | punch_in | punch_out | status  | late_minutes | early_minutes | working_hours
28          | Priya Sharma  | 2026-02-10      | 09:24:11 | 18:12:03  | Present | 24           | 0             | 8.80
```

Use `attendance_analytics_queries.sql` for daily, weekly, monthly, late, early-exit, absent, leave, attendance percentage, and department-wise dashboard queries.
