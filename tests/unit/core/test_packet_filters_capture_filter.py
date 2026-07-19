from __future__ import annotations

import unittest

from packet_capture.utils.packet_filters import PacketFilters


class BuildCaptureFilterTest(unittest.TestCase):
    def test_no_args_matches_basic_filter(self):
        self.assertEqual(PacketFilters.build_capture_filter(), "ip")

    def test_watch_only_combines_ips_and_ports(self):
        result = PacketFilters.build_capture_filter(
            watch_ips=["10.0.0.1", "10.0.0.2"], watch_ports=["22"]
        )
        self.assertEqual(result, "ip and (host 10.0.0.1 or host 10.0.0.2 or port 22)")

    def test_exclude_only_combines_ips_and_ports(self):
        result = PacketFilters.build_capture_filter(
            exclude_ips=["10.0.0.3"], exclude_ports=["22", "443"]
        )
        self.assertEqual(result, "ip and not (host 10.0.0.3 or port 22 or port 443)")

    def test_watch_and_exclude_combine(self):
        result = PacketFilters.build_capture_filter(
            watch_ips=["10.0.0.1"], exclude_ports=["22"]
        )
        self.assertEqual(result, "ip and (host 10.0.0.1) and not (port 22)")

    def test_malformed_entries_are_skipped_not_raised(self):
        result = PacketFilters.build_capture_filter(
            watch_ips=["not-an-ip", "10.0.0.1"],
            watch_ports=["abc", "99999", "0", "22"],
        )
        self.assertEqual(result, "ip and (host 10.0.0.1 or port 22)")


if __name__ == "__main__":
    unittest.main()
