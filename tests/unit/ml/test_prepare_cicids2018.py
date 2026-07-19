from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ml.datasets import prepare_cicids2018
from ml.datasets.prepare_cicids2018 import prepare_dataset
from ml.features.cicids2018_mapping import CICIDS2018_TO_INTERNAL
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


class PrepareCICIDS2018Test(unittest.TestCase):
    def _raw_dataframe(self, rows: int = 20) -> pd.DataFrame:
        internal_to_raw = {
            internal_name: raw_name
            for raw_name, internal_name in CICIDS2018_TO_INTERNAL.items()
        }
        data = {
            internal_to_raw.get(feature, feature): [
                feature_index + row_index + 1 for row_index in range(rows)
            ]
            for feature_index, feature in enumerate(FEATURE_COLUMNS)
        }
        data["Flow ID"] = [f"flow-{row_index}" for row_index in range(rows)]
        data["Src IP"] = [f"10.0.0.{row_index % 5}" for row_index in range(rows)]
        data["Dst IP"] = [f"10.0.1.{row_index % 5}" for row_index in range(rows)]
        data["Src Port"] = [1000 + row_index for row_index in range(rows)]
        data["Timestamp"] = [f"20/02/2018 10:00:{row_index:02d}" for row_index in range(rows)]
        data["Extra Raw Column"] = list(range(rows))
        data["Label"] = [
            "Benign"
            if row_index % 4 == 0
            else "DDOS attack-HOIC"
            if row_index % 4 == 1
            else "FTP-BruteForce"
            if row_index % 4 == 2
            else "Bot"
            for row_index in range(rows)
        ]
        return pd.DataFrame(data)

    def test_prepares_canonical_clean_split_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "raw.csv"
            output_dir = root / "prepared"
            self._raw_dataframe().to_csv(source_path, index=False)

            result = prepare_dataset(
                source=source_path,
                output_dir=output_dir,
                test_size=0.25,
                random_seed=7,
            )

            cleaned = pd.read_csv(result.cleaned_path)
            train = pd.read_csv(result.train_path)
            test = pd.read_csv(result.test_path)
            metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))

            self.assertEqual(list(cleaned.columns), FEATURE_COLUMNS + [LABEL_COLUMN])
            self.assertEqual(list(train.columns), FEATURE_COLUMNS + [LABEL_COLUMN])
            self.assertEqual(list(test.columns), FEATURE_COLUMNS + [LABEL_COLUMN])
            self.assertEqual(len(cleaned), 20)
            self.assertEqual(len(train), 15)
            self.assertEqual(len(test), 5)
            self.assertEqual(metadata["random_seed"], 7)
            self.assertEqual(metadata["test_size"], 0.25)
            self.assertEqual(metadata["feature_columns"], FEATURE_COLUMNS)
            self.assertEqual(metadata["total_rows"], 20)
            self.assertEqual(metadata["cleaned_rows"], 20)
            self.assertEqual(metadata["train_rows"], 15)
            self.assertEqual(metadata["test_rows"], 5)
            self.assertEqual(
                metadata["label_distribution"],
                {
                    "Bots": 5,
                    "Brute Force": 5,
                    "DDoS": 5,
                    "Normal Traffic": 5,
                },
            )
            self.assertEqual(
                metadata["source_files"][0]["sha256"],
                self._sha256(source_path),
            )
            self.assertEqual(
                metadata["outputs"]["cleaned"]["sha256"],
                self._sha256(result.cleaned_path),
            )
            self.assertEqual(
                metadata["outputs"]["train"]["sha256"],
                self._sha256(result.train_path),
            )
            self.assertEqual(
                metadata["outputs"]["test"]["sha256"],
                self._sha256(result.test_path),
            )

    def test_same_seed_produces_identical_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "raw.csv"
            self._raw_dataframe().to_csv(source_path, index=False)

            first = prepare_dataset(source_path, root / "first", random_seed=42)
            second = prepare_dataset(source_path, root / "second", random_seed=42)

            self.assertEqual(
                self._sha256(first.cleaned_path),
                self._sha256(second.cleaned_path),
            )
            self.assertEqual(
                self._sha256(first.train_path),
                self._sha256(second.train_path),
            )
            self.assertEqual(
                self._sha256(first.test_path),
                self._sha256(second.test_path),
            )

    def test_refuses_to_overwrite_existing_outputs_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "raw.csv"
            output_dir = root / "prepared"
            self._raw_dataframe().to_csv(source_path, index=False)
            prepare_dataset(source_path, output_dir)

            with self.assertRaisesRegex(FileExistsError, "--force"):
                prepare_dataset(source_path, output_dir)

    def test_validation_failure_writes_no_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "invalid.csv"
            output_dir = root / "prepared"
            self._raw_dataframe().drop(columns=["Protocol"]).to_csv(
                source_path,
                index=False,
            )

            with self.assertRaisesRegex(
                ValueError,
                "Missing canonical CICIDS2018 feature columns: protocol",
            ):
                prepare_dataset(source_path, output_dir)

            self.assertFalse(output_dir.exists())

    def test_missing_schema_fails_from_header_before_loading_full_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "invalid.csv"
            source_path.write_text("placeholder", encoding="utf-8")
            header = self._raw_dataframe(rows=0).drop(columns=["Protocol"])

            with patch.object(
                prepare_cicids2018.pd,
                "read_csv",
                return_value=header,
            ) as read_csv:
                with self.assertRaisesRegex(
                    ValueError,
                    "Missing canonical CICIDS2018 feature columns: protocol",
                ):
                    prepare_dataset(source_path, root / "prepared")

            read_csv.assert_called_once_with(source_path, nrows=0)

    def test_extra_columns_are_ignored_and_duplicate_rows_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "raw.csv"
            output_dir = root / "prepared"
            raw = self._raw_dataframe(rows=20)
            duplicated = pd.concat([raw, raw.iloc[[0]]], ignore_index=True)
            duplicated.to_csv(source_path, index=False)

            result = prepare_dataset(source=source_path, output_dir=output_dir)

            cleaned = pd.read_csv(result.cleaned_path)
            self.assertEqual(list(cleaned.columns), FEATURE_COLUMNS + [LABEL_COLUMN])
            self.assertNotIn("Extra Raw Column", cleaned.columns)
            self.assertEqual(len(cleaned), 20)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
