from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


EXPECTED_FILES = [
    "prepared_02-14-2018.csv",
    "prepared_02-15-2018.csv",
    "prepared_02-16-2018.csv",
    "prepared_02-20-2018.csv",
    "prepared_02-21-2018.csv",
    "prepared_02-22-2018.csv",
    "prepared_02-23-2018.csv",
    "prepared_02-28-2018.csv",
    "prepared_03-01-2018.csv",
    "prepared_03-02-2018.csv",
]


def _row(offset: int, label: str) -> dict[str, object]:
    values = {
        feature: float(offset + index + 1)
        for index, feature in enumerate(FEATURE_COLUMNS)
    }
    values["dst_port"] = 80 + offset
    values["protocol"] = 6
    values[LABEL_COLUMN] = label
    return values


class SplitPreparedCICIDS2018Test(unittest.TestCase):
    def _write_source_dir(self, root: Path, rows_per_file: list[dict[str, object]]) -> None:
        for file_name in EXPECTED_FILES:
            pd.DataFrame(rows_per_file).to_csv(root / file_name, index=False)

    def test_split_outputs_reusable_train_and_test_files_for_all_expected_inputs(self) -> None:
        from ml.datasets.split_prepared_cicids2018 import split_prepared_dataset

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            output_dir = Path(temp_dir) / "output"
            source_dir.mkdir()
            rows = []
            for index in range(12):
                label = ["Normal Traffic", "DDoS", "DoS"][index % 3]
                rows.append(_row(index, label))
            self._write_source_dir(source_dir, rows)

            result = split_prepared_dataset(
                source=source_dir,
                output_dir=output_dir,
                test_size=0.25,
                random_seed=7,
                chunk_size=4,
            )

            train = pd.read_csv(result.train_path)
            test = pd.read_csv(result.test_path)
            metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))

            self.assertEqual(list(train.columns), FEATURE_COLUMNS + [LABEL_COLUMN])
            self.assertEqual(list(test.columns), FEATURE_COLUMNS + [LABEL_COLUMN])
            self.assertEqual(len(metadata["source_files"]), 10)
            self.assertIn("prepared_02-20-2018.csv", metadata["source_files"])
            self.assertEqual(len(train) + len(test), 120)
            self.assertEqual(metadata["train_rows"], len(train))
            self.assertEqual(metadata["test_rows"], len(test))
            self.assertEqual(metadata["feature_columns"], FEATURE_COLUMNS)
            self.assertIn("train_sha256", metadata)
            self.assertIn("test_sha256", metadata)

    def test_split_rejects_missing_expected_prepared_file(self) -> None:
        from ml.datasets.split_prepared_cicids2018 import split_prepared_dataset

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            output_dir = Path(temp_dir) / "output"
            source_dir.mkdir()
            rows = [_row(1, "Normal Traffic"), _row(2, "DDoS")]
            for file_name in EXPECTED_FILES:
                if file_name == "prepared_02-20-2018.csv":
                    continue
                pd.DataFrame(rows).to_csv(source_dir / file_name, index=False)

            with self.assertRaisesRegex(FileNotFoundError, "prepared_02-20-2018.csv"):
                split_prepared_dataset(
                    source=source_dir,
                    output_dir=output_dir,
                )

    def test_split_cleans_invalid_values_and_filters_bad_labels(self) -> None:
        from ml.datasets.split_prepared_cicids2018 import split_prepared_dataset

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            output_dir = Path(temp_dir) / "output"
            source_dir.mkdir()
            rows = [
                _row(1, "Normal Traffic"),
                _row(2, "DDoS"),
                _row(3, "DoS"),
                _row(4, ""),
            ]
            rows[0]["dst_port"] = 70000
            rows[0]["protocol"] = 255
            rows[0]["flow_duration"] = np.inf
            rows[1]["packet_len_mean"] = -5.0
            rows[2]["fwd_iat_total"] = np.nan
            self._write_source_dir(source_dir, rows)

            result = split_prepared_dataset(
                source=source_dir,
                output_dir=output_dir,
                test_size=0.2,
                random_seed=3,
                chunk_size=2,
            )

            combined = pd.concat(
                [
                    pd.read_csv(result.train_path),
                    pd.read_csv(result.test_path),
                ],
                ignore_index=True,
            )

            self.assertEqual(len(combined), 30)
            self.assertTrue((combined["dst_port"].between(0, 65535)).all())
            self.assertTrue(set(combined["protocol"].unique()).issubset({0, 1, 6, 17}))
            self.assertTrue(np.isfinite(combined[FEATURE_COLUMNS].to_numpy(dtype=float)).all())
            self.assertTrue((combined[FEATURE_COLUMNS] >= 0).all().all())
            self.assertNotIn("", combined[LABEL_COLUMN].astype(str).tolist())

    def test_split_verbose_mode_prints_progress(self) -> None:
        from ml.datasets.split_prepared_cicids2018 import split_prepared_dataset

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            output_dir = Path(temp_dir) / "output"
            source_dir.mkdir()
            rows = [_row(index, ["Normal Traffic", "DDoS", "DoS"][index % 3]) for index in range(6)]
            self._write_source_dir(source_dir, rows)

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                split_prepared_dataset(
                    source=source_dir,
                    output_dir=output_dir,
                    chunk_size=3,
                    verbose=True,
                    progress_every=1,
                )

            output = buffer.getvalue()
            self.assertIn("Counting labels", output)
            self.assertIn("Writing split rows", output)
