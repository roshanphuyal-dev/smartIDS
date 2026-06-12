from __future__ import annotations

import unittest
from types import SimpleNamespace

from packet_capture.forwarding.contracts import build_ids_event_payload, build_session_upsert_payload


class ForwardingContractsTest(unittest.TestCase):
    def test_build_ids_event_payload_includes_backend_facing_fields(self) -> None:
        session_key = SimpleNamespace(src_ip="10.0.0.1", dst_ip="10.0.0.2", protocol=6, src_port=1234, dst_port=80)
        session = SimpleNamespace(
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            src_port=1234,
            dst_port=80,
            protocol=6,
            last_seen=123.456,
            packet_count=9,
            total_bytes=12345,
            duration=lambda: 4.5,
        )
        prediction = {"label": "SQL Injection", "confidence": 0.91}
        features = {"flow_duration": 4.5}

        payload = build_ids_event_payload(
            session_key=session_key,
            session=session,
            prediction=prediction,
            features=features,
            event_type="ml_live_prediction",
        )

        self.assertEqual(payload["source_ip"], "10.0.0.1")
        self.assertEqual(payload["destination_ip"], "10.0.0.2")
        self.assertEqual(payload["source_port"], 1234)
        self.assertEqual(payload["destination_port"], 80)
        self.assertEqual(payload["packet_count"], 9)
        self.assertEqual(payload["byte_count"], 12345)
        self.assertEqual(payload["flow_duration"], 4.5)
        self.assertEqual(payload["attack_type"], "SQL Injection")
        self.assertEqual(payload["confidence_score"], 0.91)
        self.assertEqual(payload["action_taken"], "alert")
        self.assertIn("session_id", payload)

    def test_build_session_upsert_payload_matches_backend_contract(self) -> None:
        session_key = SimpleNamespace(src_ip="10.0.0.1", dst_ip="10.0.0.2", protocol=6, src_port=1234, dst_port=80)
        session = SimpleNamespace(
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            src_port=1234,
            dst_port=80,
            protocol=6,
            start_time=111.0,
            last_seen=123.0,
            packet_count=9,
            total_bytes=12345,
            duration=lambda: 12.0,
        )
        prediction = {"label": "Normal Traffic", "confidence": 0.2}
        heuristic_decision = SimpleNamespace(reason="clean", score=0, suspicious=False)

        payload = build_session_upsert_payload(
            session_key=session_key,
            session=session,
            session_state="active",
            prediction=prediction,
            heuristic_decision=heuristic_decision,
        )

        self.assertEqual(payload["session_id"], "10.0.0.1:1234-10.0.0.2:80-6")
        self.assertEqual(payload["start_time"], "1970-01-01T00:01:51+00:00")
        self.assertEqual(payload["end_time"], "1970-01-01T00:02:03+00:00")
        self.assertEqual(payload["source_ip"], "10.0.0.1")
        self.assertEqual(payload["destination_ip"], "10.0.0.2")
        self.assertEqual(payload["packet_count"], 9)
        self.assertEqual(payload["byte_count"], 12345)
        self.assertEqual(payload["duration"], 12.0)
        self.assertEqual(payload["state"], "active")
        self.assertEqual(payload["action_taken"], "allowed")
