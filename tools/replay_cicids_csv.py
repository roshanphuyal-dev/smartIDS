import argparse
import os
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from ml.features.cicids2017_mapping import (
    CICIDS2017_TO_INTERNAL,
    normalize_cicids2017_label,
)
from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN
from ml.runtime.live_predictor import LivePredictor
from packet_capture.forwarding.fastapi_alert_forwarder import FastAPIAlertForwarder
from packet_capture.utils.logger import IDSLogger, log_event
from response_engine.auto_blocker import AutoBlocker
from response_engine.policy import ResponsePolicy


def _load_project_env():
    env_path = Path(".env")
    if not env_path.exists() or not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _prepare_rows(csv_path: str, limit: int | None):
    df = pd.read_csv(csv_path)
    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns=CICIDS2017_TO_INTERNAL).copy()

    for feature in FEATURE_COLUMNS:
        if feature not in df.columns:
            df[feature] = 0

    if LABEL_COLUMN in df.columns:
        df[LABEL_COLUMN] = df[LABEL_COLUMN].apply(normalize_cicids2017_label)
    else:
        df[LABEL_COLUMN] = "Unknown"

    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].replace([np.inf, -np.inf], 0).fillna(0)

    if limit is not None and limit > 0:
        df = df.head(limit)

    return df


def main():
    parser = argparse.ArgumentParser(description="Replay CICIDS rows as timed runtime events")
    parser.add_argument("--csv-path", default="ml/data/cicids2017_test.csv")
    parser.add_argument("--interval", type=float, default=0.05, help="seconds between rows")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--alert-threshold", type=float, default=0.8)
    parser.add_argument("--forward-all-predictions", action="store_true")
    args = parser.parse_args()

    _load_project_env()
    logger = IDSLogger.get_logger("tools.replay_cicids")

    predictor = LivePredictor()
    if not predictor.enabled:
        raise RuntimeError("Live model artifacts not loaded. Train and save model first.")

    response_policy = ResponsePolicy()
    auto_blocker = AutoBlocker()

    endpoint = os.getenv("SMARTIDS_ALERT_ENDPOINT", "").strip()
    forwarder = FastAPIAlertForwarder(endpoint) if endpoint else None

    rows = _prepare_rows(args.csv_path, args.limit)

    log_event(
        logger,
        "info",
        "cicids replay started",
        {
            "event_type": "replay_start",
            "csv_path": args.csv_path,
            "row_count": int(len(rows)),
            "interval_seconds": args.interval,
            "forwarding_enabled": bool(forwarder),
            "forward_all_predictions": bool(args.forward_all_predictions),
        },
    )

    for idx, row in rows.iterrows():
        auto_blocker.expire_blocks()

        feature_values = {col: float(row[col]) for col in FEATURE_COLUMNS}
        expected_label = str(row.get(LABEL_COLUMN, "Unknown"))
        prediction = predictor.predict(feature_values)

        if prediction is None:
            continue

        src_ip = f"10.77.0.{(idx % 240) + 10}"
        dst_ip = "10.77.1.1"
        dst_port = int(feature_values.get("dst_port", 0))
        protocol = int(feature_values.get("protocol", 0))

        log_event(
            logger,
            "info",
            "replay prediction",
            {
                "event_type": "replay_prediction",
                "row_index": int(idx),
                "expected_attack_type": expected_label,
                "attack_type": prediction["label"],
                "confidence": prediction["confidence"],
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "dst_port": dst_port,
                "protocol": protocol,
            },
        )

        should_alert = (
            prediction["label"] != "Normal Traffic"
            and float(prediction["confidence"]) >= float(args.alert_threshold)
        )

        if should_alert:
            blocked, block_status = auto_blocker.temp_block(
                ip_address=src_ip,
                duration_seconds=response_policy.ml_confirmed_block_seconds,
            )
            alert_payload = {
                "type": "ml_attack_detected",
                "attack_type": prediction["label"],
                "expected_attack_type": expected_label,
                "confidence": prediction["confidence"],
                "blocked": blocked,
                "block_status": block_status,
                "block_duration_seconds": response_policy.ml_confirmed_block_seconds,
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "src_port": 0,
                "dst_port": dst_port,
                "protocol": protocol,
                "timestamp": time.time(),
                "update_type": "replay",
            }

            log_event(
                logger,
                "info",
                "replay alert emitted",
                {
                    "event_type": "alert",
                    "attack_type": alert_payload["attack_type"],
                    "confidence": alert_payload["confidence"],
                    "blocked": alert_payload["blocked"],
                    "block_status": alert_payload["block_status"],
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                },
            )

            if forwarder is not None:
                forwarder.publish_alert(alert_payload)

        elif args.forward_all_predictions and forwarder is not None:
            forwarder.publish_alert(
                {
                    "type": "ml_prediction_replay",
                    "attack_type": prediction["label"],
                    "expected_attack_type": expected_label,
                    "confidence": prediction["confidence"],
                    "blocked": False,
                    "block_status": "none",
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                    "src_port": 0,
                    "dst_port": dst_port,
                    "protocol": protocol,
                    "timestamp": time.time(),
                    "update_type": "replay_prediction",
                }
            )

        time.sleep(max(0.0, args.interval))

    log_event(
        logger,
        "info",
        "cicids replay completed",
        {
            "event_type": "replay_end",
            "rows_processed": int(len(rows)),
        },
    )


if __name__ == "__main__":
    main()
