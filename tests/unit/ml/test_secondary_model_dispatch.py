from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import joblib

from ml.features.schema import FEATURE_COLUMNS
from ml.runtime.artifact_integrity import compute_sha256
from ml.runtime.live_predictor import LivePredictor


def _write_checksum(path: Path) -> None:
    checksum_path = path.with_name(path.name + ".sha256")
    checksum_path.write_text(f"{compute_sha256(path)}\n", encoding="utf-8")


class FastDummyModel:
    def __init__(self, *, encoded_value: int, probabilities: list[float]) -> None:
        self.feature_names_in_ = list(FEATURE_COLUMNS)
        self._encoded_value = encoded_value
        self._probabilities = list(probabilities)

    def predict(self, frame):
        return [self._encoded_value for _ in range(len(frame))]

    def predict_proba(self, frame):
        return [list(self._probabilities) for _ in range(len(frame))]


class SlowDummyModel(FastDummyModel):
    def __init__(self, *, encoded_value: int, probabilities: list[float], sleep_seconds: float) -> None:
        super().__init__(encoded_value=encoded_value, probabilities=probabilities)
        self._sleep_seconds = sleep_seconds

    def predict(self, frame):
        time.sleep(self._sleep_seconds)
        return super().predict(frame)


class DummyLabelEncoder:
    def __init__(self, classes: list[str]) -> None:
        self.classes_ = list(classes)

    def inverse_transform(self, values):
        return [self.classes_[int(value)] for value in values]


class SecondaryModelDispatchTest(unittest.TestCase):
    SECONDARY_SLEEP_SECONDS = 0.5

    def _build_live_predictor(self, *, publish_secondary_result=None) -> tuple[LivePredictor, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        primary_root = root / "primary"
        secondary_root = root / "secondary"
        primary_root.mkdir()
        secondary_root.mkdir()

        primary_model_path = primary_root / "primary_model.pkl"
        primary_encoder_path = primary_root / "primary_encoder.pkl"
        joblib.dump(FastDummyModel(encoded_value=1, probabilities=[0.1, 0.9]), primary_model_path)
        joblib.dump(DummyLabelEncoder(["Normal Traffic", "DDoS"]), primary_encoder_path)
        (primary_root / "primary_columns.json").write_text(json.dumps(FEATURE_COLUMNS), encoding="utf-8")
        _write_checksum(primary_model_path)
        _write_checksum(primary_encoder_path)

        secondary_model_path = secondary_root / "secondary_model.pkl"
        secondary_encoder_path = secondary_root / "secondary_encoder.pkl"
        joblib.dump(
            SlowDummyModel(
                encoded_value=0,
                probabilities=[0.8, 0.2],
                sleep_seconds=self.SECONDARY_SLEEP_SECONDS,
            ),
            secondary_model_path,
        )
        joblib.dump(DummyLabelEncoder(["Normal Traffic", "DDoS"]), secondary_encoder_path)
        (secondary_root / "secondary_columns.json").write_text(json.dumps(FEATURE_COLUMNS), encoding="utf-8")
        _write_checksum(secondary_model_path)
        _write_checksum(secondary_encoder_path)

        predictor = LivePredictor(
            primary_bundle_dir=primary_root,
            primary_model_filename="primary_model.pkl",
            primary_encoder_filename="primary_encoder.pkl",
            primary_feature_columns_filename="primary_columns.json",
            secondary_bundle_dir=secondary_root,
            secondary_model_filename="secondary_model.pkl",
            secondary_encoder_filename="secondary_encoder.pkl",
            secondary_feature_columns_filename="secondary_columns.json",
            publish_secondary_result=publish_secondary_result,
        )
        return predictor, root

    def test_predict_primary_returns_quickly_regardless_of_slow_secondary(self) -> None:
        predictor, _ = self._build_live_predictor()
        self.assertTrue(predictor.enabled)

        features = {column: 1.0 for column in FEATURE_COLUMNS}

        started = time.perf_counter()
        result = predictor.predict_primary(features)
        elapsed = time.perf_counter() - started

        self.assertIsNotNone(result)
        self.assertEqual(result["label"], "DDoS")
        self.assertLess(elapsed, self.SECONDARY_SLEEP_SECONDS / 2)

    def test_submit_secondary_does_not_block_caller(self) -> None:
        received: list[tuple[dict, dict]] = []
        done = threading.Event()

        def on_secondary_result(result: dict, context: dict) -> None:
            received.append((result, context))
            done.set()

        predictor, _ = self._build_live_predictor(publish_secondary_result=on_secondary_result)
        features = {column: 1.0 for column in FEATURE_COLUMNS}
        context = {"session_key": "1.2.3.4:1-5.6.7.8:2-6", "event_type": "ml_live_secondary_shadow"}

        started = time.perf_counter()
        submitted = predictor.submit_secondary(features, context)
        elapsed = time.perf_counter() - started

        self.assertTrue(submitted)
        self.assertLess(elapsed, self.SECONDARY_SLEEP_SECONDS / 2)

        # The secondary result should still show up eventually via the injected callback.
        self.assertTrue(done.wait(timeout=self.SECONDARY_SLEEP_SECONDS * 4))
        self.assertEqual(len(received), 1)
        secondary_result, secondary_context = received[0]
        self.assertEqual(secondary_result["label"], "Normal Traffic")
        self.assertEqual(secondary_context, context)

    def test_submit_secondary_returns_false_when_secondary_disabled(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        primary_root = root / "primary"
        primary_root.mkdir()

        primary_model_path = primary_root / "primary_model.pkl"
        primary_encoder_path = primary_root / "primary_encoder.pkl"
        joblib.dump(FastDummyModel(encoded_value=1, probabilities=[0.1, 0.9]), primary_model_path)
        joblib.dump(DummyLabelEncoder(["Normal Traffic", "DDoS"]), primary_encoder_path)
        (primary_root / "primary_columns.json").write_text(json.dumps(FEATURE_COLUMNS), encoding="utf-8")
        _write_checksum(primary_model_path)
        _write_checksum(primary_encoder_path)

        predictor = LivePredictor(
            primary_bundle_dir=primary_root,
            primary_model_filename="primary_model.pkl",
            primary_encoder_filename="primary_encoder.pkl",
            primary_feature_columns_filename="primary_columns.json",
            secondary_bundle_dir=root / "missing-secondary",
        )

        self.assertTrue(predictor.enabled)
        self.assertFalse(predictor.model_stack.secondary_bundle.enabled)
        features = {column: 1.0 for column in FEATURE_COLUMNS}
        self.assertFalse(predictor.submit_secondary(features, {}))


if __name__ == "__main__":
    unittest.main()
