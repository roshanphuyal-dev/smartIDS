from __future__ import annotations

import unittest
from queue import Queue

from packet_capture.packet_models.packet_data import PacketData
from packet_capture.packet_models.protocol_types import ProtocolType
from packet_capture.telemetry.engine_telemetry import EngineTelemetryCollector
from traffic_engine.session_builder.session_builder import SessionBuilder


class EngineTelemetryCollectorTest(unittest.TestCase):
    def test_snapshot_reports_packet_queue_and_loss_counters(self) -> None:
        now = 100.0

        def clock() -> float:
            return now

        queue = Queue(maxsize=10)
        queue.put_nowait(object())
        queue.put_nowait(object())
        collector = EngineTelemetryCollector(clock=clock, packet_window_seconds=30)

        collector.record_packet_received()
        collector.record_packet_received()
        collector.record_packet_dropped()
        collector.record_packet_processed()

        snapshot = collector.snapshot(
            packet_queue=queue,
            session_builder=SessionBuilder(),
        )

        self.assertEqual(snapshot["packets_received_total"], 2)
        self.assertEqual(snapshot["packets_received_per_30s"], 2)
        self.assertEqual(snapshot["packets_processed_total"], 1)
        self.assertEqual(snapshot["packets_dropped_total"], 1)
        self.assertEqual(snapshot["packets_lost_total"], 1)
        self.assertTrue(snapshot["packet_loss_detected"])
        self.assertEqual(snapshot["packet_queue_size"], 2)
        self.assertEqual(snapshot["packet_queue_maxsize"], 10)
        self.assertEqual(snapshot["packet_queue_usage_percent"], 20.0)

    def test_snapshot_expires_packet_window_and_reports_ml_rate(self) -> None:
        now = 100.0

        def clock() -> float:
            return now

        collector = EngineTelemetryCollector(clock=clock, packet_window_seconds=30)
        collector.record_packet_received()
        collector.record_ml_prediction(duration_seconds=0.02)
        now = 131.0

        snapshot = collector.snapshot(
            packet_queue=Queue(maxsize=0),
            session_builder=SessionBuilder(),
        )

        self.assertEqual(snapshot["packets_received_total"], 1)
        self.assertEqual(snapshot["packets_received_per_30s"], 0)
        self.assertEqual(snapshot["ml_predictions_total"], 1)
        self.assertEqual(snapshot["ml_predictions_per_30s"], 0)
        self.assertEqual(snapshot["ml_processing_rate_per_30s"], 0)
        self.assertEqual(snapshot["last_ml_prediction_latency_ms"], 20.0)

    def test_snapshot_reports_active_sessions_and_network_exchanges(self) -> None:
        builder = SessionBuilder()
        collector = EngineTelemetryCollector(clock=lambda: 10.0)
        builder.process_packet(
            PacketData(
                src_ip="10.0.0.1",
                dst_ip="10.0.0.2",
                protocol=ProtocolType.TCP.value,
                packet_size=60,
                timestamp=1.0,
                src_port=12345,
                dst_port=443,
                payload_size=0,
            )
        )

        snapshot = collector.snapshot(
            packet_queue=Queue(maxsize=10),
            session_builder=builder,
        )

        self.assertEqual(snapshot["active_sessions"], 1)
        self.assertFalse(snapshot["application_attribution_available"])
        self.assertIn("process", snapshot["application_attribution_note"].lower())
        self.assertEqual(len(snapshot["active_network_exchanges"]), 1)
        exchange = snapshot["active_network_exchanges"][0]
        self.assertEqual(exchange["source_ip"], "10.0.0.1")
        self.assertEqual(exchange["destination_ip"], "10.0.0.2")
        self.assertEqual(exchange["destination_port"], 443)
        self.assertEqual(exchange["protocol"], ProtocolType.TCP.value)

