from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from ml.features.cicids2018_mapping import (
    CICIDS2018_TO_INTERNAL,
    normalize_cicids2018_label,
)
from ml.features.cicids2018_validation import prepare_cicids2018_features
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


class CICIDS2018ValidationTest(unittest.TestCase):
    def _dataframe(self) -> pd.DataFrame:
        internal_to_raw = {
            internal_name: raw_name
            for raw_name, internal_name in CICIDS2018_TO_INTERNAL.items()
        }
        data = {
            internal_to_raw.get(feature, feature): [index + 1, index + 2]
            for index, feature in enumerate(FEATURE_COLUMNS)
        }
        data["Flow ID"] = ["flow-1", "flow-2"]
        data["Src IP"] = ["10.0.0.1", "10.0.0.2"]
        data["Dst IP"] = ["10.0.1.1", "10.0.1.2"]
        data["Src Port"] = [1111, 2222]
        data["Timestamp"] = ["20/02/2018 10:00:00", "20/02/2018 10:00:01"]
        data["Extra Numeric Feature"] = [100, 200]
        data["Label"] = ["Benign", "FTP-BruteForce"]
        return pd.DataFrame(data)

    def test_label_normalization_preserves_expected_classes(self) -> None:
        self.assertEqual(normalize_cicids2018_label("Benign"), "Normal Traffic")
        self.assertEqual(normalize_cicids2018_label("DDOS attack-HOIC"), "DDoS")
        self.assertEqual(normalize_cicids2018_label("DoS attacks-Hulk"), "DoS")
        self.assertEqual(normalize_cicids2018_label("FTP-BruteForce"), "Brute Force")
        self.assertEqual(normalize_cicids2018_label("Bot"), "Bots")

    def test_preparation_returns_only_canonical_features_in_order(self) -> None:
        features = prepare_cicids2018_features(self._dataframe())

        self.assertEqual(list(features.columns), FEATURE_COLUMNS)
        self.assertNotIn("Extra Numeric Feature", features.columns)

    def test_raw_timing_fields_are_converted_from_microseconds_to_seconds(self) -> None:
        dataframe = self._dataframe()
        dataframe.loc[0, "Flow Duration"] = 2_000_000
        dataframe.loc[0, "Flow IAT Mean"] = 500_000
        dataframe.loc[0, "Fwd IAT Tot"] = 1_500_000

        features = prepare_cicids2018_features(dataframe)

        self.assertEqual(features.loc[0, "flow_duration"], 2.0)
        self.assertEqual(features.loc[0, "flow_iat_mean"], 0.5)
        self.assertEqual(features.loc[0, "fwd_iat_total"], 1.5)

    def test_preparation_rejects_missing_canonical_features(self) -> None:
        dataframe = self._dataframe().drop(columns=["Protocol"])

        with self.assertRaisesRegex(
            ValueError,
            "Missing canonical CICIDS2018 feature columns: protocol",
        ):
            prepare_cicids2018_features(dataframe)

    def test_preparation_rejects_nan_canonical_values(self) -> None:
        dataframe = self._dataframe()
        dataframe.loc[0, "Protocol"] = np.nan

        with self.assertRaisesRegex(
            ValueError,
            "Invalid canonical CICIDS2018 feature values: protocol",
        ):
            prepare_cicids2018_features(dataframe)

    def test_preparation_rejects_non_numeric_canonical_values(self) -> None:
        dataframe = self._dataframe()
        dataframe["Protocol"] = dataframe["Protocol"].astype(object)
        dataframe.loc[0, "Protocol"] = "tcp"

        with self.assertRaisesRegex(
            ValueError,
            "Invalid canonical CICIDS2018 feature values: protocol",
        ):
            prepare_cicids2018_features(dataframe)

    def test_preparation_rejects_infinite_canonical_values(self) -> None:
        dataframe = self._dataframe()
        dataframe["Flow Duration"] = dataframe["Flow Duration"].astype(float)
        dataframe.loc[0, "Flow Duration"] = np.inf

        with self.assertRaisesRegex(
            ValueError,
            "Invalid canonical CICIDS2018 feature values: flow_duration",
        ):
            prepare_cicids2018_features(dataframe)
