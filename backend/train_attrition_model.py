import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib

from attrition_service import FEATURE_NAMES, MODEL_DIR, MODEL_META_PATH, MODEL_PATH, employee_attrition_features, employees_for_prediction, feature_vector, heuristic_risk
from database import SessionLocal


def load_labels(path: str | None) -> dict[int, int]:
    if not path:
        return {}

    labels = {}
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            labels[int(row["employee_id"])] = int(row["attrition"])
    return labels


def training_rows(labels_path: str | None):
    labels = load_labels(labels_path)
    db = SessionLocal()
    try:
        rows = []
        targets = []
        used_bootstrap_labels = not bool(labels)

        for employee in employees_for_prediction(db):
            features = employee_attrition_features(db, employee)
            label = labels.get(employee.id)
            if label is None:
                label = 1 if heuristic_risk(features) >= 60 else 0
            rows.append(feature_vector(features))
            targets.append(label)

        if len(set(targets)) < 2:
            rows.extend([
                [95, 0, 0, 0, 60000, 36, 1],
                [45, 8, 6, 4, 22000, 3, 0],
            ])
            targets.extend([0, 1])
            used_bootstrap_labels = True

        return rows, targets, used_bootstrap_labels
    finally:
        db.close()


def train(labels_path: str | None = None):
    rows, targets, used_bootstrap_labels = training_rows(labels_path)
    if not rows:
        raise RuntimeError("No employee data available for attrition training")

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    pipeline.fit(rows, targets)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)

    metadata = {
        "model_available": True,
        "model_type": "logistic_regression",
        "feature_names": FEATURE_NAMES,
        "trained_on": datetime.utcnow().isoformat(),
        "training_rows": len(rows),
        "bootstrap_labels_used": used_bootstrap_labels,
        "labels_source": labels_path or "heuristic_bootstrap",
    }
    MODEL_META_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Train the EMS employee attrition Logistic Regression model")
    parser.add_argument(
        "--labels",
        help="Optional CSV with employee_id,attrition columns. attrition: 0=Stay, 1=Leave.",
    )
    args = parser.parse_args()
    metadata = train(args.labels)
    print(json.dumps(metadata, indent=2))
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
