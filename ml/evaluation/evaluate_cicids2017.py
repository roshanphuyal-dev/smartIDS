from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
)

TEST_PATH = Path("ml/data/cicids2017_test.csv")
MODEL_PATH = Path("ml/saved_models/cicids2017_model.pkl")
LABEL_ENCODER_PATH = Path("ml/saved_models/label_encoder.pkl")
FEATURE_COLUMNS_PATH = Path("ml/saved_models/feature_columns.json")
RESULTS_DIR = Path("ml/results")
REPORT_PATH = RESULTS_DIR / "cicids2017_evaluation_report.md"

LABEL_COLUMN = "Attack Type"


def normalize_cicids_binary_label(label: str) -> str:
    label = str(label).strip().lower()
    if label in {"benign", "normal", "normal traffic"} or label.startswith("normal") or label.startswith("benign"):
        return "benign"
    return "attack"


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(TEST_PATH)

    with open(FEATURE_COLUMNS_PATH, "r", encoding="utf-8") as f:
        feature_columns = json.load(f)

    model = joblib.load(MODEL_PATH)
    label_encoder = joblib.load(LABEL_ENCODER_PATH)

    df.columns = [col.strip() for col in df.columns]

    missing_features = [col for col in feature_columns if col not in df.columns]
    if missing_features:
        raise ValueError(
            "Test dataset is missing trained feature columns: "
            f"{missing_features[:10]}"
        )

    if LABEL_COLUMN not in df.columns:
        raise ValueError(f"Label column '{LABEL_COLUMN}' not found in test dataset.")

    X_test = df[feature_columns].apply(pd.to_numeric, errors="coerce")
    X_test = X_test.replace([np.inf, -np.inf], np.nan).dropna(axis=0)
    if X_test.empty:
        raise ValueError("No valid test rows remain after numeric feature cleaning.")

    df = df.loc[X_test.index]
    y_test_raw = df[LABEL_COLUMN].apply(normalize_cicids_binary_label)

    y_test = label_encoder.transform(y_test_raw)
    y_pred = model.predict(X_test)

    labels = list(range(len(label_encoder.classes_)))
    target_names = [str(x) for x in label_encoder.classes_]

    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    recall = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1 = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    class_report = classification_report(
        y_test,
        y_pred,
        labels=labels,
        target_names=target_names,
        zero_division=0,
    )

    matrix = confusion_matrix(y_test, y_pred, labels=labels)
    label_counts = y_test_raw.value_counts().to_string()

    report = (
        "# CICIDS2017 Model Evaluation Report\n\n"
        "## Dataset\n\n"
        f"- Test file: `{TEST_PATH}`\n"
        f"- Total test rows: `{len(df)}`\n"
        f"- Label column: `{LABEL_COLUMN}`\n"
        f"- Model: `{MODEL_PATH}`\n\n"
        "## Test Label Distribution\n\n"
        "```text\n"
        f"{label_counts}\n"
        "```\n\n"
        "## Overall Metrics\n\n"
        "| Metric | Score |\n"
        "|---|---:|\n"
        f"| Accuracy | {accuracy:.4f} |\n"
        f"| Precision | {precision:.4f} |\n"
        f"| Recall | {recall:.4f} |\n"
        f"| F1 Score | {f1:.4f} |\n\n"
        "## Classification Report\n\n"
        "```text\n"
        f"{class_report}\n"
        "```\n\n"
        "## Confusion Matrix\n\n"
        f"Labels order: {target_names}\n\n"
        "```text\n"
        f"{matrix}\n"
        "```\n"
    )

    REPORT_PATH.write_text(report, encoding="utf-8")

    print("Evaluation complete.")
    print(f"Accuracy: {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall: {recall:.4f}")
    print(f"F1 Score: {f1:.4f}")
    print(f"Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
