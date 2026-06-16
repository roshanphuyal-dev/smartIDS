from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import joblib

from ml.features.schema import FEATURE_COLUMNS
from ml.runtime.artifact_validation import load_runtime_model_artifacts
from ml.runtime.completed_flow_predictor import CompletedFlowPredictor
from ml.runtime.live_predictor import LivePredictor


class RuntimeArtifactValidationTest(unittest.TestCase):
    def _write_artifacts(self, root: Path, feature_columns: list[str]) -> tuple[Path, Path, Path]:
        model_path = root / "model.pkl"
        encoder_path = root / "encoder.pkl"
        feature_columns_path = root / "feature_columns.json"

        joblib.dump(SimpleNamespace(feature_names_in_=list(feature_columns)), model_path)
        joblib.dump(SimpleNamespace(classes_=["Normal Traffic", "SQL Injection"]), encoder_path)
        feature_columns_path.write_text(json.dumps(feature_columns), encoding="utf-8")

        return model_path, encoder_path, feature_columns_path

    def test_load_runtime_model_artifacts_accepts_canonical_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path, encoder_path, feature_columns_path = self._write_artifacts(
                Path(temp_dir),
                FEATURE_COLUMNS,
            )

            model, encoder = load_runtime_model_artifacts(
                model_path,
                encoder_path,
                feature_columns_path,
            )

            self.assertEqual(list(model.feature_names_in_), FEATURE_COLUMNS)
            self.assertEqual(list(encoder.classes_), ["Normal Traffic", "SQL Injection"])

    def test_live_predictor_disables_prediction_on_schema_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path, encoder_path, feature_columns_path = self._write_artifacts(
                Path(temp_dir),
                FEATURE_COLUMNS[:-1] + ["unexpected_column"],
            )

            predictor = LivePredictor()
            predictor.model_path = model_path
            predictor.encoder_path = encoder_path
            predictor.feature_columns_path = feature_columns_path
            predictor.enabled = False
            predictor.model = None
            predictor.label_encoder = None
            predictor.artifact_error = None

            predictor._load_artifacts()

            self.assertFalse(predictor.enabled)
            self.assertIsNone(predictor.model)
            self.assertIsNone(predictor.label_encoder)
            self.assertIn("FEATURE_COLUMNS", predictor.artifact_error or "")

    def test_completed_flow_predictor_uses_shared_artifact_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "completed_model.pkl"
            encoder_path = root / "completed_encoder.pkl"
            feature_columns_path = root / "feature_columns.json"

            joblib.dump(SimpleNamespace(feature_names_in_=list(FEATURE_COLUMNS)), model_path)
            joblib.dump(SimpleNamespace(classes_=["Normal Traffic", "SQL Injection"]), encoder_path)
            feature_columns_path.write_text(json.dumps(FEATURE_COLUMNS), encoding="utf-8")

            predictor = CompletedFlowPredictor()
            predictor.model_path = model_path
            predictor.encoder_path = encoder_path
            predictor.feature_columns_path = feature_columns_path
            predictor.enabled = False
            predictor.model = None
            predictor.label_encoder = None
            predictor.artifact_error = None

            predictor._load_artifacts()

            self.assertTrue(predictor.enabled)
            self.assertIsNotNone(predictor.model)
            self.assertIsNotNone(predictor.label_encoder)
            self.assertIsNone(predictor.artifact_error)

