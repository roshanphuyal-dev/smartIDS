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


class DummyRuntimeModel:
    def __init__(self, *, encoded_value: int, probabilities: list[float]) -> None:
        self.feature_names_in_ = list(FEATURE_COLUMNS)
        self._encoded_value = encoded_value
        self._probabilities = list(probabilities)

    def predict(self, frame):
        return [self._encoded_value for _ in range(len(frame))]

    def predict_proba(self, frame):
        return [list(self._probabilities) for _ in range(len(frame))]


class DummyLabelEncoder:
    def __init__(self, classes: list[str]) -> None:
        self.classes_ = list(classes)

    def inverse_transform(self, values):
        return [self.classes_[int(value)] for value in values]


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
            root = Path(temp_dir)
            primary_root = root / "primary"
            secondary_root = root / "secondary"
            primary_root.mkdir()
            secondary_root.mkdir()

            joblib.dump(
                DummyRuntimeModel(encoded_value=1, probabilities=[0.1, 0.9]),
                primary_root / "primary_model.pkl",
            )
            joblib.dump(
                DummyLabelEncoder(["Normal Traffic", "DDoS"]),
                primary_root / "primary_encoder.pkl",
            )
            (primary_root / "primary_columns.json").write_text(
                json.dumps(FEATURE_COLUMNS[:-1] + ["unexpected_column"]),
                encoding="utf-8",
            )
            joblib.dump(
                DummyRuntimeModel(encoded_value=0, probabilities=[0.8, 0.2]),
                secondary_root / "secondary_model.pkl",
            )
            joblib.dump(
                DummyLabelEncoder(["Normal Traffic", "DDoS"]),
                secondary_root / "secondary_encoder.pkl",
            )
            (secondary_root / "secondary_columns.json").write_text(
                json.dumps(FEATURE_COLUMNS),
                encoding="utf-8",
            )

            predictor = LivePredictor(
                primary_bundle_dir=primary_root,
                primary_model_filename="primary_model.pkl",
                primary_encoder_filename="primary_encoder.pkl",
                primary_feature_columns_filename="primary_columns.json",
                secondary_bundle_dir=secondary_root,
                secondary_model_filename="secondary_model.pkl",
                secondary_encoder_filename="secondary_encoder.pkl",
                secondary_feature_columns_filename="secondary_columns.json",
            )

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

    def test_live_predictor_returns_primary_and_secondary_model_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary_root = root / "primary"
            secondary_root = root / "secondary"
            primary_root.mkdir()
            secondary_root.mkdir()

            joblib.dump(
                DummyRuntimeModel(encoded_value=1, probabilities=[0.1, 0.9]),
                primary_root / "primary_model.pkl",
            )
            joblib.dump(
                DummyRuntimeModel(encoded_value=0, probabilities=[0.8, 0.2]),
                secondary_root / "secondary_model.pkl",
            )
            joblib.dump(
                DummyLabelEncoder(["Normal Traffic", "DDoS"]),
                primary_root / "primary_encoder.pkl",
            )
            joblib.dump(
                DummyLabelEncoder(["Normal Traffic", "DDoS"]),
                secondary_root / "secondary_encoder.pkl",
            )
            (primary_root / "primary_columns.json").write_text(
                json.dumps(FEATURE_COLUMNS),
                encoding="utf-8",
            )
            (secondary_root / "secondary_columns.json").write_text(
                json.dumps(FEATURE_COLUMNS),
                encoding="utf-8",
            )
            (primary_root / "primary_metadata.json").write_text(
                json.dumps({"algorithm": "xgboost", "dataset": "cicids2018"}),
                encoding="utf-8",
            )
            (secondary_root / "secondary_metadata.json").write_text(
                json.dumps({"algorithm": "decision_tree", "dataset": "cicids2018"}),
                encoding="utf-8",
            )

            predictor = LivePredictor(
                primary_bundle_dir=primary_root,
                primary_model_filename="primary_model.pkl",
                primary_encoder_filename="primary_encoder.pkl",
                primary_feature_columns_filename="primary_columns.json",
                primary_metadata_filename="primary_metadata.json",
                secondary_bundle_dir=secondary_root,
                secondary_model_filename="secondary_model.pkl",
                secondary_encoder_filename="secondary_encoder.pkl",
                secondary_feature_columns_filename="secondary_columns.json",
                secondary_metadata_filename="secondary_metadata.json",
            )

            prediction = predictor.predict({column: 1.0 for column in FEATURE_COLUMNS})

            self.assertTrue(predictor.enabled)
            self.assertIsNotNone(prediction)
            self.assertEqual(prediction["label"], "DDoS")
            self.assertEqual(prediction["model_key"], "xgboost")
            self.assertAlmostEqual(prediction["confidence"], 0.9)
            self.assertIn("model_outputs", prediction)
            self.assertEqual(prediction["model_outputs"]["primary"]["label"], "DDoS")
            self.assertEqual(
                prediction["model_outputs"]["secondary"]["label"],
                "Normal Traffic",
            )
            self.assertEqual(
                prediction["model_outputs"]["primary"]["metadata"]["algorithm"],
                "xgboost",
            )
            self.assertEqual(
                prediction["model_outputs"]["secondary"]["metadata"]["algorithm"],
                "decision_tree",
            )

    def test_live_predictor_stays_enabled_when_secondary_bundle_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary_root = root / "primary"
            secondary_root = root / "secondary"
            primary_root.mkdir()
            secondary_root.mkdir()

            joblib.dump(
                DummyRuntimeModel(encoded_value=1, probabilities=[0.1, 0.9]),
                primary_root / "primary_model.pkl",
            )
            joblib.dump(
                DummyLabelEncoder(["Normal Traffic", "DDoS"]),
                primary_root / "primary_encoder.pkl",
            )
            (primary_root / "primary_columns.json").write_text(
                json.dumps(FEATURE_COLUMNS),
                encoding="utf-8",
            )
            (secondary_root / "secondary_columns.json").write_text(
                json.dumps(FEATURE_COLUMNS[:-1] + ["unexpected_column"]),
                encoding="utf-8",
            )
            joblib.dump(
                DummyRuntimeModel(encoded_value=0, probabilities=[0.8, 0.2]),
                secondary_root / "secondary_model.pkl",
            )
            joblib.dump(
                DummyLabelEncoder(["Normal Traffic", "DDoS"]),
                secondary_root / "secondary_encoder.pkl",
            )

            predictor = LivePredictor(
                primary_bundle_dir=primary_root,
                primary_model_filename="primary_model.pkl",
                primary_encoder_filename="primary_encoder.pkl",
                primary_feature_columns_filename="primary_columns.json",
                secondary_bundle_dir=secondary_root,
                secondary_model_filename="secondary_model.pkl",
                secondary_encoder_filename="secondary_encoder.pkl",
                secondary_feature_columns_filename="secondary_columns.json",
            )

            prediction = predictor.predict({column: 1.0 for column in FEATURE_COLUMNS})

            self.assertTrue(predictor.enabled)
            self.assertIsNotNone(prediction)
            self.assertEqual(prediction["label"], "DDoS")
            self.assertNotIn("secondary", prediction["model_outputs"])
            self.assertIn("FEATURE_COLUMNS", predictor.secondary_artifact_error or "")
