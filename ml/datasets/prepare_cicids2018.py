from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from ml.features.cicids2018_mapping import normalize_cicids2018_label
from ml.features.cicids2018_validation import (
    coerce_cicids2018_features,
    prepare_cicids2018_features,
)
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


CLEANED_FILENAME = "cicids2018_cleaned.csv"
TRAIN_FILENAME = "cicids2018_train.csv"
TEST_FILENAME = "cicids2018_test.csv"
METADATA_FILENAME = "cicids2018_dataset_metadata.json"
RAW_LABEL_COLUMN = "Label"


@dataclass(frozen=True)
class PreparedDataset:
    cleaned_path: Path
    train_path: Path
    test_path: Path
    metadata_path: Path


def prepare_dataset(
    source: Path | str,
    output_dir: Path | str,
    test_size: float = 0.2,
    random_seed: int = 42,
    force: bool = False,
) -> PreparedDataset:
    source_path = Path(source)
    destination = Path(output_dir)
    source_files = _resolve_source_files(source_path)

    if not 0 < test_size < 1:
        raise ValueError("test_size must be greater than 0 and less than 1")

    cleaned_path = destination / CLEANED_FILENAME
    train_path = destination / TRAIN_FILENAME
    test_path = destination / TEST_FILENAME
    metadata_path = destination / METADATA_FILENAME
    output_paths = (cleaned_path, train_path, test_path, metadata_path)

    existing_outputs = [str(path) for path in output_paths if path.exists()]
    if existing_outputs and not force:
        raise FileExistsError(
            "Prepared dataset outputs already exist; use --force to overwrite: "
            + ", ".join(existing_outputs)
        )

    for csv_path in source_files:
        header = pd.read_csv(csv_path, nrows=0)
        header.columns = [str(column).strip() for column in header.columns]
        if RAW_LABEL_COLUMN not in header.columns:
            raise ValueError(
                f"Raw label column '{RAW_LABEL_COLUMN}' not found in source file: {csv_path}"
            )
        prepare_cicids2018_features(header)

    frames = []
    source_metadata = []
    for csv_path in source_files:
        frame = pd.read_csv(csv_path, low_memory=False)
        frame.columns = [str(column).strip() for column in frame.columns]
        frames.append(frame)
        source_metadata.append(
            {
                "path": str(csv_path),
                "rows": len(frame),
                "sha256": _sha256(csv_path),
            }
        )

    raw_dataset = pd.concat(frames, axis=0, ignore_index=True)
    if RAW_LABEL_COLUMN not in raw_dataset.columns:
        raise ValueError(
            f"Raw label column '{RAW_LABEL_COLUMN}' not found in source dataset"
        )

    cleaned_source = raw_dataset.drop_duplicates().copy()
    cleaned_source = cleaned_source.dropna(subset=[RAW_LABEL_COLUMN])
    cleaned_source[RAW_LABEL_COLUMN] = cleaned_source[RAW_LABEL_COLUMN].astype(str).str.strip()
    cleaned_source = cleaned_source[cleaned_source[RAW_LABEL_COLUMN] != ""]

    features = coerce_cicids2018_features(cleaned_source)
    valid_rows = np.isfinite(features.to_numpy(dtype=float)).all(axis=1)
    filtered_source = cleaned_source.loc[valid_rows].reset_index(drop=True)
    if filtered_source.empty:
        raise ValueError("No valid CICIDS2018 rows remain after canonical filtering")

    cleaned_features = prepare_cicids2018_features(filtered_source)
    labels = (
        filtered_source[RAW_LABEL_COLUMN]
        .apply(normalize_cicids2018_label)
        .astype(str)
        .rename(LABEL_COLUMN)
    )

    prepared = cleaned_features.copy()
    prepared[LABEL_COLUMN] = labels

    train_dataset, test_dataset = train_test_split(
        prepared,
        test_size=test_size,
        random_state=random_seed,
        stratify=prepared[LABEL_COLUMN],
    )

    destination.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(cleaned_path, index=False)
    train_dataset.to_csv(train_path, index=False)
    test_dataset.to_csv(test_path, index=False)

    metadata = {
        "source_files": source_metadata,
        "feature_columns": list(FEATURE_COLUMNS),
        "label_column": LABEL_COLUMN,
        "raw_label_column": RAW_LABEL_COLUMN,
        "test_size": test_size,
        "random_seed": random_seed,
        "total_rows": len(prepared),
        "cleaned_rows": len(prepared),
        "train_rows": len(train_dataset),
        "test_rows": len(test_dataset),
        "label_distribution": _label_distribution(prepared),
        "train_label_distribution": _label_distribution(train_dataset),
        "test_label_distribution": _label_distribution(test_dataset),
        "outputs": {
            "cleaned": {
                "path": str(cleaned_path),
                "sha256": _sha256(cleaned_path),
            },
            "train": {
                "path": str(train_path),
                "sha256": _sha256(train_path),
            },
            "test": {
                "path": str(test_path),
                "sha256": _sha256(test_path),
            },
        },
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return PreparedDataset(
        cleaned_path=cleaned_path,
        train_path=train_path,
        test_path=test_path,
        metadata_path=metadata_path,
    )


def _resolve_source_files(source: Path) -> list[Path]:
    if source.is_file():
        if source.suffix.lower() != ".csv":
            raise ValueError(f"Source file must be a CSV: {source}")
        return [source]

    if source.is_dir():
        csv_files = sorted(source.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in source directory: {source}")
        return csv_files

    raise FileNotFoundError(f"Source dataset path not found: {source}")


def _label_distribution(dataframe: pd.DataFrame) -> dict[str, int]:
    counts = dataframe[LABEL_COLUMN].value_counts().sort_index()
    return {str(label): int(count) for label, count in counts.items()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare strict canonical CIC IDS 2018 datasets for SmartIDS.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Raw CIC IDS 2018 CSV file or directory containing CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/data"),
        help="Directory for generated cleaned, train, test, and metadata files.",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()

    result = prepare_dataset(
        source=arguments.source,
        output_dir=arguments.output_dir,
        test_size=arguments.test_size,
        random_seed=arguments.seed,
        force=arguments.force,
    )

    print(f"Cleaned dataset: {result.cleaned_path}")
    print(f"Training dataset: {result.train_path}")
    print(f"Testing dataset: {result.test_path}")
    print(f"Metadata: {result.metadata_path}")


if __name__ == "__main__":
    main()
