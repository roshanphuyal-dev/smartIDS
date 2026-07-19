from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb

from ml.datasets.prepared_cicids2018_common import sanitize_prepared_chunk
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


MODEL_FILENAME = "cicids2018_xgboost_model.pkl"
LABEL_ENCODER_FILENAME = "cicids2018_xgboost_label_encoder.pkl"
FEATURE_COLUMNS_FILENAME = "cicids2018_xgboost_feature_columns.json"
TRAINING_METADATA_FILENAME = "cicids2018_xgboost_training_metadata.json"
TRAINING_REPORT_FILENAME = "cicids2018_xgboost_training_report.json"
MANIFEST_FILENAME = "cicids2018_xgboost_manifest.json"
ZIP_FILENAME = "cicids2018_xgboost_runtime.zip"
DEFAULT_TRAIN_CSV = Path("ml/data/cicids2018_train.csv")
DEFAULT_MODEL_DIR = Path("ml/saved_models/cicids2018_xgboost_runtime")


@dataclass(frozen=True)
class TrainingArtifacts:
    model_path: Path
    label_encoder_path: Path
    feature_columns_path: Path
    training_metadata_path: Path
    training_report_path: Path
    manifest_path: Path
    zip_path: Path | None


def train_model(
    train_csv: Path | str,
    output_dir: Path | str,
    *,
    n_estimators: int = 200,
    max_depth: int = 6,
    learning_rate: float = 0.1,
    subsample: float = 0.8,
    colsample_bytree: float = 0.8,
    n_jobs: int = 1,
    random_state: int = 42,
    create_zip: bool = True,
    chunk_size: int = 5000,
    max_bin: int = 256,
    verbose: bool = False,
    progress_every: int = 20,
) -> TrainingArtifacts:
    train_path = Path(train_csv)
    if not train_path.exists():
        raise FileNotFoundError(f"Training dataset not found: {train_path}")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if progress_every <= 0:
        raise ValueError("progress_every must be greater than 0")

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"Counting labels from {train_path} ...")
    label_counts = _count_labels(train_path, chunk_size)
    if not label_counts:
        raise ValueError("Training dataset contains no valid rows")

    label_encoder = LabelEncoder()
    label_encoder.fit(sorted(label_counts))
    num_classes = len(label_encoder.classes_)

    params = {
        "objective": "multi:softprob",
        "num_class": num_classes,
        "eval_metric": "mlogloss",
        "tree_method": "hist",
        "max_depth": max_depth,
        "learning_rate": learning_rate,
        "subsample": subsample,
        "colsample_bytree": colsample_bytree,
        "random_state": random_state,
        "n_jobs": n_jobs,
        "max_bin": max_bin,
    }

    if verbose:
        print(
            f"Found {sum(label_counts.values())} cleaned training rows across "
            f"{len(label_counts)} classes."
        )
        print("Preparing external-memory XGBoost training...")
    cache_root = Path(
        tempfile.mkdtemp(prefix="xgb_cache_", dir=str(output_root))
    )
    try:
        iterator = _PreparedTrainingIterator(
            csv_path=train_path,
            label_encoder=label_encoder,
            chunk_size=chunk_size,
            cache_prefix=str(cache_root / "train.cache"),
            verbose=verbose,
            progress_every=progress_every,
        )
        train_matrix = xgb.ExtMemQuantileDMatrix(
            iterator,
            max_bin=max_bin,
            nthread=n_jobs,
        )
        if verbose:
            print("Training XGBoost...")
        booster = xgb.train(
            params=params,
            dtrain=train_matrix,
            num_boost_round=n_estimators,
            evals=[],
            verbose_eval=(10 if verbose else False),
        )
    finally:
        shutil.rmtree(cache_root, ignore_errors=True)

    model_path = output_root / MODEL_FILENAME
    label_encoder_path = output_root / LABEL_ENCODER_FILENAME
    feature_columns_path = output_root / FEATURE_COLUMNS_FILENAME
    training_metadata_path = output_root / TRAINING_METADATA_FILENAME
    training_report_path = output_root / TRAINING_REPORT_FILENAME
    manifest_path = output_root / MANIFEST_FILENAME
    zip_path = output_root / ZIP_FILENAME if create_zip else None

    joblib.dump(booster, model_path)
    joblib.dump(label_encoder, label_encoder_path)
    feature_columns_path.write_text(json.dumps(FEATURE_COLUMNS, indent=2), encoding="utf-8")

    if verbose:
        print("Computing training metrics from streamed predictions...")
    confusion = _stream_confusion_matrix(
        csv_path=train_path,
        booster=booster,
        label_encoder=label_encoder,
        chunk_size=chunk_size,
        verbose=verbose,
        progress_every=progress_every,
    )
    training_report = _metrics_from_confusion_matrix(
        confusion=confusion,
        label_names=[str(label) for label in label_encoder.classes_],
    )
    training_report["rows"] = int(sum(label_counts.values()))
    training_report["label_distribution"] = {
        str(label): int(count)
        for label, count in sorted(label_counts.items(), key=lambda item: item[0])
    }
    training_report_path.write_text(
        json.dumps(training_report, indent=2),
        encoding="utf-8",
    )

    metadata = {
        "model_type": "Booster",
        "objective": "multi:softprob",
        "num_class": num_classes,
        "train_csv": str(train_path),
        "label_classes": [str(label) for label in label_encoder.classes_],
        "feature_columns": list(FEATURE_COLUMNS),
        "label_column": LABEL_COLUMN,
        "chunk_size": chunk_size,
        "protocol_encoding": {"TCP": 6, "UDP": 17, "ICMP": 1, "UNKNOWN": 0},
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "n_jobs": n_jobs,
            "random_state": random_state,
            "tree_method": "hist",
            "eval_metric": "mlogloss",
            "max_bin": max_bin,
        },
    }
    training_metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    manifest = {
        "model": model_path.name,
        "label_encoder": label_encoder_path.name,
        "feature_columns": feature_columns_path.name,
        "training_metadata": training_metadata_path.name,
        "training_report": training_report_path.name,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if zip_path is not None:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in (
                model_path,
                label_encoder_path,
                feature_columns_path,
                training_metadata_path,
                training_report_path,
                manifest_path,
            ):
                archive.write(path, arcname=path.name)

    return TrainingArtifacts(
        model_path=model_path,
        label_encoder_path=label_encoder_path,
        feature_columns_path=feature_columns_path,
        training_metadata_path=training_metadata_path,
        training_report_path=training_report_path,
        manifest_path=manifest_path,
        zip_path=zip_path,
    )


class _PreparedTrainingIterator(xgb.DataIter):
    def __init__(
        self,
        csv_path: Path,
        label_encoder: LabelEncoder,
        chunk_size: int,
        cache_prefix: str,
        verbose: bool,
        progress_every: int,
    ) -> None:
        super().__init__(cache_prefix=cache_prefix, release_data=True, on_host=False)
        self._csv_path = csv_path
        self._label_encoder = label_encoder
        self._chunk_size = chunk_size
        self._verbose = verbose
        self._progress_every = progress_every
        self._iterator = None
        self._reader = None
        self._chunk_counter = 0

    def reset(self) -> None:
        self._close_reader()
        self._reader = pd.read_csv(self._csv_path, chunksize=self._chunk_size)
        self._iterator = iter(self._reader)
        self._chunk_counter = 0

    def next(self, input_data) -> bool:
        if self._iterator is None:
            self.reset()

        while True:
            try:
                chunk = next(self._iterator)
            except StopIteration:
                self._close_reader()
                return False

            cleaned = sanitize_prepared_chunk(chunk)
            if cleaned.empty:
                continue
            self._chunk_counter += 1

            features = cleaned.loc[:, FEATURE_COLUMNS].to_numpy(dtype=np.float32, copy=True)
            labels = self._label_encoder.transform(
                cleaned[LABEL_COLUMN].astype(str)
            ).astype(np.float32)
            input_data(
                data=features,
                label=labels,
                feature_names=FEATURE_COLUMNS,
            )
            if self._verbose and self._chunk_counter % self._progress_every == 0:
                print(
                    f"[train-iterator] chunks={self._chunk_counter}, "
                    f"rows_sent~={self._chunk_counter * self._chunk_size}"
                )
            return True

    def _close_reader(self) -> None:
        if self._reader is not None:
            self._reader.close()
        self._reader = None
        self._iterator = None


def _count_labels(csv_path: Path, chunk_size: int) -> Counter[str]:
    counts: Counter[str] = Counter()
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
        cleaned = sanitize_prepared_chunk(chunk)
        counts.update(cleaned[LABEL_COLUMN].astype(str).tolist())
    return counts


def _stream_confusion_matrix(
    csv_path: Path,
    booster: xgb.Booster,
    label_encoder: LabelEncoder,
    chunk_size: int,
    verbose: bool = False,
    progress_every: int = 20,
) -> np.ndarray:
    num_classes = len(label_encoder.classes_)
    confusion = np.zeros((num_classes, num_classes), dtype=np.int64)

    for chunk_index, chunk in enumerate(pd.read_csv(csv_path, chunksize=chunk_size), start=1):
        cleaned = sanitize_prepared_chunk(chunk)
        if cleaned.empty:
            continue

        labels = label_encoder.transform(cleaned[LABEL_COLUMN].astype(str))
        matrix = xgb.DMatrix(
            cleaned.loc[:, FEATURE_COLUMNS].to_numpy(dtype=np.float32, copy=False),
            feature_names=FEATURE_COLUMNS,
        )
        probabilities = booster.predict(matrix)
        predictions = np.asarray(probabilities).argmax(axis=1)

        for actual, predicted in zip(labels, predictions, strict=False):
            confusion[int(actual), int(predicted)] += 1

        if verbose and chunk_index % progress_every == 0:
            print(f"[metrics] chunks={chunk_index}")

    return confusion


def _metrics_from_confusion_matrix(
    confusion: np.ndarray,
    label_names: list[str],
) -> dict[str, object]:
    total = int(confusion.sum())
    diagonal = np.diag(confusion).astype(float)
    support = confusion.sum(axis=1).astype(float)
    predicted = confusion.sum(axis=0).astype(float)

    precision_per_class = np.divide(
        diagonal,
        predicted,
        out=np.zeros_like(diagonal, dtype=float),
        where=predicted > 0,
    )
    recall_per_class = np.divide(
        diagonal,
        support,
        out=np.zeros_like(diagonal, dtype=float),
        where=support > 0,
    )
    f1_per_class = np.divide(
        2 * precision_per_class * recall_per_class,
        precision_per_class + recall_per_class,
        out=np.zeros_like(diagonal, dtype=float),
        where=(precision_per_class + recall_per_class) > 0,
    )

    weighted_divisor = support.sum() if support.sum() > 0 else 1.0
    weighted_precision = float(np.dot(precision_per_class, support) / weighted_divisor)
    weighted_recall = float(np.dot(recall_per_class, support) / weighted_divisor)
    weighted_f1 = float(np.dot(f1_per_class, support) / weighted_divisor)
    accuracy = float(diagonal.sum() / total) if total else 0.0

    classification_report = {
        label_name: {
            "precision": float(precision_per_class[index]),
            "recall": float(recall_per_class[index]),
            "f1-score": float(f1_per_class[index]),
            "support": float(support[index]),
        }
        for index, label_name in enumerate(label_names)
    }
    classification_report["accuracy"] = accuracy
    classification_report["weighted avg"] = {
        "precision": weighted_precision,
        "recall": weighted_recall,
        "f1-score": weighted_f1,
        "support": float(weighted_divisor),
    }

    return {
        "accuracy": accuracy,
        "precision_weighted": weighted_precision,
        "recall_weighted": weighted_recall,
        "f1_weighted": weighted_f1,
        "confusion_matrix": confusion.tolist(),
        "classification_report": classification_report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a multiclass XGBoost model from prepared CIC IDS 2018 training data.",
    )
    parser.add_argument("--train-csv", type=Path, default=DEFAULT_TRAIN_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--n-estimators", type=int, default=120)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--subsample", type=float, default=0.8)
    parser.add_argument("--colsample-bytree", type=float, default=0.8)
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--chunk-size", type=int, default=5000)
    parser.add_argument("--max-bin", type=int, default=256)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()

    result = train_model(
        train_csv=args.train_csv,
        output_dir=args.output_dir,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        subsample=args.subsample,
        colsample_bytree=args.colsample_bytree,
        n_jobs=args.n_jobs,
        random_state=args.seed,
        create_zip=not args.no_zip,
        chunk_size=args.chunk_size,
        max_bin=args.max_bin,
        verbose=args.verbose,
        progress_every=args.progress_every,
    )

    print(f"Model: {result.model_path}")
    print(f"Label encoder: {result.label_encoder_path}")
    print(f"Feature columns: {result.feature_columns_path}")
    print(f"Training metadata: {result.training_metadata_path}")
    print(f"Training report: {result.training_report_path}")
    if result.zip_path is not None:
        print(f"Download archive: {result.zip_path}")


if __name__ == "__main__":
    main()
