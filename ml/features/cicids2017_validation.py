from __future__ import annotations

import numpy as np
import pandas as pd

from ml.features.cicids2017_mapping import CICIDS2017_TO_INTERNAL
from ml.features.schema import FEATURE_COLUMNS


RAW_MICROSECOND_COLUMNS = (
    "Flow Duration",
    "Flow IAT Min",
    "Flow IAT Max",
    "Flow IAT Mean",
    "Flow IAT Std",
    "Fwd IAT Min",
    "Fwd IAT Max",
    "Fwd IAT Mean",
    "Fwd IAT Std",
    "Fwd IAT Total",
)


def prepare_cicids2017_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()
    for column in RAW_MICROSECOND_COLUMNS:
        if column in normalized.columns:
            normalized[column] = (
                pd.to_numeric(normalized[column], errors="coerce") / 1_000_000.0
            )

    mapped = normalized.rename(columns=CICIDS2017_TO_INTERNAL)

    missing_features = [
        feature for feature in FEATURE_COLUMNS if feature not in mapped.columns
    ]
    if missing_features:
        raise ValueError(
            "Missing canonical CICIDS2017 feature columns: "
            + ", ".join(missing_features)
        )

    features = mapped.loc[:, FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    finite_values = np.isfinite(features.to_numpy(dtype=float))
    invalid_features = [
        feature
        for index, feature in enumerate(FEATURE_COLUMNS)
        if not finite_values[:, index].all()
    ]
    if invalid_features:
        raise ValueError(
            "Invalid canonical CICIDS2017 feature values: "
            + ", ".join(invalid_features)
        )

    return features
