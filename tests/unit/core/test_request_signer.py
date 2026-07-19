from __future__ import annotations

import hashlib
import hmac
import unittest

from packet_capture.auth.request_signer import InternalRequestSigner, path_with_query


class InternalRequestSignerTest(unittest.TestCase):
    def test_sign_returns_all_three_headers(self) -> None:
        signer = InternalRequestSigner("test-secret")

        headers = signer.sign("POST", "/api/v1/alerts/upsert", b'{"a": 1}')

        self.assertIn("x-smartids-signature", headers)
        self.assertIn("x-smartids-timestamp", headers)
        self.assertIn("x-smartids-nonce", headers)
        self.assertEqual(len(headers["x-smartids-nonce"]), 32)

    def test_sign_recomputes_to_the_same_signature(self) -> None:
        secret = "test-secret"
        method = "POST"
        path = "/api/v1/alerts/upsert"
        body = b'{"attack_type": "Brute Force"}'

        signer = InternalRequestSigner(secret)
        headers = signer.sign(method, path, body)

        body_hash = hashlib.sha256(body).hexdigest()
        signing_string = (
            f"{method.upper()}\n{path}\n{body_hash}\n"
            f"{headers['x-smartids-timestamp']}\n{headers['x-smartids-nonce']}"
        )
        expected_signature = hmac.new(
            secret.encode(), signing_string.encode(), hashlib.sha256
        ).hexdigest()

        self.assertEqual(headers["x-smartids-signature"], expected_signature)

    def test_sign_with_query_string_in_path(self) -> None:
        signer = InternalRequestSigner("test-secret")

        headers = signer.sign("GET", "/api/v1/engine-commands?limit=10", b"")

        body_hash = hashlib.sha256(b"").hexdigest()
        signing_string = (
            f"GET\n/api/v1/engine-commands?limit=10\n{body_hash}\n"
            f"{headers['x-smartids-timestamp']}\n{headers['x-smartids-nonce']}"
        )
        expected_signature = hmac.new(
            b"test-secret", signing_string.encode(), hashlib.sha256
        ).hexdigest()

        self.assertEqual(headers["x-smartids-signature"], expected_signature)

    def test_sign_produces_a_fresh_nonce_each_call(self) -> None:
        signer = InternalRequestSigner("test-secret")

        first = signer.sign("POST", "/path", b"")
        second = signer.sign("POST", "/path", b"")

        self.assertNotEqual(first["x-smartids-nonce"], second["x-smartids-nonce"])
        self.assertNotEqual(first["x-smartids-signature"], second["x-smartids-signature"])


class PathWithQueryTest(unittest.TestCase):
    def test_path_without_query_string(self) -> None:
        self.assertEqual(
            path_with_query("http://127.0.0.1:3100/api/v1/engine-commands"),
            "/api/v1/engine-commands",
        )

    def test_path_with_query_string(self) -> None:
        self.assertEqual(
            path_with_query("http://127.0.0.1:3100/api/v1/engine-commands?limit=10"),
            "/api/v1/engine-commands?limit=10",
        )


if __name__ == "__main__":
    unittest.main()
