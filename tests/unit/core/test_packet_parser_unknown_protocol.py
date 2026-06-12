from __future__ import annotations

import unittest
from unittest.mock import patch

from scapy.all import Ether, IP

from packet_capture.packet_models.protocol_types import ProtocolType
from packet_capture.parsers.packet_parser import PacketParser


class PacketParserUnknownProtocolTest(unittest.TestCase):
    def test_parse_ip_only_packet_uses_unknown_protocol_contract(self) -> None:
        packet = Ether() / IP(src="10.0.0.1", dst="10.0.0.2")

        with patch("packet_capture.parsers.packet_parser.time.time", return_value=42.0):
            parsed = PacketParser().parse(packet)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.protocol, ProtocolType.UNKNOWN.value)
        self.assertIsNone(parsed.src_port)
        self.assertIsNone(parsed.dst_port)
        self.assertIsNone(parsed.tcp_flags)
        self.assertIsNone(parsed.tcp_window_size)
        self.assertIsNone(parsed.tcp_header_length)
        self.assertIsNone(parsed.transport_header_length)
        self.assertEqual(parsed.payload_size, 0)
        self.assertEqual(parsed.timestamp, 42.0)
