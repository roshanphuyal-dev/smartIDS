from __future__ import annotations

import hashlib
import hmac
import unittest
from unittest.mock import patch

from packet_capture.auth.request_signer import InternalRequestSigner
from response_engine.backend_command_poller import BackendCommandPoller


class BackendCommandPollerTest(unittest.TestCase):
    def test_poll_commands_returns_empty_list_on_socket_reset(self) -> None:
        poller = BackendCommandPoller(endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands")

        with patch("response_engine.backend_command_poller.request.urlopen", side_effect=ConnectionResetError()):
            self.assertEqual(poller.poll_commands(), [])

    def test_ack_command_returns_false_on_socket_reset(self) -> None:
        poller = BackendCommandPoller(endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands")

        with patch("response_engine.backend_command_poller.request.urlopen", side_effect=ConnectionResetError()):
            self.assertFalse(
                poller.ack_command(
                    ack_endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands/ack",
                    command_id="cmd-1",
                    status="blocked",
                )
            )

    def test_poll_commands_signs_request_when_signer_configured(self) -> None:
        secret = "test-secret"
        poller = BackendCommandPoller(
            endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands?limit=10",
            signer=InternalRequestSigner(secret),
        )

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["req"] = req
            raise ConnectionResetError()

        with patch("response_engine.backend_command_poller.request.urlopen", side_effect=fake_urlopen):
            poller.poll_commands()

        req = captured["req"]
        signature = req.headers.get("X-smartids-signature")
        timestamp = req.headers.get("X-smartids-timestamp")
        nonce = req.headers.get("X-smartids-nonce")
        self.assertTrue(signature)
        self.assertTrue(timestamp)
        self.assertTrue(nonce)

        body_hash = hashlib.sha256(b"").hexdigest()
        signing_string = f"GET\n/api/v1/engine-commands?limit=10\n{body_hash}\n{timestamp}\n{nonce}"
        expected_signature = hmac.new(
            secret.encode(), signing_string.encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(signature, expected_signature)

    def test_ack_command_signs_request_when_signer_configured(self) -> None:
        secret = "test-secret"
        poller = BackendCommandPoller(
            endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands",
            signer=InternalRequestSigner(secret),
        )

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["req"] = req
            raise ConnectionResetError()

        with patch("response_engine.backend_command_poller.request.urlopen", side_effect=fake_urlopen):
            poller.ack_command(
                ack_endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands/ack",
                command_id="cmd-1",
                status="blocked",
            )

        req = captured["req"]
        signature = req.headers.get("X-smartids-signature")
        timestamp = req.headers.get("X-smartids-timestamp")
        nonce = req.headers.get("X-smartids-nonce")
        self.assertTrue(signature)
        self.assertTrue(timestamp)
        self.assertTrue(nonce)

        body_hash = hashlib.sha256(req.data).hexdigest()
        signing_string = f"POST\n/api/v1/engine-commands/ack\n{body_hash}\n{timestamp}\n{nonce}"
        expected_signature = hmac.new(
            secret.encode(), signing_string.encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(signature, expected_signature)


if __name__ == "__main__":
    unittest.main()
