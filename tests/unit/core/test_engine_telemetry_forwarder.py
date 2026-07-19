from __future__ import annotations

import hashlib
import hmac
import unittest
from unittest.mock import patch

from packet_capture.auth.request_signer import InternalRequestSigner
from packet_capture.forwarding.fastapi_engine_telemetry_forwarder import FastAPIEngineTelemetryForwarder


class EngineTelemetryForwarderTest(unittest.TestCase):
    def test_publish_telemetry_returns_false_on_socket_reset(self) -> None:
        forwarder = FastAPIEngineTelemetryForwarder(
            endpoint_url="http://127.0.0.1:3100/api/v1/engine-telemetry",
        )

        with patch("packet_capture.forwarding.fastapi_engine_telemetry_forwarder.request.urlopen", side_effect=ConnectionResetError()):
            self.assertFalse(forwarder.publish_telemetry({"ts": "2026-06-16T18:20:54Z"}))

    def test_publish_telemetry_signs_request_when_signer_configured(self) -> None:
        secret = "test-secret"
        forwarder = FastAPIEngineTelemetryForwarder(
            endpoint_url="http://127.0.0.1:3100/api/v1/engine-telemetry",
            signer=InternalRequestSigner(secret),
        )

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["req"] = req
            raise ConnectionResetError()

        with patch(
            "packet_capture.forwarding.fastapi_engine_telemetry_forwarder.request.urlopen",
            side_effect=fake_urlopen,
        ):
            forwarder.publish_telemetry({"ts": "2026-06-16T18:20:54Z"})

        req = captured["req"]
        signature = req.headers.get("X-smartids-signature")
        timestamp = req.headers.get("X-smartids-timestamp")
        nonce = req.headers.get("X-smartids-nonce")
        self.assertTrue(signature)
        self.assertTrue(timestamp)
        self.assertTrue(nonce)

        body_hash = hashlib.sha256(req.data).hexdigest()
        signing_string = f"POST\n/api/v1/engine-telemetry\n{body_hash}\n{timestamp}\n{nonce}"
        expected_signature = hmac.new(
            secret.encode(), signing_string.encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(signature, expected_signature)


if __name__ == "__main__":
    unittest.main()
