from __future__ import annotations

import unittest
from unittest.mock import patch

from scapy.all import Ether, IP, Raw, TCP

from packet_capture.packet_models.protocol_types import ProtocolType
from packet_capture.parsers.packet_parser import PacketParser


class PacketParserTest(unittest.TestCase):
    def test_parse_tcp_packet_maps_fields(self) -> None:
        packet = Ether() / IP(src="10.0.0.1", dst="10.0.0.2") / TCP(sport=1234, dport=80, flags="S", window=4096) / Raw(load=b"abc")

        with patch("packet_capture.parsers.packet_parser.time.time", return_value=123.456):
            parsed = PacketParser().parse(packet)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.src_ip, "10.0.0.1")
        self.assertEqual(parsed.dst_ip, "10.0.0.2")
        self.assertEqual(parsed.protocol, ProtocolType.TCP.value)
        self.assertEqual(parsed.src_port, 1234)
        self.assertEqual(parsed.dst_port, 80)
        self.assertIsNotNone(parsed.tcp_flags)
        self.assertEqual(parsed.tcp_window_size, 4096)
        self.assertEqual(parsed.payload_size, 3)
        self.assertEqual(parsed.timestamp, 123.456)

    def test_parse_non_ip_packet_returns_none(self) -> None:
        packet = Ether() / Raw(load=b"abc")

        self.assertIsNone(PacketParser().parse(packet))
