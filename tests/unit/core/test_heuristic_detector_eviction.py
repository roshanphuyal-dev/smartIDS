from __future__ import annotations

import unittest

from packet_capture.packet_models.packet_data import PacketData
from threat_detection.heuristic import HeuristicDetector


def _make_packet(src_ip: str, timestamp: float) -> PacketData:
    return PacketData(
        src_ip=src_ip,
        dst_ip="10.0.0.100",
        protocol=6,
        packet_size=64,
        timestamp=timestamp,
        src_port=12345,
        dst_port=80,
        tcp_flags=0x10,
    )


class HeuristicDetectorEvictionTest(unittest.TestCase):
    def test_tracked_ip_count_stays_bounded_under_many_distinct_sources(self) -> None:
        detector = HeuristicDetector(max_tracked_ips=10)

        for index in range(1000):
            packet = _make_packet(f"10.1.{index // 256}.{index % 256}", 100.0 + index)
            detector.evaluate_packet(packet)

        tracked_ips = (
            set(detector._src_packet_times)
            | set(detector._src_recent_dst_ports)
            | set(detector._src_syn_only_times)
        )
        self.assertLessEqual(len(tracked_ips), 10)
        self.assertLessEqual(len(detector._last_seen), 10)

    def test_evicts_oldest_by_last_seen_first(self) -> None:
        detector = HeuristicDetector(max_tracked_ips=2)

        detector.evaluate_packet(_make_packet("10.0.0.1", 100.0))
        detector.evaluate_packet(_make_packet("10.0.0.2", 101.0))
        detector.evaluate_packet(_make_packet("10.0.0.3", 102.0))

        tracked_ips = (
            set(detector._src_packet_times)
            | set(detector._src_recent_dst_ports)
            | set(detector._src_syn_only_times)
        )
        self.assertEqual(tracked_ips, {"10.0.0.2", "10.0.0.3"})

    def test_empty_deques_are_pruned_after_time_trim(self) -> None:
        detector = HeuristicDetector(max_tracked_ips=10000)

        detector.evaluate_packet(_make_packet("10.0.0.1", 100.0))
        # Advance well past every trim window so all deques empty out.
        detector.evaluate_packet(_make_packet("10.0.0.2", 100.0 + detector.port_sweep_window_seconds + 1))

        tracked_ips = (
            set(detector._src_packet_times)
            | set(detector._src_recent_dst_ports)
            | set(detector._src_syn_only_times)
        )
        self.assertNotIn("10.0.0.1", tracked_ips)
        self.assertNotIn("10.0.0.1", detector._last_seen)


if __name__ == "__main__":
    unittest.main()
