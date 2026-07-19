from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from ml.features.schema import FEATURE_COLUMNS
from ml.runtime.model_stack import RuntimeModelBundle, RuntimeModelStack


class DummyModel:
    def __init__(self, *, encoded_value: int, probabilities: list[float]) -> None:
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


def _make_bundle(*, model_key: str, model_name: str, encoded_value: int, probabilities: list[float]) -> RuntimeModelBundle:
    bundle = RuntimeModelBundle.__new__(RuntimeModelBundle)
    bundle.config = type(
        "Config",
        (),
        {
            "model_key": model_key,
            "model_name": model_name,
            "bundle_dir": "unused",
        },
    )()
    bundle.model_path = "unused-model-path"
    bundle.encoder_path = "unused-encoder-path"
    bundle.feature_columns_path = "unused-feature-columns-path"
    bundle.metadata_path = None
    bundle.enabled = True
    bundle.model = DummyModel(encoded_value=encoded_value, probabilities=probabilities)
    bundle.label_encoder = DummyLabelEncoder(["Normal Traffic", "DDoS"])
    bundle.metadata = {}
    bundle.artifact_error = None
    return bundle


def _make_stack(*, with_secondary: bool = True) -> RuntimeModelStack:
    stack = RuntimeModelStack.__new__(RuntimeModelStack)
    stack.primary_bundle = _make_bundle(
        model_key="xgboost",
        model_name="XGBoost",
        encoded_value=1,
        probabilities=[0.1, 0.9],
    )
    stack.secondary_bundle = (
        _make_bundle(
            model_key="decision_tree",
            model_name="DecisionTree",
            encoded_value=0,
            probabilities=[0.8, 0.2],
        )
        if with_secondary
        else None
    )
    stack.enabled = stack.primary_bundle.enabled
    stack.artifact_error = stack.primary_bundle.artifact_error
    stack.secondary_artifact_error = None if stack.secondary_bundle is None else stack.secondary_bundle.artifact_error
    return stack


class ModelStackSplitTest(unittest.TestCase):
    def _features(self) -> dict:
        return {column: 1.0 for column in FEATURE_COLUMNS}

    def test_build_frame_produces_expected_shape_and_sanitizes_values(self) -> None:
        stack = _make_stack()
        features = self._features()
        features[FEATURE_COLUMNS[0]] = float("inf")
        features[FEATURE_COLUMNS[1]] = float("nan")

        frame = stack.build_frame(features)

        self.assertIsInstance(frame, pd.DataFrame)
        self.assertEqual(list(frame.columns), FEATURE_COLUMNS)
        self.assertEqual(len(frame), 1)
        self.assertFalse(np.isinf(frame.to_numpy()).any())
        self.assertFalse(np.isnan(frame.to_numpy()).any())
        self.assertEqual(frame.iloc[0][FEATURE_COLUMNS[0]], 0.0)
        self.assertEqual(frame.iloc[0][FEATURE_COLUMNS[1]], 0.0)

    def test_predict_primary_matches_primary_half_of_combined_predict(self) -> None:
        stack = _make_stack()
        features = self._features()

        primary_only = stack.predict_primary(features)
        combined = stack.predict(features)

        self.assertIsNotNone(primary_only)
        self.assertIsNotNone(combined)
        for key in ("label", "confidence", "encoded", "model_key", "model_name"):
            self.assertEqual(primary_only[key], combined[key])

        # predict_primary must not have run the secondary model at all.
        self.assertNotIn("secondary", primary_only["model_outputs"])
        self.assertIn("secondary", combined["model_outputs"])
        self.assertEqual(primary_only["model_outputs"]["primary"], combined["model_outputs"]["primary"])

        self.assertEqual(primary_only["model_stack"]["secondary_enabled"], True)
        self.assertEqual(combined["model_stack"]["secondary_enabled"], True)

    def test_predict_primary_returns_none_when_stack_disabled(self) -> None:
        stack = _make_stack()
        stack.enabled = False

        self.assertIsNone(stack.predict_primary(self._features()))

    def test_predict_primary_works_without_secondary_bundle(self) -> None:
        stack = _make_stack(with_secondary=False)

        result = stack.predict_primary(self._features())

        self.assertIsNotNone(result)
        self.assertEqual(result["model_stack"]["secondary_enabled"], False)
        self.assertNotIn("secondary", result["model_outputs"])

    def test_predict_secondary_never_invoked_by_predict_primary(self) -> None:
        stack = _make_stack()
        calls = []
        original_predict = stack.secondary_bundle.model.predict

        def tracking_predict(frame):
            calls.append(frame)
            return original_predict(frame)

        stack.secondary_bundle.model.predict = tracking_predict

        stack.predict_primary(self._features())

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
