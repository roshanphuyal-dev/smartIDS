from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

import joblib

from ml.features.schema import FEATURE_COLUMNS
from ml.runtime.artifact_integrity import compute_sha256
from ml.runtime.live_predictor import LivePredictor
from packet_capture.packet_models.packet_data import PacketData
from packet_capture.processor.packet_processor import PacketProcessor


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


def _build_live_predictor_with_slow_secondary(sleep_seconds: float) -> LivePredictor:
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name)
    primary_root = root / "primary"
    secondary_root = root / "secondary"
    primary_root.mkdir()
    secondary_root.mkdir()

    primary_model_path = primary_root / "primary_model.pkl"
    primary_encoder_path = primary_root / "primary_encoder.pkl"
    joblib.dump(FastDummyModel(encoded_value=0, probabilities=[0.9, 0.1]), primary_model_path)
    joblib.dump(DummyLabelEncoder(["Normal Traffic", "DDoS"]), primary_encoder_path)
    (primary_root / "primary_columns.json").write_text(json.dumps(FEATURE_COLUMNS), encoding="utf-8")
    _write_checksum(primary_model_path)
    _write_checksum(primary_encoder_path)

    secondary_model_path = secondary_root / "secondary_model.pkl"
    secondary_encoder_path = secondary_root / "secondary_encoder.pkl"
    joblib.dump(
        SlowDummyModel(encoded_value=0, probabilities=[0.8, 0.2], sleep_seconds=sleep_seconds),
        secondary_model_path,
    )
    joblib.dump(DummyLabelEncoder(["Normal Traffic", "DDoS"]), secondary_encoder_path)
    (secondary_root / "secondary_columns.json").write_text(json.dumps(FEATURE_COLUMNS), encoding="utf-8")
    _write_checksum(secondary_model_path)
    _write_checksum(secondary_encoder_path)

    return temp_dir, root, primary_root, secondary_root


class PacketProcessorSecondaryDispatchTest(unittest.TestCase):
    SECONDARY_SLEEP_SECONDS = 0.5

    def _make_packet(self, *, timestamp: float) -> PacketData:
        return PacketData(
            src_ip="10.0.0.5",
            dst_ip="10.0.0.6",
            protocol=6,
            packet_size=100,
            timestamp=timestamp,
            src_port=51000,
            dst_port=443,
        )

    def test_process_does_not_block_on_slow_secondary_model(self) -> None:
        processor = PacketProcessor()

        temp_dir, root, primary_root, secondary_root = _build_live_predictor_with_slow_secondary(
            self.SECONDARY_SLEEP_SECONDS
        )
        self.addCleanup(temp_dir.cleanup)

        received_shadow_events: list[dict] = []
        done = threading.Event()
        original_event_publisher = processor.event_publisher

        def capture_event_publisher(event: dict) -> bool:
            received_shadow_events.append(event)
            if event.get("detection_method") == "ml_live_secondary_shadow":
                done.set()
            return True

        processor.event_publisher = capture_event_publisher
        # Rewire the live predictor to route its shadow callback back into the
        # processor's own narrow publish method, matching production wiring.
        processor.live_predictor = LivePredictor(
            primary_bundle_dir=primary_root,
            primary_model_filename="primary_model.pkl",
            primary_encoder_filename="primary_encoder.pkl",
            primary_feature_columns_filename="primary_columns.json",
            secondary_bundle_dir=secondary_root,
            secondary_model_filename="secondary_model.pkl",
            secondary_encoder_filename="secondary_encoder.pkl",
            secondary_feature_columns_filename="secondary_columns.json",
            publish_secondary_result=processor._publish_secondary_shadow_event,
        )
        self.assertTrue(processor.live_predictor.enabled)

        base_ts = 1_000.0
        started = time.perf_counter()
        for index in range(5):
            processor.process(self._make_packet(timestamp=base_ts + index * 0.3))
        elapsed = time.perf_counter() - started

        # 5 packets triggering a live prediction must not block on the
        # slow secondary model running fire-and-forget in the background.
        self.assertLess(elapsed, self.SECONDARY_SLEEP_SECONDS / 2)

        # The shadow event should still show up asynchronously afterwards.
        self.assertTrue(done.wait(timeout=self.SECONDARY_SLEEP_SECONDS * 4))
        shadow_events = [e for e in received_shadow_events if e.get("detection_method") == "ml_live_secondary_shadow"]
        self.assertEqual(len(shadow_events), 1)
        self.assertEqual(shadow_events[0]["prediction"], "Normal Traffic")

        processor.event_publisher = original_event_publisher

    def test_shadow_event_callback_only_touches_event_publisher(self) -> None:
        processor = PacketProcessor()
        processor.event_publisher = Mock(return_value=True)
        processor.session_update_publisher = Mock(return_value=True)
        processor.block_event_publisher = Mock(return_value=True)
        processor.alert_publisher = Mock(return_value=True)
        processor.auto_blocker = Mock()

        result = {"label": "DDoS", "confidence": 0.95, "model_key": "decision_tree"}
        context = {
            "session_key": "10.0.0.5:51000-10.0.0.6:443-6",
            "src_ip": "10.0.0.5",
            "dst_ip": "10.0.0.6",
            "src_port": 51000,
            "dst_port": 443,
            "protocol": 6,
            "timestamp": 1000.0,
            "event_type": "ml_live_secondary_shadow",
            "is_final": False,
        }

        processor._publish_secondary_shadow_event(result, context)

        processor.event_publisher.assert_called_once()
        processor.session_update_publisher.assert_not_called()
        processor.block_event_publisher.assert_not_called()
        processor.alert_publisher.assert_not_called()
        processor.auto_blocker.temp_block.assert_not_called()
        processor.auto_blocker.record_detection_activity.assert_not_called()

        published_event = processor.event_publisher.call_args[0][0]
        self.assertEqual(published_event["detection_method"], "ml_live_secondary_shadow")
        self.assertEqual(published_event["prediction"], "DDoS")
        self.assertEqual(published_event["action"], "shadow")

    def test_telemetry_extras_reports_zero_when_no_secondary_dispatchers(self) -> None:
        processor = PacketProcessor()

        extras = processor.telemetry_extras()

        self.assertEqual(extras["secondary_model_queue_size"], 0)
        self.assertEqual(extras["secondary_model_queue_maxsize"], 0)
        self.assertEqual(extras["secondary_model_queue_usage_percent"], 0.0)
        self.assertEqual(extras["secondary_model_predictions_dropped_total"], 0)

    def test_telemetry_extras_aggregates_live_predictor_secondary_dispatcher(self) -> None:
        processor = PacketProcessor()

        temp_dir, root, primary_root, secondary_root = _build_live_predictor_with_slow_secondary(
            self.SECONDARY_SLEEP_SECONDS
        )
        self.addCleanup(temp_dir.cleanup)

        processor.live_predictor = LivePredictor(
            primary_bundle_dir=primary_root,
            primary_model_filename="primary_model.pkl",
            primary_encoder_filename="primary_encoder.pkl",
            primary_feature_columns_filename="primary_columns.json",
            secondary_bundle_dir=secondary_root,
            secondary_model_filename="secondary_model.pkl",
            secondary_encoder_filename="secondary_encoder.pkl",
            secondary_feature_columns_filename="secondary_columns.json",
            publish_secondary_result=processor._publish_secondary_shadow_event,
        )
        self.assertIsNotNone(processor.live_predictor.secondary_publisher)

        extras = processor.telemetry_extras()

        # Only the live predictor's secondary dispatcher is wired up in this
        # test; the completed-flow predictor has no secondary bundle enabled
        # (no artifacts on disk), so it contributes nothing to the aggregate.
        self.assertEqual(extras["secondary_model_queue_maxsize"], 256)
        self.assertEqual(extras["secondary_model_queue_size"], 0)
        self.assertEqual(extras["secondary_model_predictions_dropped_total"], 0)


if __name__ == "__main__":
    unittest.main()
