from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN
from ml.training.build_cicids2017_model import (
    activate_staged_directory,
    build_model_bundle,
    validate_dataset_metadata,
    write_model_manifest,
    write_sample_contracts,
)


class BuildCICIDS2017ModelTest(unittest.TestCase):
    def test_checked_in_prediction_examples_match_runtime_contract(self) -> None:
        training_path = Path(
            "ml/contracts/cicids2017_training_row.example.json"
        )
        input_path = Path("ml/contracts/live_prediction_input.example.json")
        output_path = Path("ml/contracts/live_prediction_output.example.json")

        training_row = json.loads(training_path.read_text(encoding="utf-8"))
        sample_input = json.loads(input_path.read_text(encoding="utf-8"))
        sample_output = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(
            list(training_row),
            FEATURE_COLUMNS + [LABEL_COLUMN],
        )
        self.assertEqual(list(sample_input), FEATURE_COLUMNS)
        self.assertTrue(all(isinstance(value, (int, float)) for value in sample_input.values()))
        self.assertEqual(set(sample_output), {"label", "confidence", "encoded"})
        self.assertIsInstance(sample_output["label"], str)
        self.assertIsInstance(sample_output["confidence"], (int, float))
        self.assertIsInstance(sample_output["encoded"], int)

    def test_build_trains_verifies_and_activates_complete_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_path = root / "train.csv"
            test_path = root / "test.csv"
            metadata_path = root / "metadata.json"
            active_dir = root / "saved_models"
            self._dataset(rows=20).to_csv(train_path, index=False)
            self._dataset(rows=10).to_csv(test_path, index=False)
            metadata_path.write_text(
                json.dumps(
                    self._metadata(
                        train_path,
                        test_path,
                        train_rows=20,
                        test_rows=10,
                    )
                ),
                encoding="utf-8",
            )

            result = build_model_bundle(
                train_path=train_path,
                test_path=test_path,
                dataset_metadata_path=metadata_path,
                active_dir=active_dir,
                model_type="random_forest",
            )

            expected_files = {
                "cicids2017_live_compatible_model.pkl",
                "cicids2017_live_compatible_model.pkl.sha256",
                "live_compatible_label_encoder.pkl",
                "live_compatible_label_encoder.pkl.sha256",
                "live_compatible_feature_columns.json",
                "live_compatible_benchmark_report.json",
                "cicids2017_evaluation_report.md",
                "live_compatible_training_metadata.json",
                "live_compatible_model_manifest.json",
                "live_compatible_sample_input.json",
                "live_compatible_sample_output.json",
            }
            self.assertEqual(
                expected_files,
                {path.name for path in active_dir.iterdir()},
            )
            self.assertEqual(result.active_dir, active_dir)
            sample_output = json.loads(
                (active_dir / "live_compatible_sample_output.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                set(sample_output),
                {"label", "confidence", "encoded"},
            )

    def test_failed_build_leaves_active_artifacts_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_path = root / "train.csv"
            test_path = root / "test.csv"
            metadata_path = root / "metadata.json"
            active_dir = root / "saved_models"
            active_dir.mkdir()
            (active_dir / "existing.txt").write_text("active", encoding="utf-8")
            self._dataset(rows=20).to_csv(train_path, index=False)
            invalid_test = self._dataset(rows=10)
            invalid_test[LABEL_COLUMN] = "Unseen Attack"
            invalid_test.to_csv(test_path, index=False)
            metadata_path.write_text(
                json.dumps(
                    self._metadata(
                        train_path,
                        test_path,
                        train_rows=20,
                        test_rows=10,
                    )
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Unknown test labels"):
                build_model_bundle(
                    train_path=train_path,
                    test_path=test_path,
                    dataset_metadata_path=metadata_path,
                    active_dir=active_dir,
                    model_type="random_forest",
                )

            self.assertEqual(
                (active_dir / "existing.txt").read_text(encoding="utf-8"),
                "active",
            )
            self.assertEqual(
                [path.name for path in active_dir.iterdir()],
                ["existing.txt"],
            )

    def test_validates_prepared_dataset_metadata_hashes_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_path = root / "train.csv"
            test_path = root / "test.csv"
            metadata_path = root / "metadata.json"
            self._dataset(rows=8).to_csv(train_path, index=False)
            self._dataset(rows=4).to_csv(test_path, index=False)
            metadata = self._metadata(train_path, test_path, train_rows=8, test_rows=4)
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            validated = validate_dataset_metadata(
                train_path=train_path,
                test_path=test_path,
                metadata_path=metadata_path,
            )

            self.assertEqual(validated["feature_columns"], FEATURE_COLUMNS)
            self.assertEqual(validated["train_rows"], 8)
            self.assertEqual(validated["test_rows"], 4)

    def test_rejects_dataset_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_path = root / "train.csv"
            test_path = root / "test.csv"
            metadata_path = root / "metadata.json"
            self._dataset(rows=8).to_csv(train_path, index=False)
            self._dataset(rows=4).to_csv(test_path, index=False)
            metadata = self._metadata(train_path, test_path, train_rows=8, test_rows=4)
            metadata["outputs"]["train"]["sha256"] = "incorrect"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Training dataset hash"):
                validate_dataset_metadata(train_path, test_path, metadata_path)

    def test_writes_exact_sample_input_and_output_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample_input = {
                feature: float(index + 1)
                for index, feature in enumerate(FEATURE_COLUMNS)
            }
            sample_output = {
                "label": "Normal Traffic",
                "confidence": 0.95,
                "encoded": 0,
            }

            input_path, output_path = write_sample_contracts(
                root,
                sample_input,
                sample_output,
            )

            written_input = json.loads(input_path.read_text(encoding="utf-8"))
            written_output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(list(written_input), FEATURE_COLUMNS)
            self.assertEqual(written_input, sample_input)
            self.assertEqual(written_output, sample_output)

    def test_manifest_records_artifact_hashes_and_dataset_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "model.pkl").write_bytes(b"model")
            (root / "encoder.pkl").write_bytes(b"encoder")
            dataset_metadata = {
                "source_files": [{"path": "raw.csv", "sha256": "source-hash"}],
                "outputs": {
                    "train": {"sha256": "train-hash"},
                    "test": {"sha256": "test-hash"},
                },
                "random_seed": 42,
            }

            manifest_path = write_model_manifest(
                staging_dir=root,
                dataset_metadata=dataset_metadata,
                model_type="random_forest",
                class_labels=["Normal Traffic", "Port Scanning"],
                metrics={"accuracy": 0.9},
                trained_at_utc="2026-06-15T00:00:00+00:00",
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "1.0")
            self.assertEqual(manifest["model_type"], "random_forest")
            self.assertEqual(manifest["feature_columns"], FEATURE_COLUMNS)
            self.assertEqual(
                manifest["dataset_provenance"]["outputs"]["train"]["sha256"],
                "train-hash",
            )
            self.assertEqual(
                manifest["artifacts"]["model.pkl"]["sha256"],
                self._sha256(root / "model.pkl"),
            )

    def test_activation_replaces_active_directory_after_staging_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active_dir = root / "saved_models"
            staging_dir = root / "staging"
            active_dir.mkdir()
            staging_dir.mkdir()
            (active_dir / "model.pkl").write_text("old", encoding="utf-8")
            (staging_dir / "model.pkl").write_text("new", encoding="utf-8")

            activate_staged_directory(staging_dir, active_dir)

            self.assertEqual(
                (active_dir / "model.pkl").read_text(encoding="utf-8"),
                "new",
            )
            self.assertFalse(staging_dir.exists())
            self.assertFalse(any(root.glob(".saved_models.backup-*")))

    def test_activation_restores_previous_directory_when_swap_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active_dir = root / "saved_models"
            staging_dir = root / "staging"
            active_dir.mkdir()
            staging_dir.mkdir()
            (active_dir / "model.pkl").write_text("old", encoding="utf-8")
            (staging_dir / "model.pkl").write_text("new", encoding="utf-8")
            real_replace = os.replace
            calls = 0

            def fail_second_replace(source: Path | str, destination: Path | str) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("activation failed")
                real_replace(source, destination)

            with patch(
                "ml.training.build_cicids2017_model.os.replace",
                side_effect=fail_second_replace,
            ):
                with self.assertRaisesRegex(OSError, "activation failed"):
                    activate_staged_directory(staging_dir, active_dir)

            self.assertEqual(
                (active_dir / "model.pkl").read_text(encoding="utf-8"),
                "old",
            )
            self.assertTrue(staging_dir.exists())

    @staticmethod
    def _dataset(rows: int) -> pd.DataFrame:
        data = {
            feature: [float(index + row + 1) for row in range(rows)]
            for index, feature in enumerate(FEATURE_COLUMNS)
        }
        data[LABEL_COLUMN] = [
            "Normal Traffic" if row % 2 == 0 else "Port Scanning"
            for row in range(rows)
        ]
        return pd.DataFrame(data)

    def _metadata(
        self,
        train_path: Path,
        test_path: Path,
        train_rows: int,
        test_rows: int,
    ) -> dict:
        return {
            "feature_columns": FEATURE_COLUMNS,
            "train_rows": train_rows,
            "test_rows": test_rows,
            "outputs": {
                "train": {
                    "path": str(train_path),
                    "sha256": self._sha256(train_path),
                },
                "test": {
                    "path": str(test_path),
                    "sha256": self._sha256(test_path),
                },
            },
        }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        digest.update(path.read_bytes())
        return digest.hexdigest()
