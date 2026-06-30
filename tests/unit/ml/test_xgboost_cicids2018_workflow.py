from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


def _dataset_row(offset: int, label: str) -> dict[str, object]:
    row = {
        feature: float((offset * 3) + index + 1)
        for index, feature in enumerate(FEATURE_COLUMNS)
    }
    row["dst_port"] = 1000 + offset
    row["protocol"] = 6 if offset % 2 == 0 else 17
    row[LABEL_COLUMN] = label
    return row


class XGBoostCICIDS2018WorkflowTest(unittest.TestCase):
    def _write_dataset(self, path: Path, rows: list[dict[str, object]]) -> None:
        pd.DataFrame(rows, columns=FEATURE_COLUMNS + [LABEL_COLUMN]).to_csv(path, index=False)

    def test_training_writes_multiclass_runtime_artifacts(self) -> None:
        from ml.training.train_xgboost_cicids2018 import (
            DEFAULT_MODEL_DIR,
            DEFAULT_TRAIN_CSV,
            train_model,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_csv = root / "train.csv"
            model_dir = root / "model"
            rows = []
            labels = ["Normal Traffic", "DDoS", "DoS"]
            for index in range(24):
                rows.append(_dataset_row(index, labels[index % len(labels)]))
            self._write_dataset(train_csv, rows)

            result = train_model(
                train_csv=train_csv,
                output_dir=model_dir,
                n_estimators=8,
                max_depth=3,
                n_jobs=1,
                create_zip=True,
                chunk_size=5,
            )

            metadata = json.loads(result.training_metadata_path.read_text(encoding="utf-8"))
            feature_columns = json.loads(result.feature_columns_path.read_text(encoding="utf-8"))

            self.assertTrue(result.model_path.exists())
            self.assertTrue(result.label_encoder_path.exists())
            self.assertTrue(result.training_report_path.exists())
            self.assertTrue(result.zip_path is not None and result.zip_path.exists())
            self.assertEqual(feature_columns, FEATURE_COLUMNS)
            self.assertEqual(metadata["objective"], "multi:softprob")
            self.assertEqual(sorted(metadata["label_classes"]), ["DDoS", "DoS", "Normal Traffic"])
            self.assertEqual(metadata["train_csv"], str(train_csv))
            self.assertEqual(metadata["chunk_size"], 5)
            self.assertEqual(Path(DEFAULT_TRAIN_CSV), Path("ml/data/cicids2018_train.csv"))
            self.assertEqual(Path(DEFAULT_MODEL_DIR), Path("ml/saved_models/cicids2018_xgboost_runtime"))

    def test_evaluation_writes_reports_and_filters_unknown_labels(self) -> None:
        from ml.evaluation.test_xgboost_cicids2018 import (
            DEFAULT_MODEL_DIR,
            DEFAULT_TEST_CSV,
            evaluate_model,
        )
        from ml.training.train_xgboost_cicids2018 import train_model

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_csv = root / "train.csv"
            test_csv = root / "test.csv"
            model_dir = root / "model"
            labels = ["Normal Traffic", "DDoS", "DoS"]

            train_rows = [_dataset_row(index, labels[index % len(labels)]) for index in range(30)]
            test_rows = [_dataset_row(index + 100, labels[index % len(labels)]) for index in range(12)]
            test_rows.append(_dataset_row(500, "Unknown Attack"))

            self._write_dataset(train_csv, train_rows)
            self._write_dataset(test_csv, test_rows)

            train_model(
                train_csv=train_csv,
                output_dir=model_dir,
                n_estimators=8,
                max_depth=3,
                n_jobs=1,
                create_zip=False,
                chunk_size=7,
            )

            result = evaluate_model(
                test_csv=test_csv,
                model_dir=model_dir,
                chunk_size=4,
            )

            benchmark = json.loads(result.benchmark_report_path.read_text(encoding="utf-8"))
            report_text = result.markdown_report_path.read_text(encoding="utf-8")

            self.assertIn("accuracy", benchmark)
            self.assertEqual(benchmark["unknown_labels_filtered"], 1)
            self.assertEqual(len(benchmark["confusion_matrix"]), 3)
            self.assertIn("Normal Traffic FPR", report_text)
            self.assertEqual(benchmark["chunk_size"], 4)
            self.assertEqual(Path(DEFAULT_TEST_CSV), Path("ml/data/cicids2018_test.csv"))
            self.assertEqual(Path(DEFAULT_MODEL_DIR), Path("ml/saved_models/cicids2018_xgboost_runtime"))

    def test_evaluation_rejects_feature_schema_mismatch(self) -> None:
        from ml.evaluation.test_xgboost_cicids2018 import evaluate_model
        from ml.training.train_xgboost_cicids2018 import train_model

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_csv = root / "train.csv"
            test_csv = root / "test.csv"
            model_dir = root / "model"
            labels = ["Normal Traffic", "DDoS", "DoS"]

            rows = [_dataset_row(index, labels[index % len(labels)]) for index in range(18)]
            self._write_dataset(train_csv, rows)
            self._write_dataset(test_csv, rows)

            artifacts = train_model(
                train_csv=train_csv,
                output_dir=model_dir,
                n_estimators=6,
                max_depth=3,
                n_jobs=1,
                create_zip=False,
                chunk_size=6,
            )
            artifacts.feature_columns_path.write_text(
                json.dumps(FEATURE_COLUMNS[:-1]),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "canonical FEATURE_COLUMNS"):
                evaluate_model(
                    test_csv=test_csv,
                    model_dir=model_dir,
                )

    def test_split_defaults_point_to_real_prepared_directory_and_ml_data_outputs(self) -> None:
        from ml.datasets.split_prepared_cicids2018 import DEFAULT_OUTPUT_DIR, DEFAULT_SOURCE_DIR

        self.assertEqual(Path(DEFAULT_SOURCE_DIR), Path("ml/datasets/CIC_IDS_2018"))
        self.assertEqual(Path(DEFAULT_OUTPUT_DIR), Path("ml/data"))

    def test_training_verbose_mode_prints_progress(self) -> None:
        from ml.training.train_xgboost_cicids2018 import train_model

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_csv = root / "train.csv"
            model_dir = root / "model"
            rows = [_dataset_row(index, ["Normal Traffic", "DDoS", "DoS"][index % 3]) for index in range(18)]
            self._write_dataset(train_csv, rows)

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                train_model(
                    train_csv=train_csv,
                    output_dir=model_dir,
                    n_estimators=4,
                    max_depth=3,
                    n_jobs=1,
                    create_zip=False,
                    chunk_size=5,
                    verbose=True,
                    progress_every=1,
                )

            output = buffer.getvalue()
            self.assertIn("Counting labels", output)
            self.assertIn("Training XGBoost", output)
            self.assertIn("Computing training metrics", output)
