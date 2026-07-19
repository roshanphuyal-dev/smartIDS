from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ml.datasets.prepared_cicids2018_common import (
    CANONICAL_COLUMNS,
    EXPECTED_PREPARED_FILES,
    resolve_prepared_source_files,
    sanitize_prepared_chunk,
    validate_prepared_header,
)
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


TRAIN_FILENAME = "cicids2018_train.csv"
TEST_FILENAME = "cicids2018_test.csv"
METADATA_FILENAME = "cicids2018_split_metadata.json"
DEFAULT_SOURCE_DIR = Path("ml/datasets/CIC_IDS_2018")
DEFAULT_OUTPUT_DIR = Path("ml/data")


@dataclass(frozen=True)
class PreparedSplitDataset:
    train_path: Path
    test_path: Path
    metadata_path: Path


def split_prepared_dataset(
    source: Path | str | None,
    output_dir: Path | str,
    test_size: float = 0.2,
    random_seed: int = 42,
    chunk_size: int = 10000,
    force: bool = False,
    files: list[Path | str] | None = None,
    verbose: bool = False,
    progress_every: int = 10,
) -> PreparedSplitDataset:
    if not 0 < test_size < 1:
        raise ValueError("test_size must be greater than 0 and less than 1")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if progress_every <= 0:
        raise ValueError("progress_every must be greater than 0")

    source_files = resolve_prepared_source_files(source=source, files=files)
    destination = Path(output_dir)
    train_path = destination / TRAIN_FILENAME
    test_path = destination / TEST_FILENAME
    metadata_path = destination / METADATA_FILENAME

    existing_outputs = [path for path in (train_path, test_path, metadata_path) if path.exists()]
    if existing_outputs and not force:
        raise FileExistsError(
            "Split outputs already exist; use --force to overwrite: "
            + ", ".join(str(path) for path in existing_outputs)
        )

    if verbose:
        print(f"Counting labels from {len(source_files)} prepared files...")
    label_totals, raw_rows, cleaned_rows = _count_labels(
        source_files=source_files,
        chunk_size=chunk_size,
        verbose=verbose,
        progress_every=progress_every,
    )
    test_targets = _compute_test_targets(label_totals, test_size)

    destination.mkdir(parents=True, exist_ok=True)
    for path in (train_path, test_path, metadata_path):
        if path.exists():
            path.unlink()

    rng = random.Random(random_seed)
    train_header = True
    test_header = True
    seen_counts: Counter[str] = Counter()
    train_counts: Counter[str] = Counter()
    test_counts: Counter[str] = Counter()
    train_rows = 0
    test_rows = 0

    if verbose:
        print("Writing split rows to train/test outputs...")
    for csv_path in source_files:
        for chunk_index, cleaned_chunk in enumerate(_iter_clean_chunks(csv_path, chunk_size), start=1):
            test_indices: list[int] = []
            train_indices: list[int] = []

            for row_index, label in enumerate(cleaned_chunk[LABEL_COLUMN].tolist()):
                seen_counts[label] += 1
                remaining_total = label_totals[label] - (seen_counts[label] - 1)
                remaining_test = test_targets[label] - test_counts[label]
                choose_test = False

                if remaining_test > 0:
                    if remaining_total == remaining_test:
                        choose_test = True
                    else:
                        choose_test = rng.random() < (remaining_test / remaining_total)

                if choose_test:
                    test_indices.append(row_index)
                    test_counts[label] += 1
                    test_rows += 1
                else:
                    train_indices.append(row_index)
                    train_counts[label] += 1
                    train_rows += 1

            if train_indices:
                cleaned_chunk.iloc[train_indices].to_csv(
                    train_path,
                    mode="a",
                    header=train_header,
                    index=False,
                    columns=CANONICAL_COLUMNS,
                )
                train_header = False

            if test_indices:
                cleaned_chunk.iloc[test_indices].to_csv(
                    test_path,
                    mode="a",
                    header=test_header,
                    index=False,
                    columns=CANONICAL_COLUMNS,
                )
                test_header = False

            if verbose and chunk_index % progress_every == 0:
                print(
                    f"[split] {csv_path.name}: chunks={chunk_index}, "
                    f"train_rows={train_rows}, test_rows={test_rows}"
                )

    metadata = {
        "source_files": [path.name for path in source_files],
        "source_file_details": [
            {"name": path.name, "path": str(path)}
            for path in source_files
        ],
        "expected_files": list(EXPECTED_PREPARED_FILES),
        "feature_columns": list(FEATURE_COLUMNS),
        "label_column": LABEL_COLUMN,
        "test_size": test_size,
        "random_seed": random_seed,
        "chunk_size": chunk_size,
        "raw_rows": raw_rows,
        "cleaned_rows": cleaned_rows,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "label_distribution": _sorted_counter(label_totals),
        "train_label_distribution": _sorted_counter(train_counts),
        "test_label_distribution": _sorted_counter(test_counts),
        "train_sha256": _sha256(train_path),
        "test_sha256": _sha256(test_path),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return PreparedSplitDataset(
        train_path=train_path,
        test_path=test_path,
        metadata_path=metadata_path,
    )


def _count_labels(
    source_files: list[Path],
    chunk_size: int,
    verbose: bool = False,
    progress_every: int = 10,
) -> tuple[Counter[str], int, int]:
    label_totals: Counter[str] = Counter()
    raw_rows = 0
    cleaned_rows = 0

    for csv_path in source_files:
        for chunk_index, chunk in enumerate(pd.read_csv(csv_path, chunksize=chunk_size), start=1):
            raw_rows += len(chunk)
            cleaned_chunk = sanitize_prepared_chunk(chunk)
            cleaned_rows += len(cleaned_chunk)
            label_totals.update(cleaned_chunk[LABEL_COLUMN].astype(str).tolist())
            if verbose and chunk_index % progress_every == 0:
                print(
                    f"[count] {csv_path.name}: chunks={chunk_index}, "
                    f"raw_rows={raw_rows}, cleaned_rows={cleaned_rows}"
                )

    if not label_totals:
        raise ValueError("No valid prepared CIC IDS 2018 rows remain after cleaning")

    return label_totals, raw_rows, cleaned_rows


def _compute_test_targets(label_totals: Counter[str], test_size: float) -> Counter[str]:
    targets: Counter[str] = Counter()
    for label, count in label_totals.items():
        target = int(round(count * test_size))
        if count > 1 and target >= count:
            target = count - 1
        if target < 0:
            target = 0
        targets[label] = target
    return targets


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {
        str(label): int(count)
        for label, count in sorted(counter.items(), key=lambda item: str(item[0]))
    }


def _iter_clean_chunks(csv_path: Path, chunk_size: int):
    header = pd.read_csv(csv_path, nrows=0)
    validate_prepared_header(header.columns, str(csv_path))
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
        cleaned_chunk = sanitize_prepared_chunk(chunk)
        if not cleaned_chunk.empty:
            yield cleaned_chunk


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split prepared CIC IDS 2018 CSV files into reusable train/test datasets.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing the 10 prepared CIC IDS 2018 CSV files.",
    )
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        default=None,
        help="Explicit prepared CSV path. Repeat this flag once per expected file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the generated train/test split files.",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--chunk-size", type=int, default=10000)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = split_prepared_dataset(
        source=args.source,
        output_dir=args.output_dir,
        test_size=args.test_size,
        random_seed=args.seed,
        chunk_size=args.chunk_size,
        force=args.force,
        files=args.files,
        verbose=args.verbose,
        progress_every=args.progress_every,
    )

    print(f"Training dataset: {result.train_path}")
    print(f"Testing dataset: {result.test_path}")
    print(f"Metadata: {result.metadata_path}")


if __name__ == "__main__":
    main()
