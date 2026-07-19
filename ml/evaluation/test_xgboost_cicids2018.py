from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from ml.datasets.prepared_cicids2018_common import sanitize_prepared_chunk
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN
from ml.training.train_xgboost_cicids2018 import (
    DEFAULT_MODEL_DIR,
    _metrics_from_confusion_matrix,
    FEATURE_COLUMNS_FILENAME,
    LABEL_ENCODER_FILENAME,
    MODEL_FILENAME,
)


BENCHMARK_REPORT_FILENAME = "cicids2018_xgboost_benchmark_report.json"
MARKDOWN_REPORT_FILENAME = "cicids2018_xgboost_evaluation_report.md"
CONFUSION_MATRIX_FILENAME = "cicids2018_xgboost_confusion_matrix.json"
DEFAULT_TEST_CSV = Path("ml/data/cicids2018_test.csv")


@dataclass(frozen=True)
class EvaluationArtifacts:
    benchmark_report_path: Path
    markdown_report_path: Path
    confusion_matrix_path: Path


def evaluate_model(
    test_csv: Path | str,
    model_dir: Path | str,
    chunk_size: int = 5000,
    verbose: bool = False,
    progress_every: int = 20,
) -> EvaluationArtifacts:
    test_path = Path(test_csv)
    if not test_path.exists():
        raise FileNotFoundError(f"Testing dataset not found: {test_path}")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if progress_every <= 0:
        raise ValueError("progress_every must be greater than 0")

    model_root = Path(model_dir)
    model_path = model_root / MODEL_FILENAME
    label_encoder_path = model_root / LABEL_ENCODER_FILENAME
    feature_columns_path = model_root / FEATURE_COLUMNS_FILENAME
    benchmark_report_path = model_root / BENCHMARK_REPORT_FILENAME
    markdown_report_path = model_root / MARKDOWN_REPORT_FILENAME
    confusion_matrix_path = model_root / CONFUSION_MATRIX_FILENAME

    saved_feature_columns = json.loads(feature_columns_path.read_text(encoding="utf-8"))
    if saved_feature_columns != FEATURE_COLUMNS:
        raise ValueError("Saved feature schema does not match canonical FEATURE_COLUMNS")

    model = joblib.load(model_path)
    label_encoder = joblib.load(label_encoder_path)
    target_names = [str(label) for label in label_encoder.classes_]
    if verbose:
        print(f"Evaluating {test_path} in chunks...")
    matrix, rows_evaluated, unknown_labels_filtered = _stream_evaluation_confusion(
        csv_path=test_path,
        booster=model,
        label_encoder=label_encoder,
        chunk_size=chunk_size,
        verbose=verbose,
        progress_every=progress_every,
    )
    if rows_evaluated <= 0:
        raise ValueError("No test rows remain after filtering unknown labels")

    benchmark = _metrics_from_confusion_matrix(
        confusion=matrix,
        label_names=target_names,
    )
    normal_fpr = _normal_traffic_fpr(
        confusion=matrix,
        label_encoder=label_encoder,
    )
    benchmark.update(
        {
            "rows_evaluated": rows_evaluated,
            "unknown_labels_filtered": unknown_labels_filtered,
            "labels": target_names,
            "normal_traffic_fpr": normal_fpr,
            "chunk_size": chunk_size,
        }
    )
    benchmark_report_path.write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    confusion_matrix_path.write_text(
        json.dumps({"labels": target_names, "matrix": matrix.tolist()}, indent=2),
        encoding="utf-8",
    )

    report = (
        "# CIC IDS 2018 XGBoost Evaluation Report\n\n"
        f"- Test file: `{test_path}`\n"
        f"- Rows evaluated: `{rows_evaluated}`\n"
        f"- Unknown labels filtered: `{unknown_labels_filtered}`\n"
        f"- Label column: `{LABEL_COLUMN}`\n\n"
        "## Overall Metrics\n\n"
        f"- Accuracy: `{benchmark['accuracy']:.4f}`\n"
        f"- Precision: `{benchmark['precision_weighted']:.4f}`\n"
        f"- Recall: `{benchmark['recall_weighted']:.4f}`\n"
        f"- F1 Score: `{benchmark['f1_weighted']:.4f}`\n"
        f"- Normal Traffic FPR: `{normal_fpr:.4f}`\n\n"
        "## Labels\n\n"
        f"`{target_names}`\n\n"
        "## Confusion Matrix\n\n"
        "```text\n"
        f"{matrix}\n"
        "```\n"
    )
    markdown_report_path.write_text(report, encoding="utf-8")

    return EvaluationArtifacts(
        benchmark_report_path=benchmark_report_path,
        markdown_report_path=markdown_report_path,
        confusion_matrix_path=confusion_matrix_path,
    )


def _normal_traffic_fpr(confusion: np.ndarray, label_encoder) -> float:
    if "Normal Traffic" not in label_encoder.classes_:
        return 0.0

    normal_idx = int(np.where(label_encoder.classes_ == "Normal Traffic")[0][0])
    fp = int(confusion[:, normal_idx].sum() - confusion[normal_idx, normal_idx])
    tn = int(confusion.sum() - confusion[normal_idx, :].sum() - fp)
    return float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0


def _stream_evaluation_confusion(
    csv_path: Path,
    booster: xgb.Booster,
    label_encoder,
    chunk_size: int,
    verbose: bool = False,
    progress_every: int = 20,
) -> tuple[np.ndarray, int, int]:
    num_classes = len(label_encoder.classes_)
    confusion = np.zeros((num_classes, num_classes), dtype=np.int64)
    rows_evaluated = 0
    unknown_labels_filtered = 0
    known_labels = set(str(label) for label in label_encoder.classes_)

    for chunk_index, chunk in enumerate(pd.read_csv(csv_path, chunksize=chunk_size), start=1):
        cleaned = sanitize_prepared_chunk(chunk)
        if cleaned.empty:
            continue

        labels_raw = cleaned[LABEL_COLUMN].astype(str)
        keep_mask = labels_raw.isin(known_labels)
        unknown_labels_filtered += int((~keep_mask).sum())
        cleaned = cleaned.loc[keep_mask].reset_index(drop=True)
        labels_raw = labels_raw.loc[keep_mask].reset_index(drop=True)
        if cleaned.empty:
            continue

        encoded_labels = label_encoder.transform(labels_raw)
        matrix = xgb.DMatrix(
            cleaned.loc[:, FEATURE_COLUMNS].to_numpy(dtype=np.float32, copy=False),
            feature_names=FEATURE_COLUMNS,
        )
        probabilities = booster.predict(matrix)
        predictions = np.asarray(probabilities).argmax(axis=1)

        for actual, predicted in zip(encoded_labels, predictions, strict=False):
            confusion[int(actual), int(predicted)] += 1
            rows_evaluated += 1

        if verbose and chunk_index % progress_every == 0:
            print(
                f"[eval] chunks={chunk_index}, rows_evaluated={rows_evaluated}, "
                f"unknown_filtered={unknown_labels_filtered}"
            )

    return confusion, rows_evaluated, unknown_labels_filtered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate a trained CIC IDS 2018 XGBoost model against a saved test split.",
    )
    parser.add_argument("--test-csv", type=Path, default=DEFAULT_TEST_CSV)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--chunk-size", type=int, default=5000)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--progress-every", type=int, default=20)
    args = parser.parse_args()

    result = evaluate_model(
        test_csv=args.test_csv,
        model_dir=args.model_dir,
        chunk_size=args.chunk_size,
        verbose=args.verbose,
        progress_every=args.progress_every,
    )

    print(f"Benchmark report: {result.benchmark_report_path}")
    print(f"Markdown report: {result.markdown_report_path}")
    print(f"Confusion matrix: {result.confusion_matrix_path}")


if __name__ == "__main__":
    main()
