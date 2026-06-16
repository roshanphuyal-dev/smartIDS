from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from ml.evaluation import evaluate_cicids2017
from ml.features.cicids2017_mapping import (
    CICIDS2017_TO_INTERNAL,
    normalize_cicids2017_label,
)
from ml.features.cicids2017_validation import prepare_cicids2017_features
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN
from ml.training import train_cicids2017_live_compatible


class _FakeModel:
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.zeros(len(features), dtype=int)


class CICIDS2017ValidationTest(unittest.TestCase):
    def test_ddos_label_is_not_collapsed_into_dos(self) -> None:
        self.assertEqual(normalize_cicids2017_label("DDoS"), "DDoS")
        self.assertEqual(normalize_cicids2017_label("DoS Hulk"), "DoS")

    def _dataframe(self) -> pd.DataFrame:
        internal_to_raw = {
            internal_name: raw_name
            for raw_name, internal_name in CICIDS2017_TO_INTERNAL.items()
        }
        data = {
            internal_to_raw.get(feature, feature): [index + 1, index + 2]
            for index, feature in enumerate(FEATURE_COLUMNS)
        }
        data["Extra Numeric Feature"] = [100, 200]
        data[LABEL_COLUMN] = ["BENIGN", "DDoS"]
        return pd.DataFrame(data)

    def test_training_returns_only_canonical_features_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                train_cicids2017_live_compatible,
                "MODEL_OUTPUT_DIR",
                Path(temp_dir),
            ):
                features, _, _ = (
                    train_cicids2017_live_compatible._prepare_live_compatible_dataset(
                        self._dataframe()
                    )
                )

        self.assertEqual(list(features.columns), FEATURE_COLUMNS)
        self.assertNotIn("Extra Numeric Feature", features.columns)

    def test_raw_cicids_timing_fields_are_converted_from_microseconds_to_seconds(
        self,
    ) -> None:
        dataframe = self._dataframe()
        dataframe.loc[0, "Flow Duration"] = 2_000_000
        dataframe.loc[0, "Flow IAT Mean"] = 500_000
        dataframe.loc[0, "Fwd IAT Total"] = 1_500_000

        features = prepare_cicids2017_features(dataframe)

        self.assertEqual(features.loc[0, "flow_duration"], 2.0)
        self.assertEqual(features.loc[0, "flow_iat_mean"], 0.5)
        self.assertEqual(features.loc[0, "fwd_iat_total"], 1.5)

    def test_training_rejects_missing_canonical_features(self) -> None:
        dataframe = self._dataframe().drop(columns=["Protocol"])

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                train_cicids2017_live_compatible,
                "MODEL_OUTPUT_DIR",
                Path(temp_dir),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Missing canonical CICIDS2017 feature columns: protocol",
                ):
                    train_cicids2017_live_compatible._prepare_live_compatible_dataset(
                        dataframe
                    )

    def test_training_rejects_nan_canonical_values(self) -> None:
        dataframe = self._dataframe()
        dataframe.loc[0, "Protocol"] = np.nan

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                train_cicids2017_live_compatible,
                "MODEL_OUTPUT_DIR",
                Path(temp_dir),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Invalid canonical CICIDS2017 feature values: protocol",
                ):
                    train_cicids2017_live_compatible._prepare_live_compatible_dataset(
                        dataframe
                    )

    def test_training_rejects_non_numeric_canonical_values(self) -> None:
        dataframe = self._dataframe()
        dataframe["Protocol"] = dataframe["Protocol"].astype(object)
        dataframe.loc[0, "Protocol"] = "tcp"

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                train_cicids2017_live_compatible,
                "MODEL_OUTPUT_DIR",
                Path(temp_dir),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Invalid canonical CICIDS2017 feature values: protocol",
                ):
                    train_cicids2017_live_compatible._prepare_live_compatible_dataset(
                        dataframe
                    )

    def test_training_rejects_infinite_canonical_values(self) -> None:
        dataframe = self._dataframe()
        dataframe["Flow Duration"] = dataframe["Flow Duration"].astype(float)
        dataframe.loc[0, "Flow Duration"] = np.inf

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                train_cicids2017_live_compatible,
                "MODEL_OUTPUT_DIR",
                Path(temp_dir),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Invalid canonical CICIDS2017 feature values: flow_duration",
                ):
                    train_cicids2017_live_compatible._prepare_live_compatible_dataset(
                        dataframe
                    )

    def test_evaluation_rejects_missing_canonical_features(self) -> None:
        dataframe = self._dataframe().drop(columns=["Protocol"])

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
                patch.object(evaluate_cicids2017, "RESULTS_DIR", root),
                patch.object(evaluate_cicids2017, "REPORT_PATH", root / "report.md"),
                patch.object(
                    evaluate_cicids2017,
                    "FEATURE_COLUMNS_PATH",
                    feature_columns_path,
                ),
                patch.object(evaluate_cicids2017.pd, "read_csv", return_value=dataframe),
                patch.object(
                    evaluate_cicids2017.joblib,
                    "load",
                    side_effect=[_FakeModel(), encoder],
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Missing canonical CICIDS2017 feature columns: protocol",
                ):
                    evaluate_cicids2017.main()
