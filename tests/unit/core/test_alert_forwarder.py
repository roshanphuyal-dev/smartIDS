from __future__ import annotations

import hashlib
import hmac
import unittest
from unittest.mock import patch

from packet_capture.auth.request_signer import InternalRequestSigner
from packet_capture.forwarding.fastapi_alert_forwarder import FastAPIAlertForwarder


class AlertForwarderTest(unittest.TestCase):
    def test_publish_alert_returns_false_on_socket_reset(self) -> None:
        forwarder = FastAPIAlertForwarder(
            endpoint_url="http://127.0.0.1:3100/api/v1/alerts/upsert",
        )

        with patch(
            "packet_capture.forwarding.fastapi_alert_forwarder.request.urlopen",
            side_effect=ConnectionResetError(),
        ):
            self.assertFalse(forwarder.publish_alert({"attack_type": "Brute Force"}))

    def test_publish_alert_signs_request_when_signer_configured(self) -> None:
        secret = "test-secret"
        forwarder = FastAPIAlertForwarder(
            endpoint_url="http://127.0.0.1:3100/api/v1/alerts/upsert",
            signer=InternalRequestSigner(secret),
        )

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["req"] = req
            raise ConnectionResetError()

        with patch(
            "packet_capture.forwarding.fastapi_alert_forwarder.request.urlopen",
            side_effect=fake_urlopen,
        ):
            forwarder.publish_alert({"attack_type": "Brute Force"})

        req = captured["req"]
        signature = req.headers.get("X-smartids-signature")
        timestamp = req.headers.get("X-smartids-timestamp")
        nonce = req.headers.get("X-smartids-nonce")
        self.assertTrue(signature)
        self.assertTrue(timestamp)
        self.assertTrue(nonce)

        body_hash = hashlib.sha256(req.data).hexdigest()
        signing_string = f"POST\n/api/v1/alerts/upsert\n{body_hash}\n{timestamp}\n{nonce}"
        expected_signature = hmac.new(
            secret.encode(), signing_string.encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(signature, expected_signature)


if __name__ == "__main__":
    unittest.main()
