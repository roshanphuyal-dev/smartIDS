from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from ml.evaluation.metrics import MetricsEvaluator
from ml.features.cicids2017_mapping import normalize_cicids2017_label
from ml.features.cicids2017_validation import prepare_cicids2017_features
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN
from ml.models.sklearn_model import SklearnModel
from ml.models.xgboost_model import XGBoostModel
from ml.runtime.artifact_validation import load_runtime_model_artifacts


MODEL_FILENAME = "cicids2017_live_compatible_model.pkl"
ENCODER_FILENAME = "live_compatible_label_encoder.pkl"
FEATURE_COLUMNS_FILENAME = "live_compatible_feature_columns.json"
BENCHMARK_FILENAME = "live_compatible_benchmark_report.json"
EVALUATION_FILENAME = "cicids2017_evaluation_report.md"
TRAINING_METADATA_FILENAME = "live_compatible_training_metadata.json"
MANIFEST_FILENAME = "live_compatible_model_manifest.json"
SAMPLE_INPUT_FILENAME = "live_compatible_sample_input.json"
SAMPLE_OUTPUT_FILENAME = "live_compatible_sample_output.json"


@dataclass(frozen=True)
class ModelBuildResult:
    active_dir: Path
    manifest_path: Path
    sample_input_path: Path
    sample_output_path: Path


def validate_dataset_metadata(
    train_path: Path | str,
    test_path: Path | str,
    metadata_path: Path | str,
) -> dict:
    train_file = Path(train_path)
    test_file = Path(test_path)
    metadata_file = Path(metadata_path)

    for path in (train_file, test_file, metadata_file):
        if not path.exists():
            raise FileNotFoundError(f"Required model-build input not found: {path}")

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    if metadata.get("feature_columns") != FEATURE_COLUMNS:
        raise ValueError(
            "Dataset metadata feature schema does not match canonical FEATURE_COLUMNS"
        )

    outputs = metadata.get("outputs", {})
    expected_train_hash = outputs.get("train", {}).get("sha256")
    expected_test_hash = outputs.get("test", {}).get("sha256")
    if expected_train_hash != _sha256(train_file):
        raise ValueError("Training dataset hash does not match dataset metadata")
    if expected_test_hash != _sha256(test_file):
        raise ValueError("Testing dataset hash does not match dataset metadata")

    train_rows = _csv_row_count(train_file)
    test_rows = _csv_row_count(test_file)
    if metadata.get("train_rows") != train_rows:
        raise ValueError("Training dataset row count does not match dataset metadata")
    if metadata.get("test_rows") != test_rows:
        raise ValueError("Testing dataset row count does not match dataset metadata")

    return metadata


def write_sample_contracts(
    output_dir: Path | str,
    sample_input: dict,
    sample_output: dict,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    if list(sample_input) != FEATURE_COLUMNS:
        raise ValueError("Sample input does not match canonical FEATURE_COLUMNS order")
    if set(sample_output) != {"label", "confidence", "encoded"}:
        raise ValueError("Sample output must contain label, confidence, and encoded")

    input_path = destination / SAMPLE_INPUT_FILENAME
    output_path = destination / SAMPLE_OUTPUT_FILENAME
    input_path.write_text(
        json.dumps(sample_input, indent=2),
        encoding="utf-8",
    )
    output_path.write_text(
        json.dumps(sample_output, indent=2),
        encoding="utf-8",
    )
    return input_path, output_path


def write_model_manifest(
    staging_dir: Path | str,
    dataset_metadata: dict,
    model_type: str,
    class_labels: list[str],
    metrics: dict,
    trained_at_utc: str,
) -> Path:
    staging_path = Path(staging_dir)
    artifacts = {}
    for path in sorted(staging_path.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != MANIFEST_FILENAME:
            artifacts[path.name] = {
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }

    manifest = {
        "schema_version": "1.0",
        "model_type": model_type,
        "trained_at_utc": trained_at_utc,
        "feature_columns": list(FEATURE_COLUMNS),
        "protocol_encoding": {
            "TCP": 6,
            "UDP": 17,
            "ICMP": 1,
            "UNKNOWN": 0,
        },
        "class_labels": class_labels,
        "metrics": metrics,
        "dataset_provenance": dataset_metadata,
        "artifacts": artifacts,
    }
    manifest_path = staging_path / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def activate_staged_directory(
    staging_dir: Path | str,
    active_dir: Path | str,
) -> None:
    staging_path = Path(staging_dir)
    active_path = Path(active_dir)
    if not staging_path.is_dir():
        raise FileNotFoundError(f"Staged model directory not found: {staging_path}")

    active_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = active_path.parent / (
        f".{active_path.name}.backup-{uuid4().hex}"
    )
    had_active = active_path.exists()

    if had_active:
        os.replace(active_path, backup_path)

    try:
        os.replace(staging_path, active_path)
    except Exception:
        if had_active and backup_path.exists():
            os.replace(backup_path, active_path)
        raise
    else:
        if backup_path.exists():
            shutil.rmtree(backup_path, ignore_errors=True)


def build_model_bundle(
    train_path: Path | str = Path("ml/data/cicids2017_train.csv"),
    test_path: Path | str = Path("ml/data/cicids2017_test.csv"),
    dataset_metadata_path: Path | str = Path(
        "ml/data/cicids2017_dataset_metadata.json"
    ),
    active_dir: Path | str = Path("ml/saved_models"),
    model_type: str = "xgboost",
) -> ModelBuildResult:
    train_file = Path(train_path)
    test_file = Path(test_path)
    metadata_file = Path(dataset_metadata_path)
    active_path = Path(active_dir)
    dataset_metadata = validate_dataset_metadata(
        train_file,
        test_file,
        metadata_file,
    )

    train_dataframe = _load_dataset(train_file)
    test_dataframe = _load_dataset(test_file)
    train_features = prepare_cicids2017_features(train_dataframe)
    test_features = prepare_cicids2017_features(test_dataframe)
    train_labels_raw = _normalized_labels(train_dataframe)
    test_labels_raw = _normalized_labels(test_dataframe)

    label_encoder = LabelEncoder()
    train_labels = label_encoder.fit_transform(train_labels_raw)
    unknown_test_labels = sorted(
        set(test_labels_raw.unique()) - set(label_encoder.classes_)
    )
    if unknown_test_labels:
        raise ValueError(f"Unknown test labels: {unknown_test_labels}")
    test_labels = label_encoder.transform(test_labels_raw)

    active_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = Path(
        tempfile.mkdtemp(
            prefix=f".{active_path.name}.staging-",
            dir=active_path.parent,
        )
    )
    activated = False

    try:
        model_wrapper = _build_model(model_type)
        model_wrapper.train(train_features, train_labels)
        predictions = model_wrapper.predict(test_features)
        class_indexes = list(range(len(label_encoder.classes_)))
        class_labels = [str(label) for label in label_encoder.classes_]
        evaluator = MetricsEvaluator()
        metrics = evaluator.evaluate(
            y_true=test_labels,
            y_pred=predictions,
            labels=class_indexes,
            target_names=class_labels,
        )
        metrics["normal_traffic_false_positive_rate"] = _normal_traffic_fpr(
            test_labels,
            predictions,
            label_encoder,
        )

        trained_at_utc = datetime.now(timezone.utc).isoformat()
        model_path = staging_path / MODEL_FILENAME
        encoder_path = staging_path / ENCODER_FILENAME
        feature_columns_path = staging_path / FEATURE_COLUMNS_FILENAME
        benchmark_path = staging_path / BENCHMARK_FILENAME
        evaluation_path = staging_path / EVALUATION_FILENAME
        training_metadata_path = staging_path / TRAINING_METADATA_FILENAME

        model_wrapper.save(str(model_path))
        joblib.dump(label_encoder, encoder_path)
        model_path.with_name(model_path.name + ".sha256").write_text(
            f"{_sha256(model_path)}\n", encoding="utf-8"
        )
        encoder_path.with_name(encoder_path.name + ".sha256").write_text(
            f"{_sha256(encoder_path)}\n", encoding="utf-8"
        )
        feature_columns_path.write_text(
            json.dumps(FEATURE_COLUMNS, indent=2),
            encoding="utf-8",
        )
        benchmark_path.write_text(
            json.dumps(metrics, indent=2),
            encoding="utf-8",
        )
        evaluation_path.write_text(
            _evaluation_report(
                test_path=test_file,
                model_path=model_path,
                labels=class_labels,
                label_distribution=test_labels_raw.value_counts().sort_index(),
                metrics=metrics,
            ),
            encoding="utf-8",
        )
        training_metadata = {
            "model_file": MODEL_FILENAME,
            "label_encoder_file": ENCODER_FILENAME,
            "feature_columns_file": FEATURE_COLUMNS_FILENAME,
            "model_type": model_type,
            "class_labels": class_labels,
            "trained_at_utc": trained_at_utc,
            "dataset_metadata_file": str(metadata_file),
            "dataset_metadata_sha256": _sha256(metadata_file),
            "train_dataset_sha256": _sha256(train_file),
            "test_dataset_sha256": _sha256(test_file),
            "protocol_encoding": {
                "TCP": 6,
                "UDP": 17,
                "ICMP": 1,
                "UNKNOWN": 0,
            },
        }
        training_metadata_path.write_text(
            json.dumps(training_metadata, indent=2),
            encoding="utf-8",
        )

        runtime_model, runtime_encoder = load_runtime_model_artifacts(
            model_path,
            encoder_path,
            feature_columns_path,
        )
        sample_input = {
            feature: float(test_features.iloc[0][feature])
            for feature in FEATURE_COLUMNS
        }
        sample_output = _predict(
            runtime_model,
            runtime_encoder,
            sample_input,
        )
        sample_input_path, sample_output_path = write_sample_contracts(
            staging_path,
            sample_input,
            sample_output,
        )
        write_model_manifest(
            staging_dir=staging_path,
            dataset_metadata=dataset_metadata,
            model_type=model_type,
            class_labels=class_labels,
            metrics=metrics,
            trained_at_utc=trained_at_utc,
        )

        activate_staged_directory(staging_path, active_path)
        activated = True
        return ModelBuildResult(
            active_dir=active_path,
            manifest_path=active_path / MANIFEST_FILENAME,
            sample_input_path=active_path / sample_input_path.name,
            sample_output_path=active_path / sample_output_path.name,
        )
    finally:
        if not activated and staging_path.exists():
            shutil.rmtree(staging_path)


def _build_model(model_type: str):
    if model_type == "xgboost":
        return XGBoostModel()
    if model_type in {"random_forest", "hist_gradient_boosting"}:
        return SklearnModel(model_type=model_type)
    raise ValueError(f"Unsupported model type: {model_type}")


def _load_dataset(path: Path) -> pd.DataFrame:
    dataframe = pd.read_csv(path)
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    if LABEL_COLUMN not in dataframe.columns:
        raise ValueError(f"Label column '{LABEL_COLUMN}' not found in dataset: {path}")
    if dataframe.empty:
        raise ValueError(f"Dataset contains no rows: {path}")
    return dataframe


def _normalized_labels(dataframe: pd.DataFrame) -> pd.Series:
    return dataframe[LABEL_COLUMN].apply(normalize_cicids2017_label).astype(str)


def _predict(model, label_encoder, features: dict) -> dict:
    frame = pd.DataFrame([features], columns=FEATURE_COLUMNS)
    encoded = int(model.predict(frame)[0])
    label = str(label_encoder.inverse_transform([encoded])[0])
    confidence = 0.0
    if hasattr(model, "predict_proba"):
        confidence = float(np.max(model.predict_proba(frame)[0]))
    return {
        "label": label,
        "confidence": confidence,
        "encoded": encoded,
    }


def _normal_traffic_fpr(y_true, y_pred, label_encoder: LabelEncoder) -> float:
    if "Normal Traffic" not in label_encoder.classes_:
        return 0.0
    normal_index = int(
        np.where(label_encoder.classes_ == "Normal Traffic")[0][0]
    )
    true_normal = y_true == normal_index
    predicted_normal = y_pred == normal_index
    true_negative = int(np.sum((~true_normal) & (~predicted_normal)))
    false_positive = int(np.sum((~true_normal) & predicted_normal))
    denominator = false_positive + true_negative
    return float(false_positive / denominator) if denominator else 0.0


def _evaluation_report(
    test_path: Path,
    model_path: Path,
    labels: list[str],
    label_distribution: pd.Series,
    metrics: dict,
) -> str:
    return (
        "# CICIDS2017 Model Evaluation Report\n\n"
        "## Dataset\n\n"
        f"- Test file: `{test_path}`\n"
        f"- Total test rows: `{int(label_distribution.sum())}`\n"
        f"- Label column: `{LABEL_COLUMN}`\n"
        f"- Model: `{model_path.name}`\n\n"
        "## Test Label Distribution\n\n"
        "```text\n"
        f"{label_distribution.to_string()}\n"
        "```\n\n"
        "## Overall Metrics\n\n"
        "| Metric | Score |\n"
        "|---|---:|\n"
        f"| Accuracy | {metrics['accuracy']:.4f} |\n"
        f"| Precision | {metrics['precision']:.4f} |\n"
        f"| Recall | {metrics['recall']:.4f} |\n"
        f"| F1 Score | {metrics['f1_score']:.4f} |\n"
        "| Normal Traffic FPR | "
        f"{metrics['normal_traffic_false_positive_rate']:.4f} |\n\n"
        "## Confusion Matrix\n\n"
        f"Labels order: {labels}\n\n"
        "```text\n"
        f"{np.array(metrics['confusion_matrix'])}\n"
        "```\n"
    )


def _csv_row_count(path: Path) -> int:
    with path.open("rb") as file:
        line_count = sum(1 for _ in file)
    return max(0, line_count - 1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate prepared CICIDS2017 data, train and evaluate a model, "
            "verify runtime artifacts, and activate the complete model bundle."
        )
    )
    parser.add_argument(
        "--train",
        type=Path,
        default=Path("ml/data/cicids2017_train.csv"),
    )
    parser.add_argument(
        "--test",
        type=Path,
        default=Path("ml/data/cicids2017_test.csv"),
    )
    parser.add_argument(
        "--dataset-metadata",
        type=Path,
        default=Path("ml/data/cicids2017_dataset_metadata.json"),
    )
    parser.add_argument(
        "--active-dir",
        type=Path,
        default=Path("ml/saved_models"),
    )
    parser.add_argument(
        "--model-type",
        choices=["xgboost", "random_forest", "hist_gradient_boosting"],
        default="xgboost",
    )
    arguments = parser.parse_args()

    result = build_model_bundle(
        train_path=arguments.train,
        test_path=arguments.test,
        dataset_metadata_path=arguments.dataset_metadata,
        active_dir=arguments.active_dir,
        model_type=arguments.model_type,
    )
    print(f"Active model directory: {result.active_dir}")
    print(f"Model manifest: {result.manifest_path}")
    print(f"Sample input: {result.sample_input_path}")
    print(f"Sample output: {result.sample_output_path}")


if __name__ == "__main__":
    main()
