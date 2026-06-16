from __future__ import annotations

import unittest

import pandas as pd

from ml.datasets.cicids2017_loader import CICIDS2017Loader
from ml.features.cicids2017_mapping import CICIDS2017_TO_INTERNAL
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


class CICIDS2017LoaderFeaturesTest(unittest.TestCase):
    def test_mapping_covers_live_compatible_cicids_headers(self) -> None:
        expected_mappings = {
            "Protocol": "protocol",
            "Flow IAT Min": "flow_iat_min",
            "Flow IAT Max": "flow_iat_max",
            "Flow IAT Mean": "flow_iat_mean",
            "Flow IAT Std": "flow_iat_std",
            "Fwd IAT Min": "fwd_iat_min",
            "Fwd IAT Max": "fwd_iat_max",
            "Fwd IAT Mean": "fwd_iat_mean",
            "Fwd IAT Std": "fwd_iat_std",
            "Fwd IAT Total": "fwd_iat_total",
            "SYN Flag Count": "syn_flag_count",
            "RST Flag Count": "rst_flag_count",
            "URG Flag Count": "urg_flag_count",
            "Fwd Header Length": "fwd_header_length",
        }

        for raw_name, internal_name in expected_mappings.items():
            self.assertEqual(CICIDS2017_TO_INTERNAL.get(raw_name), internal_name)

    def _raw_dataframe(self) -> pd.DataFrame:
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

    def test_selects_exact_canonical_features_after_mapping_raw_columns(self) -> None:
        loader = CICIDS2017Loader(dataset_path="unused.csv")

        cleaned = loader.clean_dataset(self._raw_dataframe())
        features, labels = loader.split_features_labels(cleaned)

        self.assertEqual(list(features.columns), FEATURE_COLUMNS)
        self.assertEqual(loader.feature_columns, FEATURE_COLUMNS)
        self.assertNotIn("Extra Numeric Feature", features.columns)
        self.assertEqual(len(labels), 2)

    def test_rejects_missing_canonical_features_with_field_names(self) -> None:
        loader = CICIDS2017Loader(dataset_path="unused.csv")
        dataframe = self._raw_dataframe().drop(columns=["Destination Port"])

        cleaned = loader.clean_dataset(dataframe)

        with self.assertRaisesRegex(
            ValueError,
            "Missing canonical CICIDS2017 feature columns: dst_port",
        ):
            loader.split_features_labels(cleaned)

    def test_preserves_constant_canonical_features_during_cleaning(self) -> None:
        loader = CICIDS2017Loader(dataset_path="unused.csv")
        dataframe = self._raw_dataframe()
        for column in dataframe.columns:
            if column not in {LABEL_COLUMN, "Extra Numeric Feature"}:
                dataframe[column] = 1

        cleaned = loader.clean_dataset(dataframe)
        features, _ = loader.split_features_labels(cleaned)

        self.assertEqual(list(features.columns), FEATURE_COLUMNS)
