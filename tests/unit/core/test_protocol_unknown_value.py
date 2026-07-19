from __future__ import annotations

import unittest

from packet_capture.packet_models.protocol_types import ProtocolType


class ProtocolUnknownValueTest(unittest.TestCase):
    def test_unknown_protocol_value_is_zero(self) -> None:
        self.assertEqual(ProtocolType.UNKNOWN.value, 0)
