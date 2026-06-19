from __future__ import annotations

import unittest
from unittest.mock import patch

from packet_capture.forwarding.fastapi_engine_telemetry_forwarder import FastAPIEngineTelemetryForwarder


class EngineTelemetryForwarderTest(unittest.TestCase):
    def test_publish_telemetry_returns_false_on_socket_reset(self) -> None:
        forwarder = FastAPIEngineTelemetryForwarder(
            endpoint_url="http://127.0.0.1:3100/api/v1/engine-telemetry",
        )

        with patch("packet_capture.forwarding.fastapi_engine_telemetry_forwarder.request.urlopen", side_effect=ConnectionResetError()):
            self.assertFalse(forwarder.publish_telemetry({"ts": "2026-06-16T18:20:54Z"}))


if __name__ == "__main__":
    unittest.main()
