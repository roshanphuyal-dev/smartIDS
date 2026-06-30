from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


EXPECTED_PREPARED_FILES = [
    "prepared_02-14-2018.csv",
    "prepared_02-15-2018.csv",
    "prepared_02-16-2018.csv",
    "prepared_02-20-2018.csv",
    "prepared_02-21-2018.csv",
    "prepared_02-22-2018.csv",
    "prepared_02-23-2018.csv",
    "prepared_02-28-2018.csv",
    "prepared_03-01-2018.csv",
    "prepared_03-02-2018.csv",
]

BAD_LABELS = {"", "nan", "none", "null", "label", "attack type"}
VALID_PROTOCOLS = {0, 1, 6, 17}
INT_COLUMNS = [
    "dst_port",
    "protocol",
    "total_fwd_packets",
    "total_fwd_bytes",
    "fin_flag_count",
    "syn_flag_count",
    "rst_flag_count",
    "psh_flag_count",
    "ack_flag_count",
    "urg_flag_count",
    "fwd_header_length",
    "init_win_bytes_forward",
    "act_data_pkt_fwd",
    "min_seg_size_forward",
]
CANONICAL_COLUMNS = FEATURE_COLUMNS + [LABEL_COLUMN]


def resolve_prepared_source_files(
    source: Path | str | None = None,
    files: Iterable[Path | str] | None = None,
) -> list[Path]:
    if files:
        resolved = [Path(file_path) for file_path in files]
    else:
        if source is None:
            raise ValueError("Either source or files must be provided")
        source_path = Path(source)
        if not source_path.exists() or not source_path.is_dir():
            raise FileNotFoundError(f"Prepared dataset directory not found: {source_path}")
        resolved = [source_path / name for name in EXPECTED_PREPARED_FILES]

    names = [path.name for path in resolved]
    missing = [name for name in EXPECTED_PREPARED_FILES if name not in names]
    unexpected = sorted(set(names) - set(EXPECTED_PREPARED_FILES))

    if missing:
        raise FileNotFoundError(
            "Missing expected prepared CIC IDS 2018 files: " + ", ".join(missing)
        )
    if unexpected:
        raise ValueError(
            "Unexpected prepared CIC IDS 2018 files supplied: " + ", ".join(unexpected)
        )

    ordered = {path.name: path for path in resolved}
    result = [ordered[name] for name in EXPECTED_PREPARED_FILES]
    for path in result:
        if not path.exists():
            raise FileNotFoundError(f"Prepared dataset file not found: {path}")
    return result


def validate_prepared_header(columns: Iterable[object], source_name: str) -> None:
    normalized = [str(column).strip() for column in columns]
    missing = [column for column in CANONICAL_COLUMNS if column not in normalized]
    if missing:
        raise ValueError(
            f"Missing canonical prepared CIC IDS 2018 columns in {source_name}: "
            + ", ".join(missing)
        )


def sanitize_prepared_chunk(dataframe: pd.DataFrame) -> pd.DataFrame:
    working = dataframe.copy()
    working.columns = [str(column).strip() for column in working.columns]
    validate_prepared_header(working.columns, "chunk")

    working = working.loc[:, CANONICAL_COLUMNS].copy()
    working = working[working[LABEL_COLUMN].notna()].copy()
    working[LABEL_COLUMN] = working[LABEL_COLUMN].astype(str).str.strip()
    working = working[
        ~working[LABEL_COLUMN].str.lower().isin(BAD_LABELS)
    ].copy()

    if working.empty:
        return working

    for column in FEATURE_COLUMNS:
        working[column] = pd.to_numeric(working[column], errors="coerce")

    working[FEATURE_COLUMNS] = working[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    working[FEATURE_COLUMNS] = working[FEATURE_COLUMNS].fillna(0)
    working[FEATURE_COLUMNS] = working[FEATURE_COLUMNS].clip(lower=0)

    working["protocol"] = working["protocol"].round().astype("int64")
    working.loc[~working["protocol"].isin(VALID_PROTOCOLS), "protocol"] = 0

    working["dst_port"] = working["dst_port"].round()
    working.loc[
        (working["dst_port"] < 0) | (working["dst_port"] > 65535),
        "dst_port",
    ] = 0

    for column in INT_COLUMNS:
        working[column] = working[column].round().astype("int64")

    for column in FEATURE_COLUMNS:
        if column not in INT_COLUMNS:
            working[column] = working[column].astype("float64")

    return working.reset_index(drop=True)
