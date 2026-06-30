from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from ml.evaluation import evaluate_cicids2018
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN
from ml.training import train_cicids2018_live_compatible


class _FakeModel:
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.zeros(len(features), dtype=int)


class CICIDS2018TrainingEvaluationTest(unittest.TestCase):
    def _dataframe(self) -> pd.DataFrame:
        data = {
            feature: [float(index + 1), float(index + 2)]
            for index, feature in enumerate(FEATURE_COLUMNS)
        }
        data[LABEL_COLUMN] = ["Benign", "DDOS attack-HOIC"]
        return pd.DataFrame(data)

    def test_training_returns_only_canonical_features_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                train_cicids2018_live_compatible,
                "MODEL_OUTPUT_DIR",
                Path(temp_dir),
            ):
                features, _, _ = (
                    train_cicids2018_live_compatible._prepare_live_compatible_dataset(
                        self._dataframe()
                    )
                )

        self.assertEqual(list(features.columns), FEATURE_COLUMNS)

    def test_training_rejects_missing_canonical_features(self) -> None:
        dataframe = self._dataframe().drop(columns=["protocol"])

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                train_cicids2018_live_compatible,
                "MODEL_OUTPUT_DIR",
                Path(temp_dir),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Missing canonical CICIDS2018 feature columns: protocol",
                ):
                    train_cicids2018_live_compatible._prepare_live_compatible_dataset(
                        dataframe
                    )

    def test_training_rejects_infinite_canonical_values(self) -> None:
        dataframe = self._dataframe()
        dataframe["flow_duration"] = dataframe["flow_duration"].astype(float)
        dataframe.loc[0, "flow_duration"] = np.inf

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                train_cicids2018_live_compatible,
                "MODEL_OUTPUT_DIR",
                Path(temp_dir),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Invalid canonical CICIDS2018 feature values: flow_duration",
                ):
                    train_cicids2018_live_compatible._prepare_live_compatible_dataset(
                        dataframe
                    )

    def test_evaluation_rejects_missing_canonical_features(self) -> None:
        dataframe = self._dataframe().drop(columns=["protocol"])

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            feature_columns_path = root / "feature_columns.json"
            feature_columns_path.write_text(
                json.dumps(FEATURE_COLUMNS),
                encoding="utf-8",
            )
            encoder = SimpleNamespace(
                classes_=np.array(["Normal Traffic"]),
                transform=lambda labels: np.zeros(len(labels), dtype=int),
            )

            with (
                patch.object(evaluate_cicids2018, "RESULTS_DIR", root),
                patch.object(evaluate_cicids2018, "REPORT_PATH", root / "report.md"),
                patch.object(
                    evaluate_cicids2018,
                    "FEATURE_COLUMNS_PATH",
                    feature_columns_path,
                ),
                patch.object(evaluate_cicids2018.pd, "read_csv", return_value=dataframe),
                patch.object(
                    evaluate_cicids2018.joblib,
                    "load",
                    side_effect=[_FakeModel(), encoder],
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Missing canonical CICIDS2018 feature columns: protocol",
                ):
                    evaluate_cicids2018.main()
