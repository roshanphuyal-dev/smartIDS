from __future__ import annotations

import unittest

from packet_capture.packet_models.protocol_types import ProtocolType


class ProtocolMappingTest(unittest.TestCase):
    def test_protocol_ids_match_project_contract(self) -> None:
        self.assertEqual(ProtocolType.TCP.value, 6)
        self.assertEqual(ProtocolType.UDP.value, 17)
        self.assertEqual(ProtocolType.ICMP.value, 1)
        self.assertEqual(ProtocolType.UNKNOWN.value, 0)
