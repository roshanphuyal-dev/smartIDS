from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from ml.features.cicids2017_mapping import normalize_cicids2017_label
from ml.features.cicids2017_validation import prepare_cicids2017_features
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


TRAIN_FILENAME = "cicids2017_train.csv"
TEST_FILENAME = "cicids2017_test.csv"
METADATA_FILENAME = "cicids2017_dataset_metadata.json"


@dataclass(frozen=True)
class PreparedDataset:
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

    train_path = destination / TRAIN_FILENAME
    test_path = destination / TEST_FILENAME
    metadata_path = destination / METADATA_FILENAME
    output_paths = (train_path, test_path, metadata_path)

    existing_outputs = [str(path) for path in output_paths if path.exists()]
    if existing_outputs and not force:
        raise FileExistsError(
            "Prepared dataset outputs already exist; use --force to overwrite: "
            + ", ".join(existing_outputs)
        )

    for csv_path in source_files:
        header = pd.read_csv(csv_path, nrows=0)
        header.columns = [str(column).strip() for column in header.columns]
        if LABEL_COLUMN not in header.columns:
            raise ValueError(
                f"Label column '{LABEL_COLUMN}' not found in source file: {csv_path}"
            )
        prepare_cicids2017_features(header)

    frames = []
    source_metadata = []
    for csv_path in source_files:
        frame = pd.read_csv(csv_path)
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
    if LABEL_COLUMN not in raw_dataset.columns:
        raise ValueError(f"Label column '{LABEL_COLUMN}' not found in source dataset")

    features = prepare_cicids2017_features(raw_dataset)
    labels = raw_dataset[LABEL_COLUMN].apply(normalize_cicids2017_label).astype(str)
    prepared = features.copy()
    prepared[LABEL_COLUMN] = labels

    train_dataset, test_dataset = train_test_split(
        prepared,
        test_size=test_size,
        random_state=random_seed,
        stratify=prepared[LABEL_COLUMN],
    )

    destination.mkdir(parents=True, exist_ok=True)
    train_dataset.to_csv(train_path, index=False)
    test_dataset.to_csv(test_path, index=False)

    metadata = {
        "source_files": source_metadata,
        "feature_columns": list(FEATURE_COLUMNS),
        "label_column": LABEL_COLUMN,
        "test_size": test_size,
        "random_seed": random_seed,
        "total_rows": len(prepared),
        "train_rows": len(train_dataset),
        "test_rows": len(test_dataset),
        "label_distribution": _label_distribution(prepared),
        "train_label_distribution": _label_distribution(train_dataset),
        "test_label_distribution": _label_distribution(test_dataset),
        "outputs": {
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
        description="Prepare strict canonical CICIDS2017 train/test datasets.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Raw CICIDS2017 CSV file or directory containing CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/data"),
        help="Directory for generated train, test, and metadata files.",
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

    print(f"Training dataset: {result.train_path}")
    print(f"Testing dataset: {result.test_path}")
    print(f"Metadata: {result.metadata_path}")


if __name__ == "__main__":
    main()
