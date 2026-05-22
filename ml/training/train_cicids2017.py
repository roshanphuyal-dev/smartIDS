from pathlib import Path

import joblib
import numpy as np

from ml.datasets.cicids2017_loader import CICIDS2017Loader
from ml.evaluation.metrics import MetricsEvaluator
from ml.models.sklearn_model import SklearnModel
from ml.models.xgboost_model import XGBoostModel


DATASET_PATH = "ml/data/cicids2017_train.csv"

MODEL_OUTPUT_DIR = "ml/saved_models"

MODEL_TYPE = "xgboost"
# MODEL_TYPE = "random_forest"
# MODEL_TYPE = "hist_gradient_boosting"


def train():
    print("\nLoading CICIDS2017 dataset...")

    loader = CICIDS2017Loader(
        dataset_path=DATASET_PATH,
        binary_classification=True,
    )
    # if not DATASET_PATH.exists():
    #     raise FileNotFoundError(f"Dataset DATASET_PATH not found: {DATASET_PATH}")

    X_train, X_test, y_train, y_test = (
        loader.load_and_prepare()
    )

    labels = list(range(len(loader.get_label_encoder().classes_)))
    target_names = [str(label) for label in loader.get_label_encoder().classes_]

    if len(labels) < 2:
        raise ValueError(
            "Training data contains only one class after preprocessing: "
            f"{target_names}. Check the dataset labels and binary label mapping."
        )

    missing_test_labels = set(labels) - set(np.unique(y_test))
    if missing_test_labels:
        missing_names = [target_names[label] for label in sorted(missing_test_labels)]
        print(
            "\nWarning: test split has no samples for labels: "
            f"{missing_names}. Metrics will still include all known labels."
        )

    print(f"\nTraining samples : {len(X_train)}")
    print(f"Testing samples  : {len(X_test)}")
    print(f"Features         : {X_train.shape[1]}")

    print("\nInitializing models...")

    if MODEL_TYPE == "xgboost":
        model_wrapper = XGBoostModel()

    else:
        model_wrapper = SklearnModel(
            model_type=MODEL_TYPE
        )

    print("\nTraining started...")

    model_wrapper.train(
        X_train,
        y_train,
    )

    print("Training completed.")

    print("\nRunning evaluation...")

    predictions = model_wrapper.predict(X_test)

    evaluator = MetricsEvaluator()

    metrics = evaluator.evaluate(
        y_true=y_test,
        y_pred=predictions,
        labels=labels,
        target_names=target_names,
    )

    evaluator.print_summary(metrics)

    output_dir = Path(MODEL_OUTPUT_DIR)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\nSaving trained models...")

    model_path = (
        output_dir / "cicids2017_model.pkl"
    )

    model_wrapper.save(str(model_path))

    print("Model saved.")

    print("\nSaving label encoder...")

    label_encoder_path = (
        output_dir / "label_encoder.pkl"
    )

    joblib.dump(
        loader.get_label_encoder(),
        label_encoder_path,
    )

    print("Label encoder saved.")

    print("\nSaving feature schema...")

    feature_columns_path = (
        output_dir / "feature_columns.json"
    )

    loader.save_feature_columns(
        str(feature_columns_path)
    )

    print("Feature schema saved.")

    print("\nSaving benchmark report...")

    benchmark_report_path = (
        output_dir / "benchmark_report.json"
    )

    evaluator.save_report(
        metrics=metrics,
        output_path=str(
            benchmark_report_path
        ),
    )

    print("Benchmark report saved.")

    print("\n========== TRAINING COMPLETE ==========")


if __name__ == "__main__":
    train()
