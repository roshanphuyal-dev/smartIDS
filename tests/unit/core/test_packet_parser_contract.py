from __future__ import annotations

import unittest
from unittest.mock import patch

from scapy.all import Ether, ICMP, IP, Raw, UDP

from packet_capture.packet_models.protocol_types import ProtocolType
from packet_capture.parsers.packet_parser import PacketParser


class PacketParserContractTest(unittest.TestCase):
    def test_parse_udp_packet_contract_fields(self) -> None:
        packet = Ether() / IP(src="10.0.0.1", dst="10.0.0.2") / UDP(sport=5353, dport=53) / Raw(load=b"hello")

        with patch("packet_capture.parsers.packet_parser.time.time", return_value=123.456):
            parsed = PacketParser().parse(packet)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.protocol, ProtocolType.UDP.value)
        self.assertEqual(parsed.src_port, 5353)
        self.assertEqual(parsed.dst_port, 53)
        self.assertEqual(parsed.transport_header_length, 8)
        self.assertEqual(parsed.payload_size, 5)
        self.assertEqual(parsed.packet_size, len(packet))
        self.assertEqual(parsed.timestamp, 123.456)

    def test_parse_icmp_packet_contract_fields(self) -> None:
        packet = Ether() / IP(src="10.0.0.1", dst="10.0.0.2") / ICMP() / Raw(load=b"ping")

        with patch("packet_capture.parsers.packet_parser.time.time", return_value=789.123):
            parsed = PacketParser().parse(packet)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.protocol, ProtocolType.ICMP.value)
        self.assertIsNone(parsed.src_port)
        self.assertIsNone(parsed.dst_port)
        self.assertEqual(parsed.transport_header_length, 8)
        self.assertEqual(parsed.payload_size, 4)
        self.assertEqual(parsed.timestamp, 789.123)
