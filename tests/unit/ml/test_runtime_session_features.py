from __future__ import annotations

import math
import unittest

from feature_engine.extractors.session_feature_extractor import SessionFeatureExtractor
from ml.features.schema import FEATURE_COLUMNS
from packet_capture.packet_models.packet_data import PacketData
from packet_capture.packet_models.protocol_types import ProtocolType
from traffic_engine.session_builder.session_builder import SessionBuilder
from traffic_engine.session_builder.traffic_session import TrafficSession


class RuntimeSessionFeatureTest(unittest.TestCase):
    def test_empty_session_extracts_exact_finite_canonical_schema(self) -> None:
        session = TrafficSession(
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            protocol=ProtocolType.TCP.value,
            src_port=1234,
            dst_port=443,
            start_time=100.0,
            last_seen=100.0,
        )

        features = SessionFeatureExtractor().extract(session)

        self.assertEqual(list(features), FEATURE_COLUMNS)
        self.assertEqual(len(features), 37)
        self.assertTrue(all(math.isfinite(float(value)) for value in features.values()))
        self.assertEqual(features["flow_duration"], 0.0)
        self.assertEqual(features["flow_bytes_per_sec"], 0.0)
        self.assertEqual(features["dst_port"], 443)

    def test_tcp_session_tracks_live_compatible_feature_values_in_seconds(self) -> None:
        builder = SessionBuilder()
        extractor = SessionFeatureExtractor()
        packets = [
            self._packet(
                timestamp=100.0,
                tcp_flags=0x02,
                packet_size=60,
                payload_size=0,
                transport_header_length=20,
                tcp_window_size=64240,
            ),
            self._packet(
                timestamp=100.25,
                tcp_flags=0x18,
                packet_size=110,
                payload_size=50,
                transport_header_length=20,
                tcp_window_size=60000,
            ),
            self._packet(
                timestamp=101.0,
                tcp_flags=0x34,
                packet_size=90,
                payload_size=30,
                transport_header_length=24,
                tcp_window_size=58000,
            ),
        ]

        session = None
        for packet in packets:
            session = builder.process_packet(packet)

        features = extractor.extract(session)

        self.assertEqual(list(features), FEATURE_COLUMNS)
        self.assertEqual(features["protocol"], ProtocolType.TCP.value)
        self.assertEqual(features["flow_duration"], 1.0)
        self.assertEqual(features["total_fwd_packets"], 3)
        self.assertEqual(features["total_fwd_bytes"], 260)
        self.assertEqual(features["flow_packets_per_sec"], 3.0)
        self.assertEqual(features["fwd_packets_per_sec"], 3.0)
        self.assertEqual(features["packet_len_min"], 60.0)
        self.assertEqual(features["packet_len_max"], 110.0)
        self.assertEqual(features["fwd_iat_total"], 1.0)
        self.assertEqual(features["flow_iat_min"], 0.25)
        self.assertEqual(features["flow_iat_max"], 0.75)
        self.assertEqual(features["syn_flag_count"], 1)
        self.assertEqual(features["psh_flag_count"], 1)
        self.assertEqual(features["ack_flag_count"], 2)
        self.assertEqual(features["rst_flag_count"], 1)
        self.assertEqual(features["urg_flag_count"], 1)
        self.assertEqual(features["fwd_header_length"], 64)
        self.assertEqual(features["init_win_bytes_forward"], 64240)
        self.assertEqual(features["act_data_pkt_fwd"], 2)
        self.assertEqual(features["min_seg_size_forward"], 30)

    def test_udp_and_icmp_sessions_keep_protocol_defaults_and_header_lengths(self) -> None:
        extractor = SessionFeatureExtractor()
        udp_session = SessionBuilder().process_packet(
            self._packet(
                timestamp=10.0,
                protocol=ProtocolType.UDP.value,
                src_port=5353,
                dst_port=53,
                packet_size=70,
                payload_size=12,
                transport_header_length=8,
            )
        )
        icmp_session = SessionBuilder().process_packet(
            self._packet(
                timestamp=20.0,
                protocol=ProtocolType.ICMP.value,
                src_port=None,
                dst_port=None,
                packet_size=84,
                payload_size=56,
                transport_header_length=8,
            )
        )

        udp_features = extractor.extract(udp_session)
        icmp_features = extractor.extract(icmp_session)

        self.assertEqual(udp_features["protocol"], ProtocolType.UDP.value)
        self.assertEqual(udp_features["dst_port"], 53)
        self.assertEqual(udp_features["fwd_header_length"], 8)
        self.assertEqual(udp_features["syn_flag_count"], 0)
        self.assertEqual(icmp_features["protocol"], ProtocolType.ICMP.value)
        self.assertEqual(icmp_features["dst_port"], 0)
        self.assertEqual(icmp_features["fwd_header_length"], 8)

    def test_fin_and_rst_sessions_finalize_with_flow_end_reason(self) -> None:
        for tcp_flags in (0x01, 0x04):
            builder = SessionBuilder()
            packet = self._packet(timestamp=1.0, tcp_flags=tcp_flags)
            builder.process_packet(packet)

            finalized = builder.finalize_session_if_needed(packet)

            self.assertIsNotNone(finalized)
            self.assertEqual(finalized["reason"], "flow_end")
            self.assertTrue(finalized["session"].is_finished())

    def test_prediction_triggers_require_minimum_age_and_packet_count_then_periodic_windows(
        self,
    ) -> None:
        builder = SessionBuilder()

        packets = [
            self._packet(timestamp=0.0),
            self._packet(timestamp=1.1),
            self._packet(timestamp=1.2),
            self._packet(timestamp=1.3),
            self._packet(timestamp=1.4),
            self._packet(timestamp=1.5),
            self._packet(timestamp=2.6),
        ]

        results = []
        for packet in packets:
            builder.process_packet(packet)
            results.append(builder.should_predict(packet))

        self.assertEqual(
            results,
            [False, False, False, False, True, False, True],
        )

    def test_flow_end_prediction_triggers_even_before_minimum_packet_count(self) -> None:
        builder = SessionBuilder()
        packet = self._packet(timestamp=0.2, tcp_flags=0x01)

        builder.process_packet(packet)

        self.assertTrue(builder.should_predict(packet))

    @staticmethod
    def _packet(
        *,
        timestamp: float,
        protocol: int = ProtocolType.TCP.value,
        src_ip: str = "10.0.0.1",
        dst_ip: str = "10.0.0.2",
        src_port: int | None = 1234,
        dst_port: int | None = 443,
        packet_size: int = 60,
        tcp_flags: int | None = None,
        tcp_window_size: int | None = None,
        transport_header_length: int | None = None,
        payload_size: int | None = None,
    ) -> PacketData:
        return PacketData(
            src_ip=src_ip,
            dst_ip=dst_ip,
            protocol=protocol,
            packet_size=packet_size,
            timestamp=timestamp,
            src_port=src_port,
            dst_port=dst_port,
            tcp_flags=tcp_flags,
            tcp_window_size=tcp_window_size,
            tcp_header_length=transport_header_length,
            transport_header_length=transport_header_length,
            payload_size=payload_size,
        )

