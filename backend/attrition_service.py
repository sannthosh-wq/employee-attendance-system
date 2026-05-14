import json
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import joblib
except ImportError:  # pragma: no cover - handled at runtime for environments before install
    joblib = None

from sqlalchemy import extract, or_
from sqlalchemy.orm import Session

from attendance_logic import approved_leave_on, attendance_day_credit, employee_work_start_date, is_working_day, working_leave_days
from models import Attendance, AttritionPrediction, Employee, Leave, SalaryStructure


MODEL_DIR = Path(__file__).resolve().parent / "ml_models"
MODEL_PATH = MODEL_DIR / "attrition_model.joblib"
MODEL_META_PATH = MODEL_DIR / "attrition_model_meta.json"
FEATURE_NAMES = [
    "attendance_percentage",
    "late_count",
    "leave_count",
    "consecutive_absences",
    "salary",
    "tenure_months",
    "role_encoded",
]


def risk_level(score: float) -> str:
    if score > 70:
        return "High Risk"
    if score >= 40:
        return "Medium Risk"
    return "Low Risk"


def role_encoded(role: str | None) -> int:
    return 1 if role in {"admin", "super_admin"} else 0


def tenure_months(employee: Employee, today: date | None = None) -> int:
    today = today or date.today()
    joined = employee.joined_at or today
    months = (today.year - joined.year) * 12 + today.month - joined.month
    if today.day < joined.day:
        months -= 1
    return max(months, 0)


def latest_salary(db: Session, employee_id: int) -> float:
    salary = (
        db.query(SalaryStructure)
        .filter(SalaryStructure.employee_id == employee_id)
        .order_by(SalaryStructure.is_active.desc(), SalaryStructure.effective_from.desc(), SalaryStructure.id.desc())
        .first()
    )
    return float(salary.total_salary or 0) if salary else 0.0


def attendance_records_by_date(db: Session, employee_id: int, start_date: date, end_date: date) -> dict[date, Attendance]:
    rows = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date >= start_date,
            Attendance.date <= end_date,
        )
        .all()
    )
    return {row.date: row for row in rows}


def approved_leave_days(db: Session, employee_id: int, start_date: date, end_date: date) -> int:
    leaves = (
        db.query(Leave)
        .filter(
            Leave.employee_id == employee_id,
            Leave.status == "approved",
            Leave.start_date <= end_date,
            Leave.end_date >= start_date,
        )
        .all()
    )
    return sum(
        working_leave_days(max(leave.start_date, start_date), min(leave.end_date, end_date))
        for leave in leaves
    )


def consecutive_absences(db: Session, employee: Employee, start_date: date, end_date: date, records: dict[date, Attendance]) -> int:
    current = start_date
    streak = 0
    longest = 0

    while current <= end_date:
        if not is_working_day(current) or approved_leave_on(db, employee.id, current):
            streak = 0
            current += timedelta(days=1)
            continue

        record = records.get(current)
        if record and record.login_time:
            streak = 0
        else:
            streak += 1
            longest = max(longest, streak)

        current += timedelta(days=1)

    return longest


def employee_attrition_features(db: Session, employee: Employee, today: date | None = None, lookback_days: int = 90) -> dict:
    today = today or date.today()
    period_start = max(employee_work_start_date(employee), today - timedelta(days=lookback_days))
    if period_start > today:
        period_start = today

    records = attendance_records_by_date(db, employee.id, period_start, today)
    working_days = sum(
        1
        for offset in range((today - period_start).days + 1)
        if is_working_day(period_start + timedelta(days=offset))
    )
    leave_count = approved_leave_days(db, employee.id, period_start, today)
    effective_working_days = max(working_days - leave_count, 1)
    present_credit = sum(
        attendance_day_credit(record, employee.shift)
        for record in records.values()
        if is_working_day(record.date) and record.login_time
    )
    attendance_percentage = min(round((present_credit / effective_working_days) * 100, 2), 100)
    late_count = sum(1 for record in records.values() if record.is_late)
    absence_streak = consecutive_absences(db, employee, period_start, today, records)

    return {
        "employee_id": employee.id,
        "name": employee.name,
        "attendance_percentage": attendance_percentage,
        "late_count": late_count,
        "leave_count": leave_count,
        "consecutive_absences": absence_streak,
        "salary": latest_salary(db, employee.id),
        "tenure_months": tenure_months(employee, today),
        "role_encoded": role_encoded(employee.role),
    }


def feature_vector(features: dict) -> list[float]:
    return [float(features[name] or 0) for name in FEATURE_NAMES]


def heuristic_risk(features: dict) -> float:
    attendance_gap = max(0, 100 - features["attendance_percentage"]) * 0.42
    late_pressure = min(features["late_count"] * 3.0, 18)
    leave_pressure = min(features["leave_count"] * 2.2, 16)
    absence_pressure = min(features["consecutive_absences"] * 8.0, 24)
    tenure_pressure = 10 if features["tenure_months"] < 6 else 4 if features["tenure_months"] < 12 else 0
    salary_pressure = 7 if features["salary"] and features["salary"] < 30000 else 0
    admin_offset = -5 if features["role_encoded"] else 0
    return round(max(0, min(100, attendance_gap + late_pressure + leave_pressure + absence_pressure + tenure_pressure + salary_pressure + admin_offset)), 2)


def load_model():
    if not joblib or not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


def model_metadata() -> dict:
    if not MODEL_META_PATH.exists():
        return {"model_available": False, "model_type": "heuristic_fallback"}
    return json.loads(MODEL_META_PATH.read_text())


def predict_risk_score(features: dict, model=None) -> float:
    if model is not None:
        try:
            probability = model.predict_proba([feature_vector(features)])[0][1]
            return round(float(probability) * 100, 2)
        except Exception:
            pass
    return heuristic_risk(features)


def employees_for_prediction(db: Session) -> list[Employee]:
    return (
        db.query(Employee)
        .filter(
            Employee.role != "super_admin",
            Employee.role.isnot(None),
            or_(Employee.employment_type.is_(None), Employee.employment_type != "intern"),
        )
        .order_by(Employee.id.asc())
        .all()
    )


def store_monthly_prediction(db: Session, employee_id: int, score: float, level: str, predicted_on: datetime | None = None):
    predicted_on = predicted_on or datetime.utcnow()
    existing = (
        db.query(AttritionPrediction)
        .filter(
            AttritionPrediction.employee_id == employee_id,
            extract("year", AttritionPrediction.predicted_on) == predicted_on.year,
            extract("month", AttritionPrediction.predicted_on) == predicted_on.month,
        )
        .first()
    )

    if existing:
        existing.risk_score = score
        existing.risk_level = level
        existing.predicted_on = predicted_on
        return existing

    item = AttritionPrediction(
        employee_id=employee_id,
        risk_score=score,
        risk_level=level,
        predicted_on=predicted_on,
    )
    db.add(item)
    return item


def prediction_summary(predictions: list[dict]) -> dict:
    total = len(predictions)
    high = sum(1 for item in predictions if item["risk_level"] == "High Risk")
    medium = sum(1 for item in predictions if item["risk_level"] == "Medium Risk")
    low = sum(1 for item in predictions if item["risk_level"] == "Low Risk")
    overall = round(sum(item["risk_score"] for item in predictions) / total, 2) if total else 0
    return {
        "total_employees": total,
        "high_risk_count": high,
        "medium_risk_count": medium,
        "low_risk_count": low,
        "overall_risk_percent": overall,
    }


def monthly_trend(db: Session, months: int = 6) -> list[dict]:
    today = date.today()
    start_month = today.month - months + 1
    start_year = today.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1

    start_date = date(start_year, start_month, 1)
    rows = (
        db.query(AttritionPrediction)
        .filter(AttritionPrediction.predicted_on >= datetime.combine(start_date, datetime.min.time()))
        .order_by(AttritionPrediction.predicted_on.asc())
        .all()
    )
    grouped: dict[str, list[AttritionPrediction]] = {}
    for row in rows:
        key = row.predicted_on.strftime("%Y-%m")
        grouped.setdefault(key, []).append(row)

    trend = []
    year, month = start_year, start_month
    for _ in range(months):
        key = f"{year}-{month:02d}"
        items = grouped.get(key, [])
        average = round(sum(item.risk_score for item in items) / len(items), 2) if items else 0
        trend.append({
            "month": key,
            "average_risk": average,
            "high": sum(1 for item in items if item.risk_level == "High Risk"),
            "medium": sum(1 for item in items if item.risk_level == "Medium Risk"),
            "low": sum(1 for item in items if item.risk_level == "Low Risk"),
        })
        month += 1
        if month > 12:
            month = 1
            year += 1

    return trend


def predict_attrition(db: Session, store: bool = True) -> dict:
    model = load_model()
    predictions = []

    for employee in employees_for_prediction(db):
        features = employee_attrition_features(db, employee)
        score = predict_risk_score(features, model)
        level = risk_level(score)
        if store:
            store_monthly_prediction(db, employee.id, score, level)

        predictions.append({
            **features,
            "risk_score": score,
            "risk_level": level,
        })

    if store:
        db.commit()

    predictions.sort(key=lambda item: item["risk_score"], reverse=True)
    return {
        "generated_on": datetime.utcnow(),
        "model": model_metadata(),
        "summary": prediction_summary(predictions),
        "predictions": predictions,
        "trend": monthly_trend(db),
    }


def model_status() -> dict:
    metadata = model_metadata()
    metadata["feature_names"] = FEATURE_NAMES
    metadata["model_path"] = str(MODEL_PATH)
    return metadata
